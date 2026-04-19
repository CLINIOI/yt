# pages/channels_page.py — Страница каналов
#
# Компоненты:
#   FetchChannelWorker  — QThread: получает инфо + видео канала, сохраняет в БД
#   AddChannelDialog    — диалог добавления нового канала
#   ChannelCard         — карточка канала в левой панели
#   ChannelsPage        — основной виджет страницы

import os
import re
import json
import logging
import webbrowser
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QLineEdit,
    QSizePolicy, QCheckBox, QSpacerItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QColor, QFont

from db import db
from youtube_service import yt_service, DownloadWorker, DownloadProgress
from download_queue import queue_manager, DownloadQueuePanel

log = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
)


# ─────────────────────────────────────────────────────────────────────
# КОНСТАНТЫ
# ─────────────────────────────────────────────────────────────────────

STATUS_LABEL = {
    "new":         "Новое",
    "queued":      "В очереди",
    "downloading": "Скачивается",
    "downloaded":  "Скачано",
    "processing":  "Обработка",
    "processed":   "Обработано",
    "error":       "Ошибка",
}

STATUS_COLOR = {
    "new":         "#5a5957",
    "queued":      "#e8af34",
    "downloading": "#4f98a3",
    "downloaded":  "#6daa45",
    "processing":  "#da7101",
    "processed":   "#4f98a3",
    "error":       "#dd6974",
}

# Цвета аватаров для карточек каналов (выбирается по индексу)
AVATAR_COLORS = [
    "#1a5f6b", "#3a5a1e", "#6b3a1a", "#3a1a6b",
    "#1a3a6b", "#6b1a3a", "#3a6b1a", "#5a3a1a",
]

PAGE_STYLE = """
/* ── Toolbar ── */
QWidget#ch_toolbar {
    background: #1c1b19;
    border-bottom: 1px solid #2d2c2a;
}
QLabel#page_heading {
    color: #cdccca;
    font-size: 16px;
    font-weight: 600;
}

/* ── Кнопки ── */
QPushButton#btn_primary {
    background: #4f98a3;
    color: #171614;
    border: none;
    border-radius: 7px;
    font-size: 13px;
    font-weight: 600;
    padding: 7px 18px;
}
QPushButton#btn_primary:hover  { background: #227f8b; }
QPushButton#btn_primary:pressed{ background: #1a626b; }

QPushButton#btn_ghost {
    background: transparent;
    color: #797876;
    border: 1px solid #393836;
    border-radius: 7px;
    font-size: 13px;
    padding: 6px 14px;
}
QPushButton#btn_ghost:hover  { background: #22211f; color: #cdccca; }
QPushButton#btn_ghost:pressed{ background: #2d2c2a; }

QPushButton#btn_danger {
    background: transparent;
    color: #797876;
    border: none;
    border-radius: 5px;
    font-size: 16px;
    padding: 2px 6px;
}
QPushButton#btn_danger:hover { color: #dd6974; background: #2d2018; }

/* ── Левая панель ── */
QFrame#left_panel {
    background: #1c1b19;
    border-right: 1px solid #2d2c2a;
}
QLabel#panel_meta {
    color: #5a5957;
    font-size: 11px;
    padding: 0px 16px;
}

/* ── Карточка канала ── */
QFrame#channel_card {
    background: transparent;
    border: none;
    border-radius: 8px;
    margin: 0px 8px;
}
QFrame#channel_card:hover { background: #22211f; }
QFrame#channel_card[selected="true"] { background: #253535; }

QLabel#card_avatar {
    border-radius: 8px;
    font-size: 16px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#card_title {
    color: #cdccca;
    font-size: 13px;
    font-weight: 600;
}
QLabel#card_sub {
    color: #5a5957;
    font-size: 11px;
}
QLabel#card_tiktok {
    color: #5a5957;
    font-size: 10px;
}
QLabel#card_badge {
    background: #4f98a3;
    color: #0a1e20;
    font-size: 10px;
    font-weight: 700;
    border-radius: 8px;
    padding: 1px 6px;
}

/* ── Правая панель / детали канала ── */
QWidget#right_panel { background: #171614; }

QWidget#ch_header { background: #1c1b19; border-bottom: 1px solid #2d2c2a; }
QLabel#ch_title   { color: #cdccca; font-size: 18px; font-weight: 700; }
QLabel#ch_url     { color: #5a5957; font-size: 12px; }
QLabel#ch_stats   { color: #797876; font-size: 12px; }

/* ── Таблица видео ── */
QTableWidget {
    background: #171614;
    border: none;
    gridline-color: #1c1b19;
    color: #cdccca;
    font-size: 13px;
    outline: none;
}
QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #1c1b19;
}
QTableWidget::item:selected {
    background: #253535;
    color: #cdccca;
}
QHeaderView::section {
    background: #1c1b19;
    color: #5a5957;
    border: none;
    border-bottom: 1px solid #2d2c2a;
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

/* ── Диалог ── */
QDialog { background: #1c1b19; }
QLabel#dlg_title { color: #cdccca; font-size: 15px; font-weight: 600; }
QLabel#dlg_hint  { color: #5a5957; font-size: 12px; }
QLabel#dlg_status{ color: #797876; font-size: 12px; }
QLabel#dlg_error { color: #dd6974; font-size: 12px; }

QLineEdit#url_input {
    background: #201f1d;
    border: 1px solid #393836;
    border-radius: 7px;
    color: #cdccca;
    font-size: 13px;
    padding: 9px 12px;
}
QLineEdit#url_input:focus { border-color: #4f98a3; }

/* ── Кнопка просмотра видео ── */
QPushButton#btn_watch {
    background: #253535;
    color: #4f98a3;
    border: 1px solid #393836;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
}
QPushButton#btn_watch:hover { background: #4f98a3; color: #0a1e20; }

/* ── Пустое состояние ── */
QLabel#empty_icon  { color: #3a3937; font-size: 40px; }
QLabel#empty_title { color: #5a5957; font-size: 14px; font-weight: 600; }
QLabel#empty_sub   { color: #3a3937; font-size: 12px; }

/* ── Скролл ── */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #393836;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def fmt_views(n: int) -> str:
    """Форматирует просмотры: 1 234 567 → 1.2M."""
    if not n:
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


class NumericTableItem(QTableWidgetItem):
    """QTableWidgetItem с числовой сортировкой по UserRole."""
    def __lt__(self, other: QTableWidgetItem) -> bool:
        my_val    = self.data(Qt.ItemDataRole.UserRole)
        other_val = other.data(Qt.ItemDataRole.UserRole)
        try:
            return (my_val or 0) < (other_val or 0)
        except TypeError:
            return False


def fmt_duration(seconds: int) -> str:
    if not seconds:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_date(yyyymmdd: str) -> str:
    if not yyyymmdd or len(yyyymmdd) < 8:
        return "—"
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"


def sanitize_dirname(name: str) -> str:
    """Очищает строку для использования как имя папки."""
    return re.sub(r'[\/:*?"<>|]', "_", name).strip()


def load_download_dir(channel_title: str) -> str:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            cfg = json.load(fh)
        base = cfg.get("paths", {}).get("downloads", "./downloads")
    except Exception:
        base = "./downloads"
    base = os.path.join(os.path.dirname(CONFIG_PATH), base)
    return os.path.join(base, sanitize_dirname(channel_title or "unknown"))


# ─────────────────────────────────────────────────────────────────────
# WORKER — фоновое получение инфо + видео канала
# ─────────────────────────────────────────────────────────────────────

class FetchChannelWorker(QThread):
    """
    Получает метаданные канала и список видео, сохраняет в БД.
    Используется как при добавлении нового канала, так и при обновлении.
    """
    status_msg    = pyqtSignal(str)       # текстовый статус для UI
    finished      = pyqtSignal(int, int)  # channel_id, new_videos_count
    error_occurred = pyqtSignal(str)      # сообщение об ошибке

    def __init__(self, url: str, channel_id: Optional[int] = None,
                 video_limit: int = 0,
                 tiktok_handle: str = None,
                 tiktok_url: str = None,
                 parent=None):  # 0 = все видео
        super().__init__(parent)
        self.url           = yt_service.normalize_channel_url(url)
        self.channel_id    = channel_id   # None → новый канал
        self.video_limit   = video_limit
        self.tiktok_handle = tiktok_handle
        self.tiktok_url    = tiktok_url

    def run(self):
        # ── 1. Информация о канале ──
        self.status_msg.emit("Получение информации о канале…")
        ch_info = yt_service.get_channel_info(self.url)
        if not ch_info:
            self.error_occurred.emit("Не удалось получить данные канала. Проверьте URL и подключение к интернету.")
            return

        # ── 2. Сохранить / обновить канал в БД ──
        if self.channel_id is None:
            self.channel_id = db.add_channel(
                url=self.url,
                title=ch_info.title,
                yt_channel_id=ch_info.yt_channel_id,
                thumbnail_url=ch_info.thumbnail_url,
                tiktok_handle=self.tiktok_handle,
                tiktok_url=self.tiktok_url,
            )
        else:
            _upd = dict(
                title=ch_info.title,
                yt_channel_id=ch_info.yt_channel_id,
                thumbnail_url=ch_info.thumbnail_url,
            )
            if self.tiktok_handle is not None:
                _upd["tiktok_handle"] = self.tiktok_handle
            if self.tiktok_url is not None:
                _upd["tiktok_url"] = self.tiktok_url
            db.update_channel(self.channel_id, **_upd)

        # ── 3. Список видео ──
        limit_info = f" (до {self.video_limit})" if self.video_limit > 0 else " (все видео)"
        self.status_msg.emit(f"Загрузка списка видео{limit_info}…")
        videos = yt_service.get_channel_videos(self.url, limit=self.video_limit)

        # ── 4. Добавить только новые видео в БД ──
        new_count = 0
        for v in videos:
            vid_id = db.add_video(
                channel_id=self.channel_id,
                yt_id=v.yt_id,
                title=v.title,
                duration=v.duration,
                thumbnail_url=v.thumbnail_url,
                upload_date=v.upload_date,
                view_count=v.view_count,
            )
            if vid_id is not None:
                new_count += 1

        db.update_channel(self.channel_id, video_count=len(videos))
        db.mark_channel_checked(self.channel_id)

        self.status_msg.emit(f"Готово. Новых видео: {new_count}")
        self.finished.emit(self.channel_id, new_count)


# ─────────────────────────────────────────────────────────────────────
# DIALOG — добавление канала
# ─────────────────────────────────────────────────────────────────────

class AddChannelDialog(QDialog):
    channel_added = pyqtSignal(int)  # channel_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить канал")
        self.setFixedWidth(460)
        self.setModal(True)
        self._worker: Optional[FetchChannelWorker] = None
        self._build_ui()
        self.setStyleSheet(PAGE_STYLE)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 24)
        lay.setSpacing(0)

        title = QLabel("Добавить YouTube-канал")
        title.setObjectName("dlg_title")
        lay.addWidget(title)
        lay.addSpacing(6)

        hint = QLabel("Вставьте ссылку на канал или @handle")
        hint.setObjectName("dlg_hint")
        lay.addWidget(hint)
        lay.addSpacing(18)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("url_input")
        self.url_input.setPlaceholderText("https://youtube.com/@channel  или  @channel")
        self.url_input.returnPressed.connect(self._on_add)
        lay.addWidget(self.url_input)
        lay.addSpacing(14)

        hint_tt = QLabel("TikTok аккаунт (обязательно)")
        hint_tt.setObjectName("dlg_hint")
        lay.addWidget(hint_tt)
        lay.addSpacing(6)

        self.tiktok_handle_input = QLineEdit()
        self.tiktok_handle_input.setObjectName("url_input")
        self.tiktok_handle_input.setPlaceholderText("@username")
        self.tiktok_handle_input.returnPressed.connect(self._on_add)
        lay.addWidget(self.tiktok_handle_input)
        lay.addSpacing(14)

        hint_tt_url = QLabel("Ссылка на TikTok канал (по желанию)")
        hint_tt_url.setObjectName("dlg_hint")
        lay.addWidget(hint_tt_url)
        lay.addSpacing(6)

        self.tiktok_url_input = QLineEdit()
        self.tiktok_url_input.setObjectName("url_input")
        self.tiktok_url_input.setPlaceholderText("https://tiktok.com/@username")
        self.tiktok_url_input.returnPressed.connect(self._on_add)
        lay.addWidget(self.tiktok_url_input)
        lay.addSpacing(10)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("dlg_status")
        lay.addWidget(self.status_lbl)
        lay.addSpacing(20)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setObjectName("btn_ghost")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        btn_row.addStretch()

        self.add_btn = QPushButton("Добавить")
        self.add_btn.setObjectName("btn_primary")
        self.add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(self.add_btn)

        lay.addLayout(btn_row)

    def _on_add(self):
        url = self.url_input.text().strip()
        if not url:
            self._show_status("Введите URL канала", error=True)
            return

        tiktok_handle = self.tiktok_handle_input.text().strip() or None
        tiktok_url    = self.tiktok_url_input.text().strip() or None

        self._set_loading(True)
        self._show_status("Подключение к YouTube…")

        self._worker = FetchChannelWorker(url, tiktok_handle=tiktok_handle, tiktok_url=tiktok_url)
        self._worker.status_msg.connect(lambda m: self._show_status(m))
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.error_occurred.connect(self._on_fetch_error)
        self._worker.start()

    def _on_fetch_done(self, channel_id: int, new_count: int):
        self._set_loading(False)
        self.channel_added.emit(channel_id)
        self.accept()

    def _on_fetch_error(self, msg: str):
        self._set_loading(False)
        self._show_status(msg, error=True)

    def _show_status(self, msg: str, error: bool = False):
        self.status_lbl.setObjectName("dlg_error" if error else "dlg_status")
        self.status_lbl.setStyleSheet(
            "color: #dd6974;" if error else "color: #797876;"
        )
        self.status_lbl.setText(msg)

    def _set_loading(self, loading: bool):
        self.add_btn.setEnabled(not loading)
        self.url_input.setEnabled(not loading)
        self.add_btn.setText("Загружаю…" if loading else "Добавить")


# ─────────────────────────────────────────────────────────────────────
# CHANNEL CARD — карточка в левой панели
# ─────────────────────────────────────────────────────────────────────

class ChannelCard(QFrame):
    clicked  = pyqtSignal(int)   # channel_id
    deleted  = pyqtSignal(int)   # channel_id
    refreshed = pyqtSignal(int)  # channel_id

    def __init__(self, channel: dict, index: int = 0, parent=None):
        super().__init__(parent)
        self.channel_id = channel["id"]
        self.setObjectName("channel_card")
        self.setFixedHeight(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build(channel, index)

    def _build(self, ch: dict, idx: int):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(10)

        # Аватар
        color = AVATAR_COLORS[idx % len(AVATAR_COLORS)]
        letter = (ch.get("title") or "?")[0].upper()
        avatar = QLabel(letter)
        avatar.setObjectName("card_avatar")
        avatar.setFixedSize(38, 38)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(f"background:{color}; border-radius:8px; "
                             f"color:#fff; font-size:16px; font-weight:700;")
        lay.addWidget(avatar)

        # Инфо
        info = QVBoxLayout()
        info.setSpacing(2)

        title_lbl = QLabel(ch.get("title") or ch.get("url", ""))
        title_lbl.setObjectName("card_title")
        title_lbl.setMaximumWidth(130)
        title_lbl.setText(title_lbl.fontMetrics().elidedText(
            title_lbl.text(), Qt.TextElideMode.ElideRight, 130
        ))
        info.addWidget(title_lbl)

        tiktok_handle = ch.get("tiktok_handle") or ""
        if tiktok_handle:
            tt_str = tiktok_handle if tiktok_handle.startswith("@") else f"@{tiktok_handle}"
            tt_lbl = QLabel(tt_str)
            tt_lbl.setObjectName("card_tiktok")
            tt_lbl.setMaximumWidth(130)
            tt_lbl.setText(tt_lbl.fontMetrics().elidedText(
                tt_lbl.text(), Qt.TextElideMode.ElideRight, 130
            ))
            info.addWidget(tt_lbl)

        new_count = db.get_new_videos_count(self.channel_id)
        sub_text = f"{ch.get('video_count', 0)} видео"
        sub_lbl = QLabel(sub_text)
        sub_lbl.setObjectName("card_sub")
        info.addWidget(sub_lbl)

        lay.addLayout(info)
        lay.addStretch()

        # Бейдж «новых»
        if new_count > 0:
            badge = QLabel(str(new_count))
            badge.setObjectName("card_badge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(badge)

        # Кнопка удаления
        del_btn = QPushButton("✕")
        del_btn.setObjectName("btn_danger")
        del_btn.setFixedSize(26, 26)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.channel_id))
        lay.addWidget(del_btn)

    def set_selected(self, selected: bool):
        self.setProperty("selected", "true" if selected else "false")
        self.setStyleSheet(self.styleSheet())  # force re-polish

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.channel_id)
        super().mousePressEvent(event)


# ─────────────────────────────────────────────────────────────────────
# CHANNELS PAGE — основной виджет
# ─────────────────────────────────────────────────────────────────────

class ChannelsPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self._selected_channel_id: Optional[int] = None
        self._channel_cards: dict[int, ChannelCard] = {}
        self._active_workers: list[QThread] = []
        # Подключаем сигналы глобального менеджера очереди
        queue_manager.download_finished.connect(self._on_dl_finished)
        queue_manager.download_failed.connect(self._on_dl_error)

        self._build_ui()
        self.setStyleSheet(PAGE_STYLE)
        self._load_channels()

    # ─────────────────────────────────────────────────
    # Построение UI
    # ─────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #2d2c2a; }")
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 900])

        root.addWidget(splitter)

        self._queue_panel = DownloadQueuePanel(queue_manager)
        root.addWidget(self._queue_panel)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("ch_toolbar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 16, 0)

        heading = QLabel("Каналы")
        heading.setObjectName("page_heading")
        lay.addWidget(heading)
        lay.addStretch()

        refresh_btn = QPushButton("🔄  Обновить все")
        refresh_btn.setObjectName("btn_ghost")
        refresh_btn.clicked.connect(self._refresh_all_channels)
        lay.addWidget(refresh_btn)

        lay.addSpacing(8)

        add_btn = QPushButton("＋  Добавить канал")
        add_btn.setObjectName("btn_primary")
        add_btn.clicked.connect(self._open_add_dialog)
        lay.addWidget(add_btn)

        return bar

    def _build_left_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("left_panel")
        panel.setFixedWidth(258)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(0)

        self._meta_lbl = QLabel("")
        self._meta_lbl.setObjectName("panel_meta")
        lay.addWidget(self._meta_lbl)
        lay.addSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._channels_container = QWidget()
        self._channels_layout = QVBoxLayout(self._channels_container)
        self._channels_layout.setContentsMargins(0, 0, 0, 0)
        self._channels_layout.setSpacing(2)
        self._channels_layout.addStretch()

        scroll.setWidget(self._channels_container)
        lay.addWidget(scroll)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("right_panel")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Шапка канала (скрыта пока канал не выбран)
        self._ch_header = self._build_channel_header()
        lay.addWidget(self._ch_header)

        # Таблица видео
        self._video_table = self._build_video_table()
        lay.addWidget(self._video_table)

        # Пустое состояние
        self._empty_state = self._build_empty_state()
        lay.addWidget(self._empty_state)

        self._ch_header.hide()
        self._video_table.hide()
        self._empty_state.show()

        return panel

    def _build_channel_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("ch_header")
        header.setFixedHeight(90)

        lay = QHBoxLayout(header)
        lay.setContentsMargins(20, 12, 16, 12)
        lay.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(3)

        self._ch_title_lbl = QLabel("—")
        self._ch_title_lbl.setObjectName("ch_title")
        info.addWidget(self._ch_title_lbl)

        self._ch_url_lbl = QLabel("")
        self._ch_url_lbl.setObjectName("ch_url")
        self._ch_url_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._ch_url_lbl.setOpenExternalLinks(True)
        info.addWidget(self._ch_url_lbl)

        self._ch_stats_lbl = QLabel("")
        self._ch_stats_lbl.setObjectName("ch_stats")
        info.addWidget(self._ch_stats_lbl)

        lay.addLayout(info)
        lay.addStretch()

        # Кнопки действий
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        self._refresh_ch_btn = QPushButton("🔄  Обновить")
        self._refresh_ch_btn.setObjectName("btn_ghost")
        self._refresh_ch_btn.clicked.connect(self._refresh_current_channel)
        btn_col.addWidget(self._refresh_ch_btn)

        self._download_btn = QPushButton("⬇  Скачать выбранные")
        self._download_btn.setObjectName("btn_primary")
        self._download_btn.clicked.connect(self._download_selected)
        btn_col.addWidget(self._download_btn)

        lay.addLayout(btn_col)
        return header

    def _build_video_table(self) -> QTableWidget:
        table = QTableWidget()
        # Колонки: 0=☐  1=НАЗВАНИЕ  2=ДЛИНА  3=ПРОСМОТРЫ  4=ДАТА  5=СТАТУС  6=▶
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(
            ["☐", "НАЗВАНИЕ", "ДЛИНА", "ПРОСМОТРЫ", "ДАТА", "СТАТУС", "▶"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().hide()
        table.setAlternatingRowColors(False)
        table.setWordWrap(False)

        # Сортировка по клику на заголовок (клик — ▲, повторный — ▼)
        table.setSortingEnabled(True)
        hdr = table.horizontalHeader()
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(4, Qt.SortOrder.DescendingOrder)  # по умолчанию: новые первые
        hdr.sectionClicked.connect(self._on_sort_clicked)

        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)

        table.setColumnWidth(0, 36)
        table.setColumnWidth(2, 68)
        table.setColumnWidth(3, 88)
        table.setColumnWidth(4, 96)
        table.setColumnWidth(5, 108)
        table.setColumnWidth(6, 86)
        table.verticalHeader().setDefaultSectionSize(36)

        return table

    def _on_sort_clicked(self, col: int):
        """Запрещаем сортировку по колонке с чекбоксами."""
        if col == 0:
            # Сброс к дате (новые сверху)
            self._video_table.horizontalHeader().setSortIndicator(
                4, Qt.SortOrder.DescendingOrder)
            self._video_table.sortByColumn(4, Qt.SortOrder.DescendingOrder)

    def _build_empty_state(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)

        ico = QLabel("📺")
        ico.setObjectName("empty_icon")
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ico)

        t = QLabel("Выберите канал")
        t.setObjectName("empty_title")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)

        s = QLabel("или добавьте новый через «＋ Добавить канал»")
        s.setObjectName("empty_sub")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(s)

        return w

    # ─────────────────────────────────────────────────
    # Загрузка каналов из БД
    # ─────────────────────────────────────────────────

    def _load_channels(self):
        """Очищает и перестраивает список каналов из БД."""
        # Удаляем старые карточки
        for card in self._channel_cards.values():
            card.deleteLater()
        self._channel_cards.clear()

        channels = db.get_all_channels()

        # Убираем старый stretch, добавим заново
        while self._channels_layout.count():
            item = self._channels_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, ch in enumerate(channels):
            card = ChannelCard(ch, index=idx)
            card.clicked.connect(self._on_channel_selected)
            card.deleted.connect(self._on_channel_deleted)
            self._channel_cards[ch["id"]] = card
            self._channels_layout.addWidget(card)

        self._channels_layout.addStretch()

        total = len(channels)
        new_total = sum(db.get_new_videos_count(c["id"]) for c in channels)
        self._meta_lbl.setText(
            f"{total} {'канал' if total == 1 else 'каналов'}  ·  "
            f"{new_total} новых видео"
        )

    # ─────────────────────────────────────────────────
    # Выбор канала → загрузка видео
    # ─────────────────────────────────────────────────

    def _on_channel_selected(self, channel_id: int):
        # Снимаем выделение с предыдущего
        if self._selected_channel_id and self._selected_channel_id in self._channel_cards:
            self._channel_cards[self._selected_channel_id].set_selected(False)

        self._selected_channel_id = channel_id

        if channel_id in self._channel_cards:
            self._channel_cards[channel_id].set_selected(True)

        ch = db.get_channel(channel_id)
        if not ch:
            return

        # Обновляем шапку
        self._ch_title_lbl.setText(ch.get("title") or "—")

        yt_url     = ch.get("url", "")
        tt_handle  = ch.get("tiktok_handle") or ""
        tt_url     = ch.get("tiktok_url") or ""
        if not tt_handle.startswith("@") and tt_handle:
            tt_handle = f"@{tt_handle}"

        yt_link = f'<a href="{yt_url}" style="color:#4f98a3; text-decoration:none;">{yt_url}</a>'
        if tt_handle and tt_url:
            tt_link = f'<a href="{tt_url}" style="color:#ff6b6b; text-decoration:none;">{tt_handle}</a>'
            combined = f'{yt_link} <span style="color:#393836;"> / </span> {tt_link}'
        elif tt_handle:
            combined = f'{yt_link} <span style="color:#393836;"> / </span> <span style="color:#ff6b6b;">{tt_handle}</span>'
        else:
            combined = yt_link
        self._ch_url_lbl.setText(combined)

        stats = db.get_channel_stats(channel_id)
        by_s  = stats.get("by_status", {})
        self._ch_stats_lbl.setText(
            f"Всего: {stats['total_videos']}  ·  "
            f"Новых: {by_s.get('new', 0)}  ·  "
            f"Скачано: {by_s.get('downloaded', 0)}"
        )

        self._load_videos(channel_id)

        self._ch_header.show()
        self._video_table.show()
        self._empty_state.hide()

    def _load_videos(self, channel_id: int):
        """Заполняет таблицу видео из БД (без ограничения количества)."""
        videos = db.get_videos_by_channel(channel_id)
        table  = self._video_table

        # Отключаем сортировку на время заполнения — быстрее
        table.setSortingEnabled(False)
        table.setRowCount(0)

        for v in videos:
            row = table.rowCount()
            table.insertRow(row)

            # 0 — Чекбокс (не сортируется)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, v["id"])
            table.setItem(row, 0, chk)

            # 1 — Название
            name_item = QTableWidgetItem(v.get("title", ""))
            name_item.setToolTip(v.get("title", ""))
            table.setItem(row, 1, name_item)

            # 2 — Длина (сортировка по секундам)
            dur_item = NumericTableItem(fmt_duration(v.get("duration", 0)))
            dur_item.setData(Qt.ItemDataRole.UserRole, v.get("duration") or 0)
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, dur_item)

            # 3 — Просмотры (сортировка по числу)
            views = v.get("view_count") or 0
            views_item = NumericTableItem(fmt_views(views))
            views_item.setData(Qt.ItemDataRole.UserRole, views)
            views_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 3, views_item)

            # 4 — Дата публикации (YYYYMMDD сортируется как строка = хронологически)
            raw_date = v.get("upload_date", "") or ""
            date_item = QTableWidgetItem(fmt_date(raw_date))
            date_item.setData(Qt.ItemDataRole.UserRole, raw_date)
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 4, date_item)

            # 5 — Статус
            status      = v.get("status", "new")
            status_item = QTableWidgetItem(STATUS_LABEL.get(status, status))
            status_item.setForeground(QColor(STATUS_COLOR.get(status, "#797876")))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 5, status_item)

            # 6 — Кнопка "▶ Видео" → открывает YouTube в браузере
            yt_id = v.get("yt_id", "")
            if yt_id:
                watch_btn = QPushButton("▶ Видео")
                watch_btn.setObjectName("btn_watch")
                watch_url = f"https://www.youtube.com/watch?v={yt_id}"
                watch_btn.clicked.connect(
                    lambda _checked, u=watch_url: webbrowser.open(u)
                )
                table.setCellWidget(row, 6, watch_btn)

        # Включаем сортировку и применяем текущий индикатор
        table.setSortingEnabled(True)
        hdr = table.horizontalHeader()
        table.sortByColumn(
            hdr.sortIndicatorSection(),
            hdr.sortIndicatorOrder(),
        )

    # ─────────────────────────────────────────────────
    # Добавление канала
    # ─────────────────────────────────────────────────

    def _open_add_dialog(self):
        dlg = AddChannelDialog(self)
        dlg.channel_added.connect(self._on_channel_added)
        dlg.exec()

    def _on_channel_added(self, channel_id: int):
        self._load_channels()
        # Автовыбор добавленного канала
        QTimer.singleShot(100, lambda: self._on_channel_selected(channel_id))

    # ─────────────────────────────────────────────────
    # Удаление канала
    # ─────────────────────────────────────────────────

    def _on_channel_deleted(self, channel_id: int):
        db.delete_channel(channel_id)
        if self._selected_channel_id == channel_id:
            self._selected_channel_id = None
            self._ch_header.hide()
            self._video_table.hide()
            self._empty_state.show()
        self._load_channels()

    # ─────────────────────────────────────────────────
    # Обновление каналов
    # ─────────────────────────────────────────────────

    def _refresh_current_channel(self):
        if not self._selected_channel_id:
            return
        ch = db.get_channel(self._selected_channel_id)
        if not ch:
            return
        self._run_fetch(ch["url"], self._selected_channel_id)

    def _refresh_all_channels(self):
        for ch in db.get_all_channels():
            self._run_fetch(ch["url"], ch["id"])

    def _run_fetch(self, url: str, channel_id: int):
        worker = FetchChannelWorker(url, channel_id=channel_id)
        worker.status_msg.connect(lambda m: log.debug("Fetch: %s", m))
        worker.finished.connect(self._on_fetch_finished)
        worker.error_occurred.connect(lambda e: log.error("Fetch error: %s", e))
        self._active_workers.append(worker)
        worker.start()

    def _on_fetch_finished(self, channel_id: int, new_count: int):
        self._load_channels()
        if self._selected_channel_id == channel_id:
            self._on_channel_selected(channel_id)
        # Убираем завершённый worker из списка
        self._active_workers = [w for w in self._active_workers if w.isRunning()]

    # ─────────────────────────────────────────────────
    # Скачивание выбранных видео
    # ─────────────────────────────────────────────────

    def _download_selected(self):
        if not self._selected_channel_id:
            return

        ch = db.get_channel(self._selected_channel_id)
        if not ch:
            return

        output_dir = load_download_dir(ch.get("title", "unknown"))
        table  = self._video_table
        queued = 0

        for row in range(table.rowCount()):
            chk = table.item(row, 0)
            if not chk or chk.checkState() == Qt.CheckState.Unchecked:
                continue

            video_id = chk.data(Qt.ItemDataRole.UserRole)
            video    = db.get_video(video_id)
            if not video or video["status"] in ("queued", "downloading", "downloaded"):
                continue

            queue_manager.add(
                video_id=video_id,
                title=video.get("title", f"video_{video_id}"),
                yt_id=video["yt_id"],
                output_dir=output_dir,
                quality="1080p",
            )
            queued += 1

        if queued:
            self._load_videos(self._selected_channel_id)

    def _on_dl_finished(self, video_id: int, file_path: str):
        """Вызывается менеджером очереди после успешного скачивания."""
        if self._selected_channel_id:
            self._load_videos(self._selected_channel_id)
        self._load_channels()

    def _on_dl_error(self, video_id: int, error_msg: str):
        """Вызывается менеджером очереди при ошибке."""
        if self._selected_channel_id:
            self._load_videos(self._selected_channel_id)
