# ui_main.py — Главное окно приложения
#
# Содержит:
#   • Боковой навбар с иконками и статус-индикаторами
#   • QStackedWidget со всеми пятью страницами
#   • Полную маршрутизацию сигналов между страницами
#   • Сохранение/восстановление геометрии окна
#   • Статусную строку (активные загрузки / обработка)

import os
import json
import shutil

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame,
    QButtonGroup, QStatusBar,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent

from pages.channels_page   import ChannelsPage
from pages.processing_page import ProcessingPage
from pages.folders_page    import FoldersPage
from pages.stats_page      import StatsPage
from pages.presets_page    import PresetsPage

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# ──────────────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────────────

DARK_THEME = """
QMainWindow, QWidget#central { background: #171614; }

/* ── SIDEBAR ── */
QFrame#sidebar { background: #1c1b19; border-right: 1px solid #2d2c2a; }

QLabel#app_logo {
    color: #4f98a3; font-size: 20px; font-weight: 700;
    letter-spacing: 1px; padding: 0 20px;
}
QLabel#app_sub  { color: #5a5957; font-size: 10px; padding: 0 20px; }

QFrame#sidebar_div {
    background: #2d2c2a; border: none;
    max-height: 1px; margin: 4px 16px;
}

QLabel#nav_section {
    color: #5a5957; font-size: 10px;
    letter-spacing: 1.5px; padding: 0 20px;
}

QPushButton#nav_btn {
    background: transparent; border: none; border-radius: 8px;
    color: #797876; font-size: 13px;
    text-align: left; padding: 10px 16px;
    margin: 1px 8px;
}
QPushButton#nav_btn:hover   { background: #22211f; color: #cdccca; }
QPushButton#nav_btn:checked { background: #253535; color: #4f98a3; font-weight: 600; }

/* ── СТАТУСНАЯ ПАНЕЛЬ САЙДБАРА ── */
QFrame#sidebar_status { background: #171614; border-top: 1px solid #2d2c2a; }
QLabel#status_tool    { color: #3a3937; font-size: 11px; }
QLabel#status_tool[ok="true"]  { color: #437a22; }
QLabel#status_tool[ok="false"] { color: #964219; }

/* Счётчик загрузок */
QLabel#dl_counter { color: #5a5957; font-size: 11px; padding: 0 20px; }
QLabel#dl_counter[active="true"] { color: #4f98a3; }

QLabel#version_label { color: #3a3937; font-size: 10px; padding: 0 20px; }

/* ── STATUSBAR ── */
QStatusBar { background: #1c1b19; color: #5a5957; font-size: 11px;
             border-top: 1px solid #2d2c2a; }
QStatusBar::item { border: none; }
"""

NAV_ITEMS = [
    ("📺", "  Каналы",     0),
    ("⚙️", "  Обработка",  1),
    ("📁", "  Папки",      2),
    ("📊", "  Статистика", 3),
    ("🎛", "  Пресеты",    4),
]

# Страницы, которые обновляются при каждом переходе
REFRESH_ON_VISIT: set[int] = {2, 3}   # FoldersPage, StatsPage


# ──────────────────────────────────────────────────────────────────────
# Главное окно
# ──────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, config: dict = None):
        super().__init__()
        self.config = config or {}
        self._env   = self._probe_env()

        self.setWindowTitle("YT Manager")
        self.setMinimumSize(960, 620)

        self._build_ui()
        self._connect_signals()
        self.setStyleSheet(DARK_THEME)
        self._restore_geometry()

        # Открываем первую страницу
        self._nav_buttons[0].setChecked(True)
        self.stack.setCurrentIndex(0)

        # Обновляем счётчик загрузок каждые 3 секунды
        self._dl_timer = QTimer(self)
        self._dl_timer.setInterval(3000)
        self._dl_timer.timeout.connect(self._refresh_dl_counter)
        self._dl_timer.start()

    # ── Окружение ─────────────────────────────────────────────────────
    def _probe_env(self) -> dict:
        return {
            "ffmpeg":  bool(shutil.which("ffmpeg")),
            "yt_dlp":  bool(shutil.which("yt-dlp")) or self._has_ytdlp_module(),
        }

    @staticmethod
    def _has_ytdlp_module() -> bool:
        try:
            import yt_dlp  # noqa: F401
            return True
        except ImportError:
            return False

    # ── Построение UI ─────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_stack(), stretch=1)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self._statusbar = sb

    # ── САЙДБАР ───────────────────────────────────────────────────────
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Логотип
        lay.addSpacing(24)
        logo = QLabel("YT Manager")
        logo.setObjectName("app_logo")
        lay.addWidget(logo)
        lay.addSpacing(3)
        sub = QLabel("YouTube · Video Tool")
        sub.setObjectName("app_sub")
        lay.addWidget(sub)
        lay.addSpacing(18)
        lay.addWidget(self._hdiv())
        lay.addSpacing(14)

        # Навигация
        nav_lbl = QLabel("МЕНЮ")
        nav_lbl.setObjectName("nav_section")
        lay.addWidget(nav_lbl)
        lay.addSpacing(6)

        self._btn_group   = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._nav_buttons = []

        for icon, label, idx in NAV_ITEMS:
            btn = QPushButton(f"  {icon}{label}")
            btn.setObjectName("nav_btn")
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, i=idx: self._navigate(i))
            self._btn_group.addButton(btn, idx)
            self._nav_buttons.append(btn)
            lay.addWidget(btn)
            lay.addSpacing(2)

        lay.addStretch()

        # Счётчик загрузок
        self._dl_counter = QLabel("Загрузок: 0")
        self._dl_counter.setObjectName("dl_counter")
        self._dl_counter.setProperty("active", "false")
        lay.addWidget(self._dl_counter)
        lay.addSpacing(6)

        # Статус инструментов
        self._tool_status_frame = self._build_tool_status()
        lay.addWidget(self._tool_status_frame)
        lay.addSpacing(8)
        lay.addWidget(self._hdiv())
        lay.addSpacing(10)

        version = QLabel("v0.1.0  ·  alpha")
        version.setObjectName("version_label")
        lay.addWidget(version)
        lay.addSpacing(14)

        return sidebar

    def _build_tool_status(self) -> QFrame:
        frm = QFrame()
        frm.setObjectName("sidebar_status")
        lay = QHBoxLayout(frm)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(12)

        ffmpeg_ok = self._env["ffmpeg"]
        ytdlp_ok  = self._env["yt_dlp"]

        self._lbl_ffmpeg = QLabel(
            f"{'🟢' if ffmpeg_ok else '🔴'} ffmpeg")
        self._lbl_ffmpeg.setObjectName("status_tool")
        self._lbl_ffmpeg.setProperty("ok", "true" if ffmpeg_ok else "false")
        self._lbl_ffmpeg.setToolTip(
            "ffmpeg найден" if ffmpeg_ok else "ffmpeg не найден — нарезка и склейка недоступны")
        lay.addWidget(self._lbl_ffmpeg)

        self._lbl_ytdlp = QLabel(
            f"{'🟢' if ytdlp_ok else '🔴'} yt-dlp")
        self._lbl_ytdlp.setObjectName("status_tool")
        self._lbl_ytdlp.setProperty("ok", "true" if ytdlp_ok else "false")
        self._lbl_ytdlp.setToolTip(
            "yt-dlp найден" if ytdlp_ok else "yt-dlp не найден — загрузка видео недоступна")
        lay.addWidget(self._lbl_ytdlp)
        lay.addStretch()
        return frm

    def _hdiv(self) -> QFrame:
        d = QFrame()
        d.setObjectName("sidebar_div")
        d.setFrameShape(QFrame.Shape.HLine)
        return d

    # ── СТЕК СТРАНИЦ ──────────────────────────────────────────────────
    def _build_stack(self) -> QStackedWidget:
        self.stack = QStackedWidget()

        self.page_channels   = ChannelsPage()
        self.page_processing = ProcessingPage()
        self.page_folders    = FoldersPage()
        self.page_stats      = StatsPage()
        self.page_presets    = PresetsPage()

        for page in [self.page_channels, self.page_processing,
                     self.page_folders, self.page_stats, self.page_presets]:
            self.stack.addWidget(page)

        return self.stack

    # ── МАРШРУТИЗАЦИЯ СИГНАЛОВ ────────────────────────────────────────
    def _connect_signals(self):
        # Смена страницы → авто-обновление
        self.stack.currentChanged.connect(self._on_page_changed)

        # Пресет применён → обработка + статусбар
        self.page_presets.preset_applied.connect(self._on_preset_applied)

        # Каналы: скачивание запущено → обновить счётчик
        if hasattr(self.page_channels, "download_started"):
            self.page_channels.download_started.connect(self._refresh_dl_counter)

        # Каналы: скачивание завершено → обновить папки и статистику
        if hasattr(self.page_channels, "download_finished"):
            self.page_channels.download_finished.connect(self._on_download_finished)

    # ── СЛОТЫ ─────────────────────────────────────────────────────────
    def _navigate(self, idx: int):
        self.stack.setCurrentIndex(idx)
        if 0 <= idx < len(self._nav_buttons):
            self._nav_buttons[idx].setChecked(True)

    def _on_page_changed(self, idx: int):
        """Обновляем страницы при переходе на них."""
        if idx in REFRESH_ON_VISIT:
            page = self.stack.widget(idx)
            if hasattr(page, "refresh"):
                page.refresh()

    def _on_preset_applied(self, data: dict):
        """preset_applied от PresetsPage → ProcessingPage.apply_preset."""
        self.page_processing.apply_preset(data)
        name = "пресет"
        # Если в data есть мета-поле name (при желании можно добавить)
        self._statusbar.showMessage(
            f"✓ Пресет применён к настройкам обработки", 4000)
        # Переходим на страницу обработки
        self._navigate(1)

    def _on_download_finished(self, *_):
        self._refresh_dl_counter()
        # Помечаем папки/статистику как «требующие обновления» при следующем визите
        # (они обновятся автоматически через _on_page_changed)

    def _refresh_dl_counter(self, *_):
        """Обновляет счётчик активных загрузок в сайдбаре."""
        try:
            from download_queue import DownloadQueue
            from db import db
            # Считаем незавершённые задачи
            count = len([r for r in (db.conn.execute(
                "SELECT status FROM download_queue WHERE status IN ('pending','downloading')"
            ).fetchall() or [])])
        except Exception:
            count = 0

        active = count > 0
        self._dl_counter.setText(
            f"Загрузок: {count}" if active else "Нет активных загрузок")
        self._dl_counter.setProperty("active", "true" if active else "false")
        self._dl_counter.setStyleSheet(self._dl_counter.styleSheet())

    # ── ГЕОМЕТРИЯ ОКНА ────────────────────────────────────────────────
    def _restore_geometry(self):
        app_cfg = self.config.get("app", {})
        w = app_cfg.get("window_width",  1280)
        h = app_cfg.get("window_height", 800)
        x = app_cfg.get("window_x", -1)
        y = app_cfg.get("window_y", -1)
        self.resize(w, h)
        if x >= 0 and y >= 0:
            self.move(x, y)

    def _save_geometry(self):
        geom = self.geometry()
        cfg: dict = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
        cfg.setdefault("app", {}).update({
            "window_width":  geom.width(),
            "window_height": geom.height(),
            "window_x":      geom.x(),
            "window_y":      geom.y(),
        })
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent):
        self._dl_timer.stop()
        self._save_geometry()
        super().closeEvent(event)

    # ── Публичный метод ───────────────────────────────────────────────
    def navigate_to(self, page_index: int):
        """Переключает страницу программно."""
        self._navigate(page_index)
