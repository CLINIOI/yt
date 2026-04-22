# pages/tiktok_page.py — Страница «TikTok каналы»
#
# Левая колонка: список TikTok-каналов + "+ Добавить".
# Правая колонка (при выборе канала):
#   • Статистика (YT-каналы, видео, готовые клипы, опубликовано)
#   • Хэштеги канала (редактируемые + генерация)
#   • График публикаций (список времён HH:MM)
#   • Таблица скриптов публикации
#   • Таблица опубликованного

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import QTime

from pages.base_page import BasePage
from db import db
from utils import normalize_hashtags
from tiktok.hashtag_generator import generate_hashtags
from tiktok.script_builder import build_string


log = logging.getLogger(__name__)


_TIME_SLOT_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _next_free_slot(schedule: list, busy: set) -> str | None:
    """Возвращает ближайший свободный слот публикации в формате
    'YYYY-MM-DD HH:MM'. `schedule` — список строк 'HH:MM' из
    графика канала; `busy` — уже занятые (точные строки).
    Если расписание пусто — возвращает None (планирование не задано)."""
    if not schedule:
        return None
    slots = sorted({s for s in schedule if _TIME_SLOT_RE.match(s)})
    if not slots:
        return None
    from datetime import timedelta
    today = datetime.now().date()
    for day_offset in range(0, 30):
        d = today + timedelta(days=day_offset)
        for hhmm in slots:
            candidate = f"{d.isoformat()} {hhmm}"
            # На сегодня — только будущие
            if day_offset == 0:
                h, m = hhmm.split(":")
                dt_cand = datetime.combine(
                    d, datetime.min.time().replace(hour=int(h), minute=int(m))
                )
                if dt_cand < datetime.now():
                    continue
            if candidate not in busy:
                return candidate
    return None


class AddTikTokDialog(QDialog):
    """Модалка создания нового TikTok-канала."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить TikTok-канал")
        self.setMinimumWidth(420)

        form = QFormLayout()
        self.ed_handle = QLineEdit()
        self.ed_handle.setPlaceholderText("@username")
        self.ed_name = QLineEdit()
        self.ed_avatar = QLineEdit()
        self.ed_avatar.setPlaceholderText("https://…  (необязательно)")
        self.sp_buffer = QSpinBox()
        self.sp_buffer.setRange(1, 500)
        self.sp_buffer.setValue(10)

        form.addRow("Handle (@…):", self.ed_handle)
        form.addRow("Отображаемое имя:", self.ed_name)
        form.addRow("Аватар (URL):", self.ed_avatar)
        form.addRow("Минимум готовых клипов:", self.sp_buffer)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(btns)

    def data(self) -> dict:
        return {
            "handle": self.ed_handle.text().strip().lstrip("@"),
            "display_name": self.ed_name.text().strip() or None,
            "avatar_url": self.ed_avatar.text().strip() or None,
            "clip_min_buffer": self.sp_buffer.value(),
        }


class TikTokPage(BasePage):
    """Управление TikTok-каналами."""

    PAGE_TITLE = "TikTok каналы"

    channel_selected = pyqtSignal(int)
    request_navigate_automation = pyqtSignal(int)  # перейти в Автоматизацию с данным tiktok_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_id: int | None = None
        self._suppress_autosave = False
        self._tags_save_timer = QTimer(self)
        self._tags_save_timer.setSingleShot(True)
        self._tags_save_timer.timeout.connect(self._autosave_tags)
        self._schedule_save_timer = QTimer(self)
        self._schedule_save_timer.setSingleShot(True)
        self._schedule_save_timer.timeout.connect(self._autosave_schedule)
        self._build_ui()
        self._reload_channels()

    # ── UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 760])

        root.addWidget(splitter)

    def _build_left(self) -> QWidget:
        frame = QFrame()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        header = QLabel("Каналы")
        header.setStyleSheet("font-weight: 700; font-size: 14px;")
        lay.addWidget(header)

        self.list_channels = QListWidget()
        self.list_channels.currentItemChanged.connect(self._on_channel_selected)
        lay.addWidget(self.list_channels, 1)

        btn_add = QPushButton("+ Добавить")
        btn_add.clicked.connect(self._on_add_channel)
        lay.addWidget(btn_add)

        btn_del = QPushButton("Удалить")
        btn_del.clicked.connect(self._on_delete_channel)
        lay.addWidget(btn_del)
        return frame

    def _build_right(self) -> QWidget:
        self._right_host = QWidget()
        lay = QVBoxLayout(self._right_host)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)

        # Заголовок канала
        self.lbl_title = QLabel("Выберите TikTok-канал слева или добавьте новый.")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lay.addWidget(self.lbl_title)

        # Вкладки
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        self.tab_stats = self._build_stats_tab()
        self.tab_tags = self._build_tags_tab()
        self.tab_schedule = self._build_schedule_tab()
        self.tab_scripts = self._build_scripts_tab()
        self.tab_published = self._build_published_tab()

        self.tabs.addTab(self.tab_stats, "Статистика")
        self.tabs.addTab(self.tab_tags, "Хэштеги")
        self.tabs.addTab(self.tab_schedule, "График")
        self.tabs.addTab(self.tab_scripts, "Скрипты")
        self.tabs.addTab(self.tab_published, "Опубликовано")

        self.tabs.setEnabled(False)
        return self._right_host

    def _build_stats_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.lbl_stat_yt = QLabel("YouTube-каналов: —")
        self.lbl_stat_videos = QLabel("Всего видео: —")
        self.lbl_stat_clips_ready = QLabel("Готовых клипов: —")
        self.lbl_stat_clips_total = QLabel("Всего клипов: —")
        self.lbl_stat_published = QLabel("Опубликовано: —")
        for l in (self.lbl_stat_yt, self.lbl_stat_videos,
                  self.lbl_stat_clips_ready, self.lbl_stat_clips_total,
                  self.lbl_stat_published):
            lay.addWidget(l)

        lay.addSpacing(8)
        btn_auto = QPushButton("Перейти в Автоматизацию")
        btn_auto.clicked.connect(self._go_automation)
        lay.addWidget(btn_auto)

        lay.addStretch()
        return w

    def _build_tags_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Хэштеги канала (каждый тег на отдельной строке). "
                             "Изменения сохраняются автоматически."))
        self.list_tags = QListWidget()
        self.list_tags.setEditTriggers(QListWidget.EditTrigger.DoubleClicked |
                                       QListWidget.EditTrigger.EditKeyPressed)
        self.list_tags.itemChanged.connect(self._on_tags_changed)
        lay.addWidget(self.list_tags, 1)

        row = QHBoxLayout()
        btn_add_tag = QPushButton("+ Добавить")
        btn_add_tag.clicked.connect(self._on_add_tag)
        btn_del_tag = QPushButton("Удалить")
        btn_del_tag.clicked.connect(self._on_delete_tag)
        btn_gen = QPushButton("Сгенерировать")
        btn_gen.clicked.connect(self._on_generate_tags)
        for b in (btn_add_tag, btn_del_tag, btn_gen):
            row.addWidget(b)
        row.addStretch()
        self.lbl_tags_saved = QLabel("")
        self.lbl_tags_saved.setStyleSheet("color:#6ec06e; font-weight:600;")
        row.addWidget(self.lbl_tags_saved)
        lay.addLayout(row)
        return w

    def _build_schedule_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Времена публикаций (HH:MM):"))
        self.list_schedule = QListWidget()
        lay.addWidget(self.list_schedule, 1)

        row = QHBoxLayout()
        self.time_picker = QTimeEdit()
        self.time_picker.setDisplayFormat("HH:mm")
        self.time_picker.setTime(QTime.currentTime())
        btn_add_time = QPushButton("+ Добавить время")
        btn_add_time.clicked.connect(self._on_add_schedule)
        btn_del_time = QPushButton("Удалить")
        btn_del_time.clicked.connect(self._on_delete_schedule)
        btn_save_time = QPushButton("Сохранить")
        btn_save_time.clicked.connect(self._save_schedule)
        row.addWidget(self.time_picker)
        row.addWidget(btn_add_time)
        row.addWidget(btn_del_time)
        row.addStretch()
        row.addWidget(btn_save_time)
        lay.addLayout(row)
        return w

    def _build_scripts_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.tbl_scripts = QTableWidget(0, 4)
        self.tbl_scripts.setHorizontalHeaderLabels(["Заголовок", "Теги", "Статус", "Создано"])
        self.tbl_scripts.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_scripts.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_scripts.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lay.addWidget(self.tbl_scripts, 1)

        row = QHBoxLayout()
        btn_gen = QPushButton("Сгенерировать до 10 скриптов")
        btn_gen.clicked.connect(self._on_generate_scripts)
        row.addWidget(btn_gen)
        row.addStretch()
        lay.addLayout(row)
        return w

    def _build_published_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.tbl_published = QTableWidget(0, 3)
        self.tbl_published.setHorizontalHeaderLabels(["Заголовок", "Опубликовано", "Ссылка"])
        self.tbl_published.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_published.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.tbl_published, 1)
        return w

    # ── Data loaders ───────────────────────────────────────────────
    def _reload_channels(self):
        self.list_channels.clear()
        for ch in db.list_tiktok_channels():
            label = f"@{ch['handle']}"
            if ch.get("display_name"):
                label = f"{ch['display_name']}  ({label})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, ch["id"])
            self.list_channels.addItem(item)

    def _on_channel_selected(self, current: QListWidgetItem, _prev):
        if not current:
            self._current_id = None
            self.tabs.setEnabled(False)
            self.lbl_title.setText("Выберите TikTok-канал слева или добавьте новый.")
            return
        self._current_id = int(current.data(Qt.ItemDataRole.UserRole))
        self.tabs.setEnabled(True)
        self._refresh_current()
        self.channel_selected.emit(self._current_id)

    def _refresh_current(self):
        if not self._current_id:
            return
        ch = db.get_tiktok_channel(self._current_id)
        if not ch:
            return
        title = ch.get("display_name") or f"@{ch['handle']}"
        self.lbl_title.setText(f"{title}  ·  @{ch['handle']}")

        # Статистика
        yt_channels = db.list_youtube_for_tiktok(self._current_id)
        total_videos = 0
        for c in yt_channels:
            total_videos += db.get_channel_stats(c["id"]).get("total_videos", 0)
        clips = db.list_clips(self._current_id)
        clips_ready = sum(1 for c in clips if c.get("status") == "ready")
        scripts_done = [s for s in db.list_publish_scripts(self._current_id, "done")]

        self.lbl_stat_yt.setText(f"YouTube-каналов: {len(yt_channels)}")
        self.lbl_stat_videos.setText(f"Всего видео: {total_videos}")
        self.lbl_stat_clips_ready.setText(f"Готовых клипов: {clips_ready}")
        self.lbl_stat_clips_total.setText(f"Всего клипов: {len(clips)}")
        self.lbl_stat_published.setText(f"Опубликовано: {len(scripts_done)}")

        # Теги
        self._suppress_autosave = True
        self.list_tags.clear()
        for t in ch.get("hashtags", []):
            item = QListWidgetItem(t)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.list_tags.addItem(item)
        self._suppress_autosave = False

        # Расписание
        self.list_schedule.clear()
        for t in ch.get("schedule", []):
            self.list_schedule.addItem(t)

        # Скрипты (черновики + отмеченные)
        scripts = db.list_publish_scripts(self._current_id)
        self.tbl_scripts.setRowCount(0)
        for s in scripts:
            if s.get("status") == "done":
                continue
            r = self.tbl_scripts.rowCount()
            self.tbl_scripts.insertRow(r)
            self.tbl_scripts.setItem(r, 0, QTableWidgetItem(s.get("title") or "—"))
            self.tbl_scripts.setItem(r, 1, QTableWidgetItem(s.get("hashtags") or ""))
            self.tbl_scripts.setItem(r, 2, QTableWidgetItem(s.get("status") or "draft"))
            self.tbl_scripts.setItem(r, 3, QTableWidgetItem(s.get("created_at") or ""))

        # Опубликованное
        self.tbl_published.setRowCount(0)
        for s in scripts_done:
            r = self.tbl_published.rowCount()
            self.tbl_published.insertRow(r)
            self.tbl_published.setItem(r, 0, QTableWidgetItem(s.get("title") or "—"))
            self.tbl_published.setItem(r, 1, QTableWidgetItem(s.get("scheduled_at") or ""))
            self.tbl_published.setItem(r, 2, QTableWidgetItem("—"))

    # ── Actions ────────────────────────────────────────────────────
    def _on_add_channel(self):
        dlg = AddTikTokDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.data()
        if not data["handle"]:
            QMessageBox.warning(self, "Ошибка", "Введите handle.")
            return
        tid = db.add_tiktok_channel(**data)
        if tid is None:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать канал.")
            return
        self._reload_channels()
        # Выбираем созданный
        for i in range(self.list_channels.count()):
            if int(self.list_channels.item(i).data(Qt.ItemDataRole.UserRole)) == tid:
                self.list_channels.setCurrentRow(i)
                break

    def _on_delete_channel(self):
        if not self._current_id:
            return
        ch = db.get_tiktok_channel(self._current_id)
        if not ch:
            return
        if QMessageBox.question(
            self, "Удаление",
            f"Удалить TikTok-канал @{ch['handle']} со всеми связанными клипами и скриптами?"
        ) != QMessageBox.StandardButton.Yes:
            return
        db.delete_tiktok_channel(self._current_id)
        self._current_id = None
        self._reload_channels()
        self.tabs.setEnabled(False)
        self.lbl_title.setText("Выберите TikTok-канал слева или добавьте новый.")

    # Tags ----------------------------------------------------------
    def _on_tags_changed(self, *_a):
        if self._suppress_autosave or not self._current_id:
            return
        self._tags_save_timer.start(1000)

    def _on_add_tag(self):
        text, ok = QInputDialog.getText(self, "Новый тег", "Тег:")
        if not ok or not text.strip():
            return
        item = QListWidgetItem(text.strip())
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.list_tags.addItem(item)
        self._tags_save_timer.start(1000)

    def _on_delete_tag(self):
        row = self.list_tags.currentRow()
        if row >= 0:
            self.list_tags.takeItem(row)
            self._tags_save_timer.start(300)

    def _on_generate_tags(self):
        if not self._current_id:
            return
        yt_channels = db.list_youtube_for_tiktok(self._current_id)
        sample_titles: list[str] = []
        for c in yt_channels[:5]:
            for v in db.get_videos_by_channel(c["id"])[:5]:
                if v.get("title"):
                    sample_titles.append(v["title"])
        if not sample_titles:
            QMessageBox.information(
                self, "Нет данных",
                "У привязанных YouTube-каналов нет видео — нечего анализировать. "
                "Добавьте YouTube-каналы и скачайте несколько видео."
            )
            return
        current_tags = [self.list_tags.item(i).text()
                        for i in range(self.list_tags.count())]
        generated: list[str] = []
        for t in sample_titles:
            generated.extend(generate_hashtags(t, current_tags, limit=5))
        combined = normalize_hashtags(current_tags + generated)
        self._suppress_autosave = True
        self.list_tags.clear()
        for tag in combined[:20]:
            item = QListWidgetItem(tag)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.list_tags.addItem(item)
        self._suppress_autosave = False
        # Автосохранение сразу после генерации
        self._autosave_tags()

    def _autosave_tags(self):
        if not self._current_id:
            return
        tags = [self.list_tags.item(i).text().strip()
                for i in range(self.list_tags.count())]
        tags = normalize_hashtags(tags)
        if db.set_tiktok_hashtags(self._current_id, tags):
            self._show_saved(self.lbl_tags_saved, f"Сохранено ({len(tags)})")

    # Schedule ------------------------------------------------------
    _TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")

    def _on_add_schedule(self):
        t = self.time_picker.time().toString("HH:mm")
        for i in range(self.list_schedule.count()):
            if self.list_schedule.item(i).text() == t:
                return
        self.list_schedule.addItem(t)

    def _on_delete_schedule(self):
        row = self.list_schedule.currentRow()
        if row >= 0:
            self.list_schedule.takeItem(row)

    def _save_schedule(self):
        if not self._current_id:
            return
        times = []
        for i in range(self.list_schedule.count()):
            t = self.list_schedule.item(i).text().strip()
            if self._TIME_RE.match(t):
                times.append(t)
        times = sorted(set(times))
        db.set_tiktok_schedule(self._current_id, times)
        QMessageBox.information(self, "Сохранено", f"Сохранено {len(times)} слотов.")

    # Scripts -------------------------------------------------------
    def _on_generate_scripts(self):
        if not self._current_id:
            return
        ch = db.get_tiktok_channel(self._current_id)
        if not ch:
            return
        ready = db.list_clips(self._current_id, "ready")
        if not ready:
            QMessageBox.information(
                self, "Нет клипов",
                "Нет готовых клипов. Запустите подготовку в «Автоматизации»."
            )
            return

        existing = db.list_publish_scripts(self._current_id)
        used_clip_ids = {s.get("clip_id") for s in existing if s.get("status") != "done"}
        available = [c for c in ready if c["id"] not in used_clip_ids]
        if not available:
            QMessageBox.information(
                self, "Всё готово",
                "У всех готовых клипов уже есть черновики скриптов."
            )
            return

        base_tags = ch.get("hashtags", [])
        schedule = ch.get("schedule") or []  # ["HH:MM", ...]
        caption_tpl = (db.get_setting("publish_caption_template")
                       or "{title}\n\n{hashtags}")

        # Занятые слоты: уже назначенные scheduled_at у активных скриптов
        busy_slots = set()
        for s in existing:
            if s.get("status") == "done":
                continue
            if s.get("scheduled_at"):
                busy_slots.add(s["scheduled_at"])

        n = min(10, len(available))
        ch_name = ch.get("display_name") or f"@{ch.get('handle','')}"

        for c in available[:n]:
            # Заголовок — из связанного видео, а не имя файла
            src_vid = c.get("source_video_id")
            video = db.get_video(src_vid) if src_vid else None
            title = (video.get("title") if video else None) \
                    or os.path.splitext(
                        os.path.basename(c.get("file_path") or "")
                    )[0] \
                    or "Клип"

            tags = generate_hashtags(title, base_tags, limit=5)
            tags_str = " ".join(tags)

            scheduled_at = _next_free_slot(schedule, busy_slots)
            if scheduled_at:
                busy_slots.add(scheduled_at)

            # Caption по шаблону. Поддерживаемые плейсхолдеры:
            # {title}, {hashtags}, {channel}, {date}
            try:
                caption_text = caption_tpl.format(
                    title=title,
                    hashtags=tags_str,
                    channel=ch_name,
                    date=(scheduled_at or datetime.now().strftime("%Y-%m-%d %H:%M")),
                )
            except Exception:
                caption_text = f"{title}\n\n{tags_str}"

            db.add_publish_script(
                tiktok_id=self._current_id,
                clip_id=c["id"],
                title=title,
                file_path=c.get("file_path"),
                hashtags=tags_str,
                caption=caption_text,
                scheduled_at=scheduled_at,
                status="draft",
            )
        self._refresh_current()
        QMessageBox.information(self, "Готово", f"Создано {n} черновиков.")

    # Navigation ---------------------------------------------------
    def _go_automation(self):
        if self._current_id:
            self.request_navigate_automation.emit(self._current_id)

    def _show_saved(self, label: QLabel, text: str = "Сохранено"):
        label.setText(f"✓ {text}")
        QTimer.singleShot(2000, lambda: label.setText(""))

    def refresh(self):
        """Внешний вызов при переходе на страницу."""
        self._reload_channels()
        if self._current_id:
            self._refresh_current()
