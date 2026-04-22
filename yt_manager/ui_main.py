# ui_main.py — Главное окно приложения
#
# Содержит:
#   • Боковой навбар с иконками и статус-индикаторами
#   • QStackedWidget со всеми шестью страницами
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

from pages.channels_page    import ChannelsPage
from pages.tiktok_page      import TikTokPage
from pages.automation_page  import AutomationPage
from pages.publish_page     import PublishPage
from pages.processing_page  import ProcessingPage
from pages.folders_page     import FoldersPage
from pages.stats_page       import StatsPage
from pages.presets_page     import PresetsPage
from pages.settings_page    import SettingsPage
from pages.typewriter_page  import TypewriterPage

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
THEMES_DIR  = os.path.join(BASE_DIR, "assets", "themes")

# ──────────────────────────────────────────────────────────────────────
# QSS темы (файлы в assets/themes/{dark,light}.qss)
# ──────────────────────────────────────────────────────────────────────


def _load_theme_qss(name: str) -> str:
    """Читает файл assets/themes/<name>.qss. При ошибке возвращает ''."""
    path = os.path.join(THEMES_DIR, f"{name}.qss")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

NAV_ITEMS = [
    ("📺", "  YouTube каналы", 0, "nav_btn"),
    ("⚙️", "  Автоматизация",  1, "nav_btn"),
    ("🎞", "  Обработка",      2, "nav_btn"),
    ("🎵", "  TikTok каналы",  3, "nav_btn"),
    ("📤", "  Публикация",     4, "nav_btn"),
    ("📁", "  Папки",          5, "nav_btn"),
    ("📊", "  Статистика",     6, "nav_btn"),
    ("🎛", "  Пресеты",        7, "nav_btn"),
    ("🛠", "  Настройки",      8, "nav_btn"),
    ("🎬", "  Видео-генератор", 9, "nav_btn_tw"),
]

# Страницы, которые обновляются при каждом переходе
# (Автоматизация, Обработка, TikTok, Публикация, Папки, Статистика, Настройки)
REFRESH_ON_VISIT: set[int] = {1, 2, 3, 4, 5, 6, 8}


# ──────────────────────────────────────────────────────────────────────
# Главное окно
# ──────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, config: dict = None):
        super().__init__()
        self.config = config or {}
        self._env   = self._probe_env()

        self.setWindowTitle("YT Manager")
        self.setMinimumSize(980, 640)

        self._build_ui()
        self._connect_signals()
        try:
            from db import db
            self._theme = db.get_setting("theme", "dark") or "dark"
        except Exception:
            self._theme = "dark"
        self.apply_theme(self._theme)
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

        # Навигация — основные инструменты
        nav_lbl = QLabel("МЕНЮ")
        nav_lbl.setObjectName("nav_section")
        lay.addWidget(nav_lbl)
        lay.addSpacing(6)

        self._btn_group   = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._nav_buttons = []

        for icon, label, idx, obj_name in NAV_ITEMS:
            # Добавляем разделитель перед вкладкой «Видео-генератор»
            if idx == 9:
                lay.addSpacing(8)
                lay.addWidget(self._hdiv())
                lay.addSpacing(8)
                tools_lbl = QLabel("ИНСТРУМЕНТЫ")
                tools_lbl.setObjectName("nav_section")
                lay.addWidget(tools_lbl)
                lay.addSpacing(6)

            btn = QPushButton(f"  {icon}{label}")
            btn.setObjectName(obj_name)
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

        version = QLabel("v0.2.0  ·  alpha")
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

        self.page_channels    = ChannelsPage()
        self.page_automation  = AutomationPage()
        self.page_processing  = ProcessingPage()
        self.page_tiktok      = TikTokPage()
        self.page_publish     = PublishPage()
        self.page_folders     = FoldersPage()
        self.page_stats       = StatsPage()
        self.page_presets     = PresetsPage()
        self.page_settings    = SettingsPage()
        self.page_typewriter  = TypewriterPage()

        # Порядок страниц в стеке соответствует индексам NAV_ITEMS
        for page in [self.page_channels, self.page_automation,
                     self.page_processing, self.page_tiktok,
                     self.page_publish, self.page_folders,
                     self.page_stats, self.page_presets,
                     self.page_settings, self.page_typewriter]:
            self.stack.addWidget(page)

        return self.stack

    # ── МАРШРУТИЗАЦИЯ СИГНАЛОВ ────────────────────────────────────────
    def _connect_signals(self):
        self.stack.currentChanged.connect(self._on_page_changed)
        self.page_presets.preset_applied.connect(self._on_preset_applied)

        if hasattr(self.page_tiktok, "request_navigate_automation"):
            self.page_tiktok.request_navigate_automation.connect(
                lambda _tid: self._navigate(1)
            )
        if hasattr(self.page_publish, "request_open_automation"):
            self.page_publish.request_open_automation.connect(
                lambda _tid: self._navigate(1)
            )

        if hasattr(self.page_channels, "download_started"):
            self.page_channels.download_started.connect(self._refresh_dl_counter)

        if hasattr(self.page_channels, "download_finished"):
            self.page_channels.download_finished.connect(self._on_download_finished)

        if hasattr(self.page_settings, "theme_changed"):
            self.page_settings.theme_changed.connect(self.apply_theme)

    # ── ТЕМА ──────────────────────────────────────────────────────────
    def apply_theme(self, name: str):
        """Загружает QSS-файл темы и применяет к приложению."""
        from PyQt6.QtWidgets import QApplication
        qss = _load_theme_qss(name) or _load_theme_qss("dark")
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)
        else:
            self.setStyleSheet(qss)
        self._theme = name

    # ── СЛОТЫ ─────────────────────────────────────────────────────────
    def _navigate(self, idx: int):
        self.stack.setCurrentIndex(idx)
        if 0 <= idx < len(self._nav_buttons):
            self._nav_buttons[idx].setChecked(True)

    def _on_page_changed(self, idx: int):
        if idx in REFRESH_ON_VISIT:
            page = self.stack.widget(idx)
            if hasattr(page, "refresh"):
                page.refresh()

    def _on_preset_applied(self, preset_name: str):
        self._statusbar.showMessage(f"Пресет «{preset_name}» применён", 4000)
        # После применения пресета — переходим в Автоматизацию
        self._navigate(1)

    def _on_download_finished(self):
        self._refresh_dl_counter()
        if hasattr(self.page_folders, "refresh"):
            self.page_folders.refresh()
        if hasattr(self.page_stats, "refresh"):
            self.page_stats.refresh()

    def _refresh_dl_counter(self):
        try:
            from download_queue import queue_manager
            active = queue_manager.active_count
            self._dl_counter.setText(
                f"{'⏬ ' if active else ''}Загрузок: {active}")
            self._dl_counter.setProperty("active", "true" if active else "false")
            self._dl_counter.style().unpolish(self._dl_counter)
            self._dl_counter.style().polish(self._dl_counter)
        except Exception:
            pass

    # ── ГЕОМЕТРИЯ ─────────────────────────────────────────────────────
    def _restore_geometry(self):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            geo = cfg.get("window_geometry")
            if geo:
                self.resize(geo.get("width", 1100), geo.get("height", 700))
                if "x" in geo and "y" in geo:
                    self.move(geo["x"], geo["y"])
            else:
                self.resize(1100, 700)
        except Exception:
            self.resize(1100, 700)

    def _save_geometry(self):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        g = self.geometry()
        cfg["window_geometry"] = {
            "x": g.x(), "y": g.y(),
            "width": g.width(), "height": g.height(),
        }
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def closeEvent(self, event: QCloseEvent):
        self._save_geometry()
        super().closeEvent(event)
