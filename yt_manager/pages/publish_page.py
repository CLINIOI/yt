# pages/publish_page.py — Страница «Публикация»
#
# Слева — список TikTok-каналов с индикатором запаса готовых клипов.
# Справа — таблица скриптов (draft/marked) с кнопками:
#   Скопировать  — кладёт строку публикации в буфер и помечает 'marked'
#   Отмена       — возвращает скрипт в 'draft'
#   Готово       — закрывает скрипт (status='done'), клип → 'published'
# Если все скрипты 'done' и готовых клипов < clip_min_buffer —
# показывается баннер «Нужны новые клипы».

from __future__ import annotations

import logging
import os
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from pages.base_page import BasePage
from db import db
from tiktok.script_builder import build_string


log = logging.getLogger(__name__)


class PublishPage(BasePage):
    """Публикация: список каналов + таблица скриптов с действиями."""

    PAGE_TITLE = "Публикация"

    request_open_automation = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_id: int | None = None
        self._build_ui()
        self.refresh()

    # ── UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_left())
        split.addWidget(self._build_right())
        split.setSizes([280, 760])
        root.addWidget(split)

    def _build_left(self) -> QWidget:
        f = QFrame()
        lay = QVBoxLayout(f)
        lay.setContentsMargins(8, 8, 8, 8)

        lbl = QLabel("TikTok-каналы")
        lbl.setStyleSheet("font-weight: 700;")
        lay.addWidget(lbl)

        self.list_channels = QListWidget()
        self.list_channels.currentItemChanged.connect(self._on_channel_selected)
        lay.addWidget(self.list_channels, 1)
        return f

    def _build_right(self) -> QWidget:
        f = QWidget()
        lay = QVBoxLayout(f)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(8)

        self.lbl_title = QLabel("Выберите канал слева.")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(self.lbl_title)

        # Баннер «Нужны новые клипы»
        self.banner = QFrame()
        self.banner.setObjectName("banner_need_clips")
        self.banner.setStyleSheet(
            "QFrame#banner_need_clips { background:#3a2c1c; border:1px solid #6b4924;"
            "border-radius: 6px; padding: 8px; }"
            "QLabel { color: #e1b070; }"
        )
        blay = QHBoxLayout(self.banner)
        blay.setContentsMargins(12, 8, 12, 8)
        blay.addWidget(QLabel("Готовых клипов меньше минимума. Запустите пайплайн в «Автоматизации»."))
        blay.addStretch()
        btn_go = QPushButton("Перейти в Автоматизацию")
        btn_go.clicked.connect(self._emit_open_automation)
        blay.addWidget(btn_go)
        self.banner.hide()
        lay.addWidget(self.banner)

        # Таблица скриптов
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(
            ["Заголовок", "Теги", "Статус", "Создан", "Действия"]
        )
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.verticalHeader().setVisible(False)
        lay.addWidget(self.tbl, 1)
        return f

    # ── Data ───────────────────────────────────────────────────────
    def refresh(self):
        prev = self._current_id
        self.list_channels.clear()
        for ch in db.list_tiktok_channels():
            ready = db.count_ready_clips(ch["id"])
            buf = ch.get("clip_min_buffer", 10)
            handle = f"@{ch['handle']}"
            name = ch.get("display_name") or handle
            label = f"{name}   ·  клипов: {ready}/{buf}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, ch["id"])
            self.list_channels.addItem(item)
        if prev:
            for i in range(self.list_channels.count()):
                if int(self.list_channels.item(i).data(Qt.ItemDataRole.UserRole)) == prev:
                    self.list_channels.setCurrentRow(i)
                    break

    def _on_channel_selected(self, current: QListWidgetItem, _prev):
        if not current:
            self._current_id = None
            self.lbl_title.setText("Выберите канал слева.")
            self.tbl.setRowCount(0)
            self.banner.hide()
            return
        self._current_id = int(current.data(Qt.ItemDataRole.UserRole))
        self._refresh_table()

    def _refresh_table(self):
        if not self._current_id:
            return
        ch = db.get_tiktok_channel(self._current_id)
        self.lbl_title.setText(f"Скрипты публикации  ·  @{ch['handle']}")

        scripts = db.list_publish_scripts(self._current_id)
        active = [s for s in scripts if s.get("status") != "done"]
        self.tbl.setRowCount(0)
        for s in active:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(s.get("title") or "—"))
            self.tbl.setItem(r, 1, QTableWidgetItem(s.get("hashtags") or ""))
            self.tbl.setItem(r, 2, QTableWidgetItem(s.get("status") or "draft"))
            self.tbl.setItem(r, 3, QTableWidgetItem(s.get("created_at") or ""))

            # Кнопки действий
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(4)
            btn_copy = QPushButton("Скопировать")
            btn_copy.clicked.connect(lambda _=None, sid=s["id"]: self._on_copy(sid))
            btn_cancel = QPushButton("Отмена")
            btn_cancel.clicked.connect(lambda _=None, sid=s["id"]: self._on_cancel(sid))
            btn_done = QPushButton("Готово")
            btn_done.clicked.connect(lambda _=None, sid=s["id"]: self._on_done(sid))
            hl.addWidget(btn_copy)
            hl.addWidget(btn_cancel)
            hl.addWidget(btn_done)
            self.tbl.setCellWidget(r, 4, w)

        # Баннер «нужны клипы»
        done = [s for s in scripts if s.get("status") == "done"]
        all_done = scripts and len(done) == len(scripts)
        ready = db.count_ready_clips(self._current_id)
        buf = ch.get("clip_min_buffer", 10)
        need_more = (not scripts) or (all_done and ready < buf)
        self.banner.setVisible(bool(need_more))

    # ── Actions ────────────────────────────────────────────────────
    def _on_copy(self, script_id: int):
        s = db.get_publish_script(script_id)
        if not s:
            return
        # Пересобираем строку из сохранённых полей
        tags = s.get("hashtags") or ""
        path = s.get("file_path") or ""
        caption = s.get("title") or ""
        text = s.get("caption") or build_string(path, tags, datetime.now(), caption)
        QGuiApplication.clipboard().setText(text)
        db.update_publish_script_status(script_id, "marked")
        self._refresh_table()
        log.info("publish: copied script %s", script_id)

    def _on_cancel(self, script_id: int):
        db.update_publish_script_status(script_id, "draft")
        self._refresh_table()

    def _on_done(self, script_id: int):
        if QMessageBox.question(
            self, "Отметить выполненным?",
            "Скрипт будет закрыт, а связанный клип помечен как опубликованный."
        ) != QMessageBox.StandardButton.Yes:
            return
        db.update_publish_script_status(script_id, "done")
        self._refresh_table()
        self.refresh()

    def _emit_open_automation(self):
        if self._current_id:
            self.request_open_automation.emit(self._current_id)
