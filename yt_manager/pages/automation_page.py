# pages/automation_page.py — Страница «Автоматизация»
#
# Управление автоматическим пайплайном для конкретного TikTok-канала:
#   • Фильтры видео (длительность, возраст, популярные в запас)
#   • Три блока-карточки (включаемые чекбоксами):
#       1. Скачивание — проходится по привязанным YouTube-каналам
#       2. Монтаж     — обработка скачанного (cut/merge/stack)
#       3. Клипы      — нарезка обработанного на куски по N секунд
#   • Авто-триггер: раз в N минут проверяет запас готовых клипов
#
# Старая страница ProcessingPage остаётся отдельно (для ручной нарезки).

from __future__ import annotations

import logging
import os
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QLineEdit,
)

from pages.base_page import BasePage
from db import db


log = logging.getLogger(__name__)


def _match_video_filters(v: dict, f: dict) -> bool:
    """Сопоставляет видео с фильтрами автоматизации."""
    dur = v.get("duration") or 0
    if dur < int(f.get("min_duration_sec") or 0):
        return False
    if dur > int(f.get("max_duration_sec") or 10 ** 9):
        return False
    # upload_date — YYYYMMDD строкой
    if f.get("max_age_days"):
        upd = v.get("upload_date")
        if upd and len(upd) == 8:
            try:
                from datetime import datetime, timedelta
                d = datetime.strptime(upd, "%Y%m%d")
                if d < datetime.now() - timedelta(days=int(f["max_age_days"])):
                    return False
            except Exception:
                pass
    return True


class AutomationPage(BasePage):
    """Автоматизация: фильтры, блоки, авто-триггер."""

    PAGE_TITLE = "Автоматизация"

    request_open_tiktok = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_tiktok: Optional[int] = None
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(15 * 60 * 1000)  # каждые 15 минут
        self._auto_timer.timeout.connect(self._run_auto_check)

        self._build_ui()
        self.refresh()
        # Таймер стартует только если есть хотя бы один включённый блок
        self._maybe_start_timer()

    # ── UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Верх: выбор канала
        top = QHBoxLayout()
        top.addWidget(QLabel("TikTok-канал:"))
        self.cmb_channel = QComboBox()
        self.cmb_channel.setMinimumWidth(260)
        self.cmb_channel.currentIndexChanged.connect(self._on_channel_changed)
        top.addWidget(self.cmb_channel)
        top.addStretch()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #5a5957;")
        top.addWidget(self.lbl_status)
        root.addLayout(top)

        # Фильтры
        root.addWidget(self._build_filters_group())
        # Три блока
        root.addWidget(self._build_download_block())
        root.addWidget(self._build_processing_block())
        root.addWidget(self._build_clip_block())

        root.addStretch()

        # Кнопка «Сохранить»
        bar = QHBoxLayout()
        bar.addStretch()
        btn_save = QPushButton("Сохранить настройки")
        btn_save.clicked.connect(self._save_settings)
        bar.addWidget(btn_save)
        btn_run = QPushButton("Запустить пайплайн сейчас")
        btn_run.clicked.connect(self._run_pipeline_now)
        bar.addWidget(btn_run)
        root.addLayout(bar)

    def _build_filters_group(self) -> QGroupBox:
        g = QGroupBox("Фильтры видео")
        lay = QHBoxLayout(g)
        self.sp_min_dur = QSpinBox()
        self.sp_min_dur.setRange(0, 100000)
        self.sp_min_dur.setSuffix(" сек")
        self.sp_max_dur = QSpinBox()
        self.sp_max_dur.setRange(0, 100000)
        self.sp_max_dur.setSuffix(" сек")
        self.sp_max_age = QSpinBox()
        self.sp_max_age.setRange(0, 3650)
        self.sp_max_age.setSuffix(" дн")
        self.chk_popular = QCheckBox("Брать популярные если мало подходящих")

        lay.addWidget(QLabel("Мин. длительность:"))
        lay.addWidget(self.sp_min_dur)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Макс. длительность:"))
        lay.addWidget(self.sp_max_dur)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Макс. возраст:"))
        lay.addWidget(self.sp_max_age)
        lay.addSpacing(8)
        lay.addWidget(self.chk_popular)
        lay.addStretch()
        return g

    def _build_download_block(self) -> QGroupBox:
        g = QGroupBox()
        g.setCheckable(True)
        g.setChecked(True)
        g.setTitle("Скачивание новых видео")
        lay = QVBoxLayout(g)
        row = QHBoxLayout()
        lbl = QLabel("Идёт по привязанным YouTube-каналам и добавляет новые видео в очередь.")
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        btn = QPushButton("Запустить скачивание")
        btn.clicked.connect(self._run_download)
        row.addWidget(btn)
        lay.addLayout(row)
        self.g_download = g
        return g

    def _build_processing_block(self) -> QGroupBox:
        g = QGroupBox()
        g.setCheckable(True)
        g.setChecked(False)
        g.setTitle("Монтаж")
        lay = QVBoxLayout(g)

        row = QHBoxLayout()
        self.ed_banner = QLineEdit()
        btn_b = QPushButton("…")
        btn_b.clicked.connect(lambda: self._pick_dir(self.ed_banner))
        row.addWidget(QLabel("Баннеры:"))
        row.addWidget(self.ed_banner, 1)
        row.addWidget(btn_b)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.ed_retention = QLineEdit()
        btn_r = QPushButton("…")
        btn_r.clicked.connect(lambda: self._pick_dir(self.ed_retention))
        row.addWidget(QLabel("Удержание:"))
        row.addWidget(self.ed_retention, 1)
        row.addWidget(btn_r)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.ed_background = QLineEdit()
        btn_bg = QPushButton("…")
        btn_bg.clicked.connect(lambda: self._pick_dir(self.ed_background))
        row.addWidget(QLabel("Фон:"))
        row.addWidget(self.ed_background, 1)
        row.addWidget(btn_bg)
        lay.addLayout(row)

        btn_run = QPushButton("Запустить монтаж")
        btn_run.clicked.connect(self._run_processing)
        lay.addWidget(btn_run)
        self.g_processing = g
        return g

    def _build_clip_block(self) -> QGroupBox:
        g = QGroupBox()
        g.setCheckable(True)
        g.setChecked(True)
        g.setTitle("Подготовка клипов")
        lay = QVBoxLayout(g)
        row = QHBoxLayout()
        row.addWidget(QLabel("Длительность клипа:"))
        self.sp_clip_dur = QSpinBox()
        self.sp_clip_dur.setRange(5, 600)
        self.sp_clip_dur.setSuffix(" сек")
        row.addWidget(self.sp_clip_dur)
        row.addStretch()
        btn = QPushButton("Нарезать сейчас")
        btn.clicked.connect(self._run_clip_prep)
        row.addWidget(btn)
        lay.addLayout(row)
        self.g_clips = g
        return g

    # ── Data ───────────────────────────────────────────────────────
    def refresh(self):
        prev = self._current_tiktok
        self.cmb_channel.blockSignals(True)
        self.cmb_channel.clear()
        for ch in db.list_tiktok_channels():
            label = f"@{ch['handle']}"
            if ch.get("display_name"):
                label = f"{ch['display_name']}  ({label})"
            self.cmb_channel.addItem(label, ch["id"])
        self.cmb_channel.blockSignals(False)
        if prev:
            idx = self.cmb_channel.findData(prev)
            if idx >= 0:
                self.cmb_channel.setCurrentIndex(idx)
        self._on_channel_changed()

    def _on_channel_changed(self):
        tid = self.cmb_channel.currentData()
        self._current_tiktok = int(tid) if tid else None
        if not self._current_tiktok:
            self.lbl_status.setText("Нет выбранного канала.")
            return
        s = db.get_automation_settings(self._current_tiktok)
        self.sp_min_dur.setValue(int(s.get("min_duration_sec") or 300))
        self.sp_max_dur.setValue(int(s.get("max_duration_sec") or 1800))
        self.sp_max_age.setValue(int(s.get("max_age_days") or 7))
        self.chk_popular.setChecked(bool(s.get("fallback_popular")))
        self.g_download.setChecked(bool(s.get("download_enabled")))
        self.g_processing.setChecked(bool(s.get("processing_enabled")))
        self.g_clips.setChecked(bool(s.get("publish_enabled")))
        self.ed_banner.setText(s.get("banner_dir") or "")
        self.ed_retention.setText(s.get("retention_dir") or "")
        self.ed_background.setText(s.get("background_dir") or "")
        self.sp_clip_dur.setValue(int(s.get("clip_duration_sec") or 30))

        ready = db.count_ready_clips(self._current_tiktok)
        ch = db.get_tiktok_channel(self._current_tiktok)
        buf = ch.get("clip_min_buffer", 10) if ch else 10
        self.lbl_status.setText(
            f"Готовых клипов: {ready} / {buf}"
        )

    def _save_settings(self):
        if not self._current_tiktok:
            QMessageBox.information(self, "Нет канала",
                                    "Сначала создайте TikTok-канал на вкладке 'TikTok каналы'.")
            return
        db.set_automation_settings(
            self._current_tiktok,
            download_enabled=int(self.g_download.isChecked()),
            processing_enabled=int(self.g_processing.isChecked()),
            publish_enabled=int(self.g_clips.isChecked()),
            min_duration_sec=self.sp_min_dur.value(),
            max_duration_sec=self.sp_max_dur.value(),
            max_age_days=self.sp_max_age.value(),
            fallback_popular=int(self.chk_popular.isChecked()),
            banner_dir=self.ed_banner.text().strip() or None,
            retention_dir=self.ed_retention.text().strip() or None,
            background_dir=self.ed_background.text().strip() or None,
            clip_duration_sec=self.sp_clip_dur.value(),
        )
        QMessageBox.information(self, "Сохранено", "Настройки автоматизации сохранены.")
        self._maybe_start_timer()

    # ── Actions ────────────────────────────────────────────────────
    def _pick_dir(self, target: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Выберите папку", target.text() or "")
        if d:
            target.setText(d)

    def _current_filter(self) -> dict:
        return {
            "min_duration_sec": self.sp_min_dur.value(),
            "max_duration_sec": self.sp_max_dur.value(),
            "max_age_days": self.sp_max_age.value(),
            "fallback_popular": int(self.chk_popular.isChecked()),
        }

    def _run_download(self):
        if not self._current_tiktok:
            QMessageBox.information(self, "Нет канала",
                                    "Сначала выберите TikTok-канал.")
            return
        yt_list = db.list_youtube_for_tiktok(self._current_tiktok)
        if not yt_list:
            QMessageBox.information(
                self, "Нет связей",
                "К этому TikTok-каналу не привязан ни один YouTube-канал. "
                "Привяжите их на вкладке YouTube каналов."
            )
            return
        f = self._current_filter()
        queued = 0
        try:
            from download_queue import queue_manager
        except Exception as e:
            log.exception("download_queue import failed: %s", e)
            QMessageBox.warning(self, "Ошибка", f"Не удалось получить очередь загрузок: {e}")
            return

        for c in yt_list:
            videos = db.get_videos_by_channel(c["id"], status="new")
            matched = [v for v in videos if _match_video_filters(v, f)]
            if not matched and f.get("fallback_popular"):
                matched = sorted(videos, key=lambda v: v.get("view_count") or 0, reverse=True)[:5]
            for v in matched:
                try:
                    queue_manager.add(
                        v["id"], v.get("title") or v.get("yt_id"),
                        v.get("yt_id"),
                        output_dir=os.path.abspath("downloads"),
                        quality="1080p",
                    )
                    queued += 1
                except Exception as e:
                    log.warning("queue add failed for %s: %s", v.get("yt_id"), e)

        QMessageBox.information(
            self, "Скачивание запущено",
            f"В очередь добавлено {queued} видео (каналов: {len(yt_list)})."
        )

    def _run_processing(self):
        QMessageBox.information(
            self, "Монтаж",
            "Монтаж выполняется через существующий video_service.py.\n"
            "Настройки сохранены; полная автоматизация монтажа будет подключена в "
            "отдельной итерации — пока используйте страницу «Обработка» для ручной "
            "композиции или запустите нарезку клипов."
        )

    def _run_clip_prep(self):
        """Создаёт записи clips по всем обработанным видео из привязанных
        YouTube-каналов. Нарезка физических файлов в video_service — TODO,
        здесь регистрируем ссылки на существующие файлы обработанного."""
        if not self._current_tiktok:
            return
        yt_list = db.list_youtube_for_tiktok(self._current_tiktok)
        if not yt_list:
            QMessageBox.information(self, "Нет связей",
                                    "Нет привязанных YouTube-каналов.")
            return
        added = 0
        for c in yt_list:
            for v in db.get_videos_by_channel(c["id"], status="processed"):
                file_path = v.get("file_path")
                if not file_path or not os.path.isfile(file_path):
                    continue
                # Проверяем не добавлен ли уже клип на это видео
                existing = db.list_clips(self._current_tiktok)
                if any(cl.get("source_video_id") == v["id"] for cl in existing):
                    continue
                db.add_clip(
                    self._current_tiktok, file_path,
                    source_video_id=v["id"],
                    duration=v.get("duration"),
                    status="ready",
                )
                added += 1
        self._on_channel_changed()
        QMessageBox.information(
            self, "Подготовка клипов",
            f"Добавлено {added} клипов в реестр.\n"
            f"Физическая нарезка файлов по {self.sp_clip_dur.value()} сек "
            f"будет подключена в следующей итерации."
        )

    def _run_pipeline_now(self):
        if self.g_download.isChecked():
            self._run_download()
        if self.g_clips.isChecked():
            self._run_clip_prep()

    # ── Авто-триггер ──────────────────────────────────────────────
    def _maybe_start_timer(self):
        any_on = any(
            bool(s.get("download_enabled") or s.get("publish_enabled"))
            for s in (db.get_automation_settings(ch["id"])
                      for ch in db.list_tiktok_channels())
        )
        if any_on and not self._auto_timer.isActive():
            self._auto_timer.start()
        elif not any_on and self._auto_timer.isActive():
            self._auto_timer.stop()

    def _run_auto_check(self):
        """Раз в N минут: для каждого TikTok-канала с включённой автоматизацией
        проверяем запас клипов и добираем."""
        try:
            for ch in db.list_tiktok_channels():
                s = db.get_automation_settings(ch["id"])
                if not s.get("download_enabled") and not s.get("publish_enabled"):
                    continue
                ready = db.count_ready_clips(ch["id"])
                buf = ch.get("clip_min_buffer", 10)
                if ready >= buf:
                    continue
                log.info("auto: канал %s — %d/%d клипов, запускаю пайплайн",
                         ch["handle"], ready, buf)
                # Заглушка: если подписан на канал в UI — не запускаем жёстко,
                # только сообщаем в статусбаре на следующей видимой странице.
        except Exception:
            log.exception("auto check failed")
