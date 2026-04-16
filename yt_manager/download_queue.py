# download_queue.py — Очередь загрузок: менеджер + UI-панель
#
# DownloadQueueManager  — QObject, управляет воркерами, лимит параллельности
# DownloadItemWidget    — карточка одной загрузки (прогресс-бар, скорость, отмена)
# DownloadQueuePanel    — коллапсируемая панель внизу страницы
# queue_manager         — глобальный инстанс, импортируется из других модулей

import os
import json
import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal

from db import db
from youtube_service import DownloadWorker

log = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config.json"
)

PANEL_EXPANDED_HEIGHT = 230
PANEL_HEADER_HEIGHT   = 40

QUEUE_STYLE = """
/* ── Панель ── */
QFrame#queue_panel {
    background: #1c1b19;
    border-top: 1px solid #2d2c2a;
}
QFrame#queue_header {
    background: #1c1b19;
}

QLabel#q_label {
    color: #5a5957;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
QLabel#q_counts {
    color: #4f98a3;
    font-size: 12px;
    font-weight: 700;
}
QLabel#q_empty {
    color: #3a3937;
    font-size: 12px;
}

QPushButton#q_cancel_all {
    background: transparent;
    color: #5a5957;
    border: 1px solid #393836;
    border-radius: 5px;
    font-size: 11px;
    padding: 3px 10px;
}
QPushButton#q_cancel_all:hover { color: #dd6974; border-color: #dd6974; }

QPushButton#q_toggle {
    background: transparent;
    color: #5a5957;
    border: none;
    font-size: 16px;
    padding: 2px 8px;
}
QPushButton#q_toggle:hover { color: #cdccca; }

/* ── Скролл ── */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: transparent; width: 5px;
}
QScrollBar::handle:vertical {
    background: #393836; border-radius: 2px; min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Карточка загрузки ── */
QFrame#dl_item {
    background: #201f1d;
    border-radius: 8px;
    border: 1px solid #2d2c2a;
}

QLabel#dl_icon    { font-size: 14px; }
QLabel#dl_title   { color: #cdccca; font-size: 12px; font-weight: 600; }
QLabel#dl_sub     { color: #5a5957; font-size: 11px; }
QLabel#dl_percent { color: #4f98a3; font-size: 11px; font-weight: 700; min-width: 36px; }
QLabel#dl_speed   { color: #5a5957; font-size: 11px; min-width: 80px; }
QLabel#dl_eta     { color: #5a5957; font-size: 11px; min-width: 50px; }

QPushButton#dl_cancel {
    background: transparent; border: none;
    color: #3a3937; font-size: 15px;
    border-radius: 4px; padding: 1px 5px;
}
QPushButton#dl_cancel:hover { color: #dd6974; background: #2d2018; }

QProgressBar#dl_bar {
    background: #2d2c2a;
    border: none;
    border-radius: 3px;
    max-height: 4px;
    min-height: 4px;
    text-align: center;
}
QProgressBar#dl_bar::chunk {
    background: #4f98a3;
    border-radius: 3px;
}
QProgressBar#dl_bar[done="true"]::chunk  { background: #6daa45; }
QProgressBar#dl_bar[error="true"]::chunk { background: #dd6974; }
QProgressBar#dl_bar[merge="true"]::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #4f98a3, stop:0.5 #6daa45, stop:1 #4f98a3);
}
"""

STATUS_ICON = {
    "queued":      "⏸",
    "downloading": "⬇",
    "merging":     "🔗",
    "downloaded":  "✓",
    "error":       "✗",
}
STATUS_COLOR = {
    "queued":      "#5a5957",
    "downloading": "#4f98a3",
    "merging":     "#e8af34",
    "downloaded":  "#6daa45",
    "error":       "#dd6974",
}


# ─────────────────────────────────────────────────────────────────────
# МЕНЕДЖЕР ОЧЕРЕДИ
# ─────────────────────────────────────────────────────────────────────

class DownloadQueueManager(QObject):
    """
    Управляет очередью загрузок.
    Запускает не более max_concurrent воркеров одновременно.
    При завершении одного автоматически стартует следующий.
    """

    item_queued       = pyqtSignal(int, str)        # video_id, title
    download_started  = pyqtSignal(int)             # video_id
    download_finished = pyqtSignal(int, str)        # video_id, file_path
    download_failed   = pyqtSignal(int, str)        # video_id, error_msg
    progress_updated  = pyqtSignal(int, float, str, str)  # video_id, %, speed, eta
    status_changed    = pyqtSignal(int, str)        # video_id, status
    queue_changed     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_concurrent = self._load_max_concurrent()
        self._pending: list[dict] = []              # {"video_id", "title", "yt_id", "output_dir", "quality"}
        self._active:  dict[int, DownloadWorker] = {}  # video_id → worker

    @staticmethod
    def _load_max_concurrent() -> int:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as fh:
                cfg = json.load(fh)
            return int(cfg.get("download", {}).get("max_concurrent", 2))
        except Exception:
            return 2

    # ── Публичный API ─────────────────────────────────────────────────

    def add(self, video_id: int, title: str, yt_id: str,
            output_dir: str, quality: str = "1080p"):
        """Добавить видео в очередь. Если уже есть — игнорирует."""
        if video_id in self._active:
            return
        if any(p["video_id"] == video_id for p in self._pending):
            return

        task = {"video_id": video_id, "title": title,
                "yt_id": yt_id, "output_dir": output_dir, "quality": quality}
        self._pending.append(task)
        self.item_queued.emit(video_id, title)
        self.queue_changed.emit()
        self._try_start_next()

    def cancel(self, video_id: int):
        """Отменить загрузку (из очереди или активную)."""
        self._pending = [p for p in self._pending if p["video_id"] != video_id]
        if video_id in self._active:
            self._active[video_id].cancel()
        self.queue_changed.emit()

    def cancel_all(self):
        """Отменить все загрузки."""
        for worker in list(self._active.values()):
            worker.cancel()
        self._pending.clear()
        self.queue_changed.emit()

    def get_all_tasks(self) -> list[dict]:
        """Возвращает все задачи (активные + в ожидании) для отображения."""
        result = []
        for vid_id in self._active:
            t = next((p for p in self._pending if p["video_id"] == vid_id), None)
            result.append({
                "video_id": vid_id,
                "title": t["title"] if t else f"video_{vid_id}",
                "status": "downloading"
            })
        for task in self._pending:
            if task["video_id"] not in self._active:
                result.append({**task, "status": "queued"})
        return result

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def is_active(self, video_id: int) -> bool:
        return video_id in self._active

    def is_pending(self, video_id: int) -> bool:
        return any(p["video_id"] == video_id for p in self._pending)

    # ── Внутренняя логика ─────────────────────────────────────────────

    def _try_start_next(self):
        """Запускает следующие задачи пока не достигнут лимит."""
        while len(self._active) < self.max_concurrent and self._pending:
            # Берём первую задачу из pending, которая ещё не active
            task = next((p for p in self._pending
                         if p["video_id"] not in self._active), None)
            if task is None:
                break
            self._pending.remove(task)
            self._start_worker(task)

    def _start_worker(self, task: dict):
        vid_id = task["video_id"]
        worker = DownloadWorker(
            video_id=vid_id,
            yt_id=task["yt_id"],
            output_dir=task["output_dir"],
            quality=task["quality"],
        )
        worker.progress_updated.connect(
            lambda p, s, e, v=vid_id: self.progress_updated.emit(v, p, s, e)
        )
        worker.status_changed.connect(
            lambda st, v=vid_id: self.status_changed.emit(v, st)
        )
        worker.download_finished.connect(self._on_finished)
        worker.download_error.connect(self._on_error)

        self._active[vid_id] = worker
        db.update_video_status(vid_id, "downloading")
        self.download_started.emit(vid_id)
        self.queue_changed.emit()
        worker.start()

    def _on_finished(self, video_id: int, file_path: str):
        self._active.pop(video_id, None)
        db.update_video_status(video_id, "downloaded", file_path=file_path)
        self.download_finished.emit(video_id, file_path)
        self.queue_changed.emit()
        self._try_start_next()

    def _on_error(self, video_id: int, error_msg: str):
        self._active.pop(video_id, None)
        db.update_video_status(video_id, "error", error_msg=error_msg)
        self.download_failed.emit(video_id, error_msg)
        self.queue_changed.emit()
        self._try_start_next()


# ─────────────────────────────────────────────────────────────────────
# КАРТОЧКА ОДНОЙ ЗАГРУЗКИ
# ─────────────────────────────────────────────────────────────────────

class DownloadItemWidget(QFrame):

    cancel_requested = pyqtSignal(int)  # video_id

    def __init__(self, video_id: int, title: str,
                 status: str = "queued", parent=None):
        super().__init__(parent)
        self.video_id = video_id
        self.setObjectName("dl_item")
        self.setFixedHeight(68)
        self._build(title, status)

    def _build(self, title: str, initial_status: str):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(4)

        # ── Верхняя строка ──
        top = QHBoxLayout()
        top.setSpacing(8)

        self._icon_lbl = QLabel(STATUS_ICON.get(initial_status, "⏸"))
        self._icon_lbl.setObjectName("dl_icon")
        self._icon_lbl.setFixedWidth(16)
        top.addWidget(self._icon_lbl)

        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("dl_title")
        self._title_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        top.addWidget(self._title_lbl)

        self._speed_lbl = QLabel("")
        self._speed_lbl.setObjectName("dl_speed")
        self._speed_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        top.addWidget(self._speed_lbl)

        cancel_btn = QPushButton("✕")
        cancel_btn.setObjectName("dl_cancel")
        cancel_btn.setFixedSize(22, 22)
        cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.video_id))
        top.addWidget(cancel_btn)

        lay.addLayout(top)

        # ── Нижняя строка ──
        bot = QHBoxLayout()
        bot.setSpacing(8)

        self._bar = QProgressBar()
        self._bar.setObjectName("dl_bar")
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        bot.addWidget(self._bar, stretch=1)

        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setObjectName("dl_percent")
        self._pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        bot.addWidget(self._pct_lbl)

        self._eta_lbl = QLabel("")
        self._eta_lbl.setObjectName("dl_eta")
        self._eta_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        bot.addWidget(self._eta_lbl)

        lay.addLayout(bot)

        # Применяем начальный статус
        self.set_status(initial_status)

    # ── Публичные методы обновления ───────────────────────────────────

    def update_progress(self, percent: float, speed: str, eta: str):
        self._bar.setValue(int(percent))
        self._pct_lbl.setText(f"{percent:.0f}%")
        self._speed_lbl.setText(speed)
        self._eta_lbl.setText(eta)

    def set_status(self, status: str):
        icon  = STATUS_ICON.get(status,  "⏸")
        color = STATUS_COLOR.get(status, "#5a5957")

        self._icon_lbl.setText(icon)
        self._icon_lbl.setStyleSheet(f"color: {color};")

        if status == "queued":
            self._pct_lbl.setText("В очереди")
            self._pct_lbl.setStyleSheet("color: #5a5957;")
            self._bar.setValue(0)
        elif status == "merging":
            self._pct_lbl.setText("Склейка…")
            self._pct_lbl.setStyleSheet("color: #e8af34;")
            self._bar.setProperty("merge", "true")
            self._bar.setStyleSheet(self._bar.styleSheet())
        elif status == "downloaded":
            self._pct_lbl.setText("Готово")
            self._pct_lbl.setStyleSheet(f"color: {color};")
            self._bar.setValue(100)
            self._bar.setProperty("done", "true")
            self._bar.setStyleSheet(self._bar.styleSheet())
        elif status == "error":
            self._pct_lbl.setText("Ошибка")
            self._pct_lbl.setStyleSheet(f"color: {color};")
            self._bar.setProperty("error", "true")
            self._bar.setStyleSheet(self._bar.styleSheet())

    def truncate_title(self, max_px: int = 260):
        fm = self._title_lbl.fontMetrics()
        self._title_lbl.setText(
            fm.elidedText(self._title_lbl.text(),
                          Qt.TextElideMode.ElideRight, max_px)
        )


# ─────────────────────────────────────────────────────────────────────
# ПАНЕЛЬ ОЧЕРЕДИ
# ─────────────────────────────────────────────────────────────────────

class DownloadQueuePanel(QFrame):
    """
    Коллапсируемая панель внизу страницы.
    Показывает активные загрузки и очередь с прогрес-барами.
    """

    def __init__(self, manager: DownloadQueueManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setObjectName("queue_panel")
        self._expanded = True
        self._items: dict[int, DownloadItemWidget] = {}

        self._build_ui()
        self.setStyleSheet(QUEUE_STYLE)
        self._update_header()

        # Подключаем сигналы менеджера
        manager.item_queued.connect(self._on_item_queued)
        manager.download_started.connect(self._on_download_started)
        manager.progress_updated.connect(self._on_progress)
        manager.status_changed.connect(self._on_status)
        manager.download_finished.connect(self._on_finished)
        manager.download_failed.connect(self._on_failed)
        manager.queue_changed.connect(self._update_header)

    # ── Построение UI ─────────────────────────────────────────────────

    def _build_ui(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self._root.addWidget(self._build_header())
        self._root.addWidget(self._build_body())

        self.setFixedHeight(PANEL_HEADER_HEIGHT)

    def _build_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setObjectName("queue_header")
        hdr.setFixedHeight(PANEL_HEADER_HEIGHT)

        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(8)

        lay.addWidget(_label("⬇  ЗАГРУЗКИ", "q_label"))

        self._counts_lbl = _label("", "q_counts")
        lay.addWidget(self._counts_lbl)
        lay.addStretch()

        self._cancel_all_btn = QPushButton("Отменить все")
        self._cancel_all_btn.setObjectName("q_cancel_all")
        self._cancel_all_btn.clicked.connect(self.manager.cancel_all)
        self._cancel_all_btn.hide()
        lay.addWidget(self._cancel_all_btn)

        self._toggle_btn = QPushButton("▾")
        self._toggle_btn.setObjectName("q_toggle")
        self._toggle_btn.setFixedSize(28, 28)
        self._toggle_btn.clicked.connect(self._toggle)
        lay.addWidget(self._toggle_btn)

        return hdr

    def _build_body(self) -> QScrollArea:
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        container = QWidget()
        self._items_layout = QVBoxLayout(container)
        self._items_layout.setContentsMargins(12, 6, 12, 8)
        self._items_layout.setSpacing(4)

        self._empty_lbl = _label("Нет активных загрузок", "q_empty")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._items_layout.addWidget(self._empty_lbl)
        self._items_layout.addStretch()

        self._scroll.setWidget(container)
        return self._scroll

    # ── Управление видимостью ─────────────────────────────────────────

    def _toggle(self):
        self._expanded = not self._expanded
        self._toggle_btn.setText("▾" if self._expanded else "▸")
        if self._expanded:
            self.setFixedHeight(PANEL_EXPANDED_HEIGHT)
            self._scroll.show()
        else:
            self.setFixedHeight(PANEL_HEADER_HEIGHT)
            self._scroll.hide()

    def _show_panel(self):
        if not self._expanded:
            self._toggle()

    # ── Обновление заголовка ──────────────────────────────────────────

    def _update_header(self):
        a = self.manager.active_count
        p = self.manager.pending_count

        if a == 0 and p == 0:
            self._counts_lbl.setText("")
            self._cancel_all_btn.hide()
            self._empty_lbl.show()
        else:
            parts = []
            if a:
                parts.append(f"{a} активных")
            if p:
                parts.append(f"{p} в очереди")
            self._counts_lbl.setText("  ·  ".join(parts))
            self._cancel_all_btn.show()
            self._empty_lbl.hide()

    # ── Обработчики сигналов менеджера ───────────────────────────────

    def _on_item_queued(self, video_id: int, title: str):
        if video_id not in self._items:
            widget = DownloadItemWidget(video_id, title, status="queued")
            widget.cancel_requested.connect(self.manager.cancel)
            self._items[video_id] = widget
            # Вставляем перед stretch
            idx = self._items_layout.count() - 1
            self._items_layout.insertWidget(idx, widget)
        self._show_panel()

    def _on_download_started(self, video_id: int):
        if video_id in self._items:
            self._items[video_id].set_status("downloading")

    def _on_progress(self, video_id: int, percent: float,
                     speed: str, eta: str):
        if video_id in self._items:
            self._items[video_id].update_progress(percent, speed, eta)

    def _on_status(self, video_id: int, status: str):
        if video_id in self._items:
            self._items[video_id].set_status(status)

    def _on_finished(self, video_id: int, _path: str):
        if video_id in self._items:
            self._items[video_id].set_status("downloaded")
            # Убираем карточку через 3 секунды
            QTimer.singleShot(3000, lambda v=video_id: self._remove_item(v))

    def _on_failed(self, video_id: int, _msg: str):
        if video_id in self._items:
            self._items[video_id].set_status("error")
            QTimer.singleShot(5000, lambda v=video_id: self._remove_item(v))

    def _remove_item(self, video_id: int):
        widget = self._items.pop(video_id, None)
        if widget:
            self._items_layout.removeWidget(widget)
            widget.deleteLater()


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _label(text: str, obj_name: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(obj_name)
    return lbl


# ─────────────────────────────────────────────────────────────────────
# ГЛОБАЛЬНЫЙ ИНСТАНС
# ─────────────────────────────────────────────────────────────────────

queue_manager = DownloadQueueManager()
