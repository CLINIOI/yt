# processing_page.py — Страница обработки видео (полный редизайн)
#
# Архитектура:
#   SourcePanel      — выбор источника видео (файл / папка / канал)
#   CutPanel         — настройки нарезки
#   CompositionPanel — слоты верх/центр/низ + фон
#   SubtitlePanel    — субтитры
#   FormatPanel      — формат вывода / пропорции
#   OutputPanel      — имя файла / папка вывода
#   TaskCard         — карточка активной задачи
#   ProcessingPage   — главная страница

import os
import re
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QCheckBox,
    QComboBox, QListWidget, QListWidgetItem, QScrollArea,
    QFileDialog, QAbstractItemView, QSizePolicy, QProgressBar,
    QSplitter, QButtonGroup, QStackedWidget, QTabBar,
    QGroupBox, QRadioButton, QSlider,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont

from pages.base_page import BasePage
from db import db
from video_service import VideoService, ProcessWorker, is_ffmpeg_available

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.ts', '.flv'}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORMAT_PRESETS = {
    'original': {'label': 'Оригинал',  'w': 0,    'h': 0,    'top': 0,   'center': 0,    'bottom': 0,   'ratio': 'исходный'},
    'tiktok':   {'label': 'TikTok',    'w': 1080,  'h': 1920, 'top': 320, 'center': 1280, 'bottom': 320, 'ratio': '9:16'},
    'reels':    {'label': 'Reels',     'w': 1080,  'h': 1920, 'top': 240, 'center': 1440, 'bottom': 240, 'ratio': '9:16'},
    'shorts':   {'label': 'Shorts',    'w': 1080,  'h': 1920, 'top': 0,   'center': 1920, 'bottom': 0,   'ratio': '9:16'},
    'square':   {'label': 'Квадрат',   'w': 1080,  'h': 1080, 'top': 200, 'center': 680,  'bottom': 200, 'ratio': '1:1'},
    'youtube':  {'label': 'YouTube',   'w': 1920,  'h': 1080, 'top': 0,   'center': 1080, 'bottom': 0,   'ratio': '16:9'},
}

QUALITY_MAP = {'Быстро':   'fast', 'Хорошо': 'medium', 'Лучшее': 'slow'}
BG_COLOR_MAP = {'Чёрный': 'black', 'Белый': 'white', 'Серый': 'gray'}
SUB_COLOR_MAP = {'Белый': 'white', 'Жёлтый': 'yellow', 'Чёрный': 'black'}

# ──────────────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────────────

PAGE_QSS = """
/* ── Фон страницы ── */
QWidget#proc_page { background: #171614; }

/* ── Заголовок ── */
QFrame#proc_header { background: #1c1b19; border-bottom: 1px solid #2d2c2a; }
QLabel#page_title  { color: #cdccca; font-size: 15px; font-weight: 700; }
QLabel#page_sub    { color: #5a5957; font-size: 11px; }

/* ── Секции (группы) ── */
QFrame#section_card {
    background: #1c1b19;
    border: 1px solid #2d2c2a;
    border-radius: 10px;
}
QLabel#section_title {
    color: #cdccca; font-size: 12px; font-weight: 700;
}
QLabel#section_hint {
    color: #5a5957; font-size: 10px;
}

/* ── Разделители ── */
QFrame#hdiv { background: #2d2c2a; max-height: 1px; }

/* ── Кнопки источника (радио-стиль) ── */
QPushButton#src_btn {
    background: #201f1d; color: #797876;
    border: 1px solid #2d2c2a; border-radius: 7px;
    font-size: 11px; font-weight: 600;
    padding: 7px 14px; text-align: left;
}
QPushButton#src_btn:hover   { border-color: #4f98a3; color: #cdccca; }
QPushButton#src_btn:checked {
    background: #1a3535; color: #4f98a3;
    border-color: #4f98a3; font-weight: 700;
}

/* ── Слот видео ── */
QFrame#slot_frame {
    background: #201f1d; border: 1px solid #2d2c2a;
    border-radius: 8px;
}
QFrame#slot_frame[required="true"]  { border-color: #313b3b; }
QFrame#slot_frame[filled="true"]    { border-color: #01696f; }
QLabel#slot_title   { color: #797876; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; }
QLabel#slot_badge   { color: #4f98a3; font-size: 9px; font-weight: 700; background: #1a3535; border-radius: 3px; padding: 1px 5px; }
QLabel#slot_badge_req { color: #bb653b; font-size: 9px; font-weight: 700; background: #2a1a10; border-radius: 3px; padding: 1px 5px; }
QLabel#slot_path    { color: #4f98a3; font-size: 11px; }
QLabel#slot_empty   { color: #3a3937; font-size: 11px; font-style: italic; }
QLabel#slot_info    { color: #5a5957; font-size: 10px; }

/* ── Кнопки слота ── */
QPushButton#slot_pick {
    background: #28251d; border: 1px solid #393836;
    border-radius: 5px; color: #cdccca; font-size: 11px; padding: 4px 10px;
}
QPushButton#slot_pick:hover { background: #2d2c2a; border-color: #4f98a3; }
QPushButton#slot_clear {
    background: transparent; border: none;
    color: #3a3937; font-size: 13px; border-radius: 4px; padding: 2px 6px;
}
QPushButton#slot_clear:hover { color: #dd6974; background: #2a1a1a; }

/* ── Поля ввода ── */
QLineEdit#field {
    background: #201f1d; border: 1px solid #393836;
    border-radius: 6px; color: #cdccca; font-size: 12px; padding: 6px 10px;
}
QLineEdit#field:focus { border-color: #4f98a3; }
QLineEdit#field:disabled { color: #3a3937; background: #1c1b19; }

QSpinBox#spin {
    background: #201f1d; border: 1px solid #393836;
    border-radius: 6px; color: #cdccca; font-size: 12px; padding: 5px 8px;
}
QSpinBox#spin:focus { border-color: #4f98a3; }
QSpinBox#spin::up-button, QSpinBox#spin::down-button {
    width: 16px; border: none; background: #2d2c2a; border-radius: 3px;
}

QComboBox#combo {
    background: #201f1d; border: 1px solid #393836;
    border-radius: 6px; color: #cdccca; font-size: 12px; padding: 5px 10px; min-width: 110px;
}
QComboBox#combo:focus { border-color: #4f98a3; }
QComboBox#combo::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #201f1d; color: #cdccca;
    border: 1px solid #393836; outline: none; selection-background-color: #313b3b;
}

QCheckBox#chk { color: #cdccca; font-size: 12px; spacing: 8px; }
QCheckBox#chk::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #393836; background: #201f1d;
}
QCheckBox#chk::indicator:checked { background: #4f98a3; border-color: #4f98a3; }

QRadioButton#radio { color: #cdccca; font-size: 12px; spacing: 8px; }
QRadioButton#radio::indicator {
    width: 14px; height: 14px; border-radius: 7px;
    border: 1px solid #393836; background: #201f1d;
}
QRadioButton#radio::indicator:checked { background: #4f98a3; border-color: #4f98a3; }

/* ── Формат кнопки ── */
QPushButton#fmt_btn {
    background: #201f1d; border: 1px solid #2d2c2a;
    border-radius: 7px; color: #797876; font-size: 10px; font-weight: 600;
    padding: 0; min-width: 72px; min-height: 48px;
}
QPushButton#fmt_btn:hover { border-color: #5a5957; color: #cdccca; }
QPushButton#fmt_btn:checked {
    background: #1a3535; border: 2px solid #4f98a3; color: #4f98a3; font-weight: 700;
}

/* ── Кнопки действий ── */
QPushButton#btn_start {
    background: #01696f; color: #f9f8f5; border: none;
    border-radius: 8px; font-size: 13px; font-weight: 700;
    padding: 11px 0; min-height: 42px;
}
QPushButton#btn_start:hover    { background: #0c4e54; }
QPushButton#btn_start:disabled { background: #2d2c2a; color: #5a5957; }

QPushButton#btn_secondary {
    background: #28251d; border: 1px solid #393836;
    border-radius: 7px; color: #cdccca; font-size: 12px; padding: 7px 16px;
}
QPushButton#btn_secondary:hover { background: #2d2c2a; border-color: #5a5957; }

QPushButton#icon_btn {
    background: #28251d; color: #797876; border: 1px solid #2d2c2a;
    border-radius: 5px; font-size: 13px; padding: 3px 8px;
    min-width: 28px; min-height: 28px;
}
QPushButton#icon_btn:hover { background: #2d2c2a; color: #cdccca; }
QPushButton#icon_btn:disabled { color: #3a3937; }

/* ── Список видео каналов ── */
QListWidget#ch_list {
    background: #201f1d; border: 1px solid #2d2c2a;
    border-radius: 6px; color: #cdccca; font-size: 11px; outline: none;
}
QListWidget#ch_list::item { padding: 5px 10px; border-radius: 4px; }
QListWidget#ch_list::item:selected { background: #313b3b; color: #4f98a3; }
QListWidget#ch_list::item:hover:!selected { background: #262523; }

/* ── Карточка задачи ── */
QFrame#task_card {
    background: #201f1d; border: 1px solid #2d2c2a; border-radius: 10px;
}
QLabel#task_op   { color: #4f98a3; font-size: 11px; font-weight: 700; }
QLabel#task_desc { color: #cdccca; font-size: 12px; }
QLabel#task_msg  { color: #5a5957; font-size: 11px; }
QPushButton#task_cancel {
    background: transparent; border: none; color: #3a3937;
    font-size: 14px; border-radius: 4px; padding: 2px 6px;
}
QPushButton#task_cancel:hover { color: #dd6974; background: #2a1a1a; }
QPushButton#btn_del {
    background: #2d2c2a; color: #dd6974; border: 1px solid #3a3836;
    border-radius: 5px; padding: 3px 12px; font-size: 11px;
}
QPushButton#btn_del:hover { background: #3a2828; border-color: #dd6974; }
QPushButton#btn_del_warn {
    background: #2d2c2a; color: #fdab43; border: 1px solid #3a3836;
    border-radius: 5px; padding: 3px 12px; font-size: 11px;
}
QPushButton#btn_del_warn:hover { background: #2e2820; border-color: #fdab43; }
QPushButton#btn_del_done {
    background: transparent; color: #5a5957; border: none;
    font-size: 11px; padding: 3px 12px;
}
QProgressBar#task_bar {
    background: #2d2c2a; border: none; border-radius: 3px;
    max-height: 4px; min-height: 4px;
}
QProgressBar#task_bar::chunk { background: #4f98a3; border-radius: 3px; }

/* ── Правая панель задач ── */
QFrame#tasks_panel { background: #171614; border-left: 1px solid #2d2c2a; }
QLabel#tasks_title { color: #5a5957; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; }
QLabel#no_tasks { color: #2d2c2a; font-size: 13px; }

/* ── Scroll ── */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 5px; }
QScrollBar::handle:vertical { background: #2d2c2a; border-radius: 2px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Misc ── */
QLabel#lbl { color: #797876; font-size: 12px; }
QLabel#hint { color: #5a5957; font-size: 10px; }
QLabel#err  { color: #dd6974; font-size: 11px; }
"""

# ──────────────────────────────────────────────────────────────────────
# УТИЛИТЫ
# ──────────────────────────────────────────────────────────────────────

def _lbl(text, obj='lbl', wrap=False):
    l = QLabel(text)
    l.setObjectName(obj)
    if wrap:
        l.setWordWrap(True)
    return l

def _hdiv():
    f = QFrame(); f.setObjectName('hdiv'); f.setFixedHeight(1); return f

def _spin(lo, hi, val, suffix=''):
    s = QSpinBox(); s.setObjectName('spin')
    s.setRange(lo, hi); s.setValue(val)
    if suffix: s.setSuffix(suffix)
    return s

def _combo(items):
    c = QComboBox(); c.setObjectName('combo')
    c.addItems(items); return c

def _section_card(title, hint=''):
    card = QFrame(); card.setObjectName('section_card')
    lay = QVBoxLayout(card); lay.setContentsMargins(14, 12, 14, 14); lay.setSpacing(10)
    hdr = QHBoxLayout(); hdr.setSpacing(8)
    t = QLabel(title.upper()); t.setObjectName('section_title')
    hdr.addWidget(t); hdr.addStretch()
    if hint:
        h = QLabel(hint); h.setObjectName('section_hint'); hdr.addWidget(h)
    lay.addLayout(hdr)
    lay.addWidget(_hdiv())
    return card, lay

def _pick_random_video(folder):
    import random
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
    return random.choice(files) if files else None

def _sanitize(name):
    return re.sub(r'[/:*?"<>|\\]', '_', name).strip()[:120]

# ──────────────────────────────────────────────────────────────────────
# ВИДЖЕТ: ВЫБОР ВИДЕО (слот)
# ──────────────────────────────────────────────────────────────────────

class VideoSlot(QFrame):
    """
    Слот для одного видео: отображает путь, разрешение, кнопки выбора.
    Режимы выбора: файл, папка (случайный файл), видео из канала.
    """
    changed = pyqtSignal()

    SLOT_CONFIGS = {
        'center': {'icon': '🎬', 'title': 'ЦЕНТР  —  Главное видео',     'req': True},
        'top':    {'icon': '📢', 'title': 'ВЕРХ  —  Рекламный баннер',    'req': False},
        'bottom': {'icon': '🎮', 'title': 'НИЗ  —  Удержание внимания',   'req': False},
        'bg':     {'icon': '🖼', 'title': 'ФОН  —  Зацикленное видео',    'req': False},
    }

    def __init__(self, slot_key='center', parent=None):
        super().__init__(parent)
        self.setObjectName('slot_frame')
        cfg = self.SLOT_CONFIGS.get(slot_key, {'icon': '📄', 'title': slot_key, 'req': False})
        self._req = cfg['req']
        self._icon = cfg['icon']
        self._title_text = cfg['title']
        self._path = ''
        self._is_folder = False
        self.setProperty('required', 'true' if self._req else 'false')
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # Заголовок
        hdr = QHBoxLayout(); hdr.setSpacing(6)
        icon_lbl = QLabel(self._icon); icon_lbl.setStyleSheet('font-size:14px;')
        hdr.addWidget(icon_lbl)
        t = QLabel(self._title_text); t.setObjectName('slot_title'); hdr.addWidget(t)
        hdr.addStretch()
        badge_text = 'обязательно' if self._req else 'необязательно'
        badge_obj = 'slot_badge_req' if self._req else 'slot_badge'
        b = QLabel(badge_text); b.setObjectName(badge_obj); hdr.addWidget(b)
        self._clear_btn = QPushButton('✕'); self._clear_btn.setObjectName('slot_clear')
        self._clear_btn.setFixedSize(22, 22)
        self._clear_btn.setToolTip('Очистить слот')
        self._clear_btn.clicked.connect(self.clear)
        self._clear_btn.hide()
        hdr.addWidget(self._clear_btn)
        lay.addLayout(hdr)

        # Путь / статус
        self._path_lbl = QLabel('Не выбрано'); self._path_lbl.setObjectName('slot_empty')
        self._path_lbl.setWordWrap(True)
        lay.addWidget(self._path_lbl)

        # Инфо о разрешении
        self._info_lbl = QLabel(''); self._info_lbl.setObjectName('slot_info')
        lay.addWidget(self._info_lbl)

        # Кнопки
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        for text, tip, slot in [
            ('📄  Файл',    'Выбрать видеофайл',              self._pick_file),
            ('📁  Папка',   'Выбрать папку (случайное видео)', self._pick_folder),
            ('📺  Канал',   'Выбрать из скачанных видео',      self._pick_from_channel),
        ]:
            btn = QPushButton(text); btn.setObjectName('slot_pick')
            btn.setToolTip(tip); btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Выберите видео', '',
            'Видео (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;Все файлы (*)'
        )
        if path: self._set(path, is_folder=False)

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Выберите папку с видео')
        if path: self._set(path, is_folder=True)

    def _pick_from_channel(self):
        dlg = ChannelVideoPicker(self)
        if dlg.exec():
            path = dlg.selected_path()
            if path: self._set(path, is_folder=False)

    def _set(self, path, is_folder=False):
        self._path = path
        self._is_folder = is_folder
        self.setProperty('filled', 'true')
        self.style().unpolish(self); self.style().polish(self)
        self._clear_btn.show()

        if is_folder:
            try:
                files = [f for f in os.listdir(path)
                         if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
                self._path_lbl.setObjectName('slot_path')
                self._path_lbl.setText(f'📁  {os.path.basename(path)}  ({len(files)} видео)')
                self._info_lbl.setText('Случайное видео при каждом запуске')
            except Exception:
                self._path_lbl.setText(f'📁  {path}')
        else:
            self._path_lbl.setObjectName('slot_path')
            self._path_lbl.setText(f'📄  {os.path.basename(path)}')
            self._load_info(path)

        self._path_lbl.style().unpolish(self._path_lbl)
        self._path_lbl.style().polish(self._path_lbl)
        self.changed.emit()

    def _load_info(self, path):
        try:
            svc = VideoService()
            info = svc.get_video_info(path)
            self._info_lbl.setText(
                f'{info.resolution}  ·  {info.duration_str}  ·  {info.fps:.2f} fps  ·  {info.size_mb} MB'
            )
        except Exception:
            self._info_lbl.setText('')

    def clear(self):
        self._path = ''; self._is_folder = False
        self.setProperty('filled', 'false')
        self.style().unpolish(self); self.style().polish(self)
        self._clear_btn.hide()
        self._path_lbl.setObjectName('slot_empty')
        self._path_lbl.setText('Не выбрано')
        self._path_lbl.style().unpolish(self._path_lbl)
        self._path_lbl.style().polish(self._path_lbl)
        self._info_lbl.setText('')
        self.changed.emit()

    def resolve_path(self):
        """Возвращает реальный путь к файлу (для папки — случайный файл)."""
        if not self._path: return None
        if self._is_folder: return _pick_random_video(self._path)
        return self._path

    def path(self): return self._path
    def is_empty(self): return not bool(self._path)

    def set_path(self, path):
        if path: self._set(path, is_folder=os.path.isdir(path))


# ──────────────────────────────────────────────────────────────────────
# ДИАЛОГ: ВЫБОР ВИДЕО ИЗ КАНАЛА
# ──────────────────────────────────────────────────────────────────────

class ChannelVideoPicker(object):
    """Упрощённый пикер — через QDialog."""
    from PyQt6.QtWidgets import QDialog

    def __new__(cls, parent=None):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QListWidget, QListWidgetItem, QDialogButtonBox, QLabel
        dlg = QDialog(parent)
        dlg.setWindowTitle('Выбрать видео из канала')
        dlg.setMinimumSize(520, 400)
        dlg.setStyleSheet(PAGE_QSS + "QDialog{background:#1c1b19;}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(QLabel('Канал:'))
        ch_combo = QComboBox(); ch_combo.setObjectName('combo')
        channels = []
        try: channels = db.get_all_channels()
        except: pass
        for ch in channels:
            ch_combo.addItem(ch.get('title') or ch.get('url', '?'), ch['id'])
        lay.addWidget(ch_combo)

        vlist = QListWidget(); vlist.setObjectName('ch_list')
        lay.addWidget(vlist)

        dlg._selected = ''

        def _load_videos(idx):
            vlist.clear()
            ch_id = ch_combo.itemData(idx)
            if ch_id is None: return
            try:
                videos = db.get_videos_by_channel(ch_id, status='downloaded')
                for v in videos:
                    fp = v.get('file_path', '')
                    if fp and os.path.isfile(fp):
                        item = QListWidgetItem(v.get('title', os.path.basename(fp)))
                        item.setData(Qt.ItemDataRole.UserRole, fp)
                        item.setToolTip(fp)
                        vlist.addItem(item)
            except: pass

        ch_combo.currentIndexChanged.connect(_load_videos)
        if ch_combo.count() > 0: _load_videos(0)

        def _on_select():
            sel = vlist.selectedItems()
            if sel: dlg._selected = sel[0].data(Qt.ItemDataRole.UserRole)
            dlg.accept()

        vlist.itemDoubleClicked.connect(lambda _: _on_select())

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(_on_select)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        dlg.selected_path = lambda: dlg._selected
        return dlg


# ──────────────────────────────────────────────────────────────────────
# ПАНЕЛЬ: ИСТОЧНИК ВИДЕО
# ──────────────────────────────────────────────────────────────────────

class SourcePanel(QFrame):
    """
    Выбор главного видео для обработки:
      - Один файл
      - Папка (несколько видео, настройки применяются ко всем)
      - Из скачанных видео каналов
    """
    source_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('section_card')
        self._paths = []   # список файлов для обработки
        self._channel_id = None
        self._channel_name = ''
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        # Заголовок
        hdr = QHBoxLayout()
        t = QLabel('📥  ИСТОЧНИК ВИДЕО'); t.setObjectName('section_title'); hdr.addWidget(t)
        hdr.addStretch()
        lay.addLayout(hdr)
        lay.addWidget(_hdiv())

        # Кнопки-переключатели
        mode_row = QHBoxLayout(); mode_row.setSpacing(6)
        self._btn_group = QButtonGroup(self); self._btn_group.setExclusive(True)
        self._mode_btns = {}
        for key, label in [('file', '📄  Файл'), ('folder', '📁  Папка'), ('channel', '📺  Канал')]:
            btn = QPushButton(label); btn.setObjectName('src_btn')
            btn.setCheckable(True); btn.setFixedHeight(34)
            self._btn_group.addButton(btn)
            self._mode_btns[key] = btn
            mode_row.addWidget(btn)
        mode_row.addStretch()
        self._mode_btns['file'].setChecked(True)
        lay.addLayout(mode_row)

        # Стек панелей
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_file_panel())    # 0
        self._stack.addWidget(self._build_folder_panel())  # 1
        self._stack.addWidget(self._build_channel_panel()) # 2
        lay.addWidget(self._stack)

        self._mode_btns['file'].clicked.connect(lambda: self._set_mode(0))
        self._mode_btns['folder'].clicked.connect(lambda: self._set_mode(1))
        self._mode_btns['channel'].clicked.connect(lambda: self._set_mode(2))

        # Выбранные файлы
        self._selected_lbl = _lbl('', 'hint'); lay.addWidget(self._selected_lbl)

    def _build_file_panel(self):
        w = QWidget()
        lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(8)
        self._file_edit = QLineEdit(); self._file_edit.setObjectName('field')
        self._file_edit.setPlaceholderText('Путь к видеофайлу...')
        self._file_edit.textChanged.connect(self._on_file_changed)
        lay.addWidget(self._file_edit)
        btn = QPushButton('Обзор'); btn.setObjectName('btn_secondary')
        btn.setFixedWidth(70); btn.clicked.connect(self._browse_file)
        lay.addWidget(btn)
        self._file_info = _lbl('', 'hint')
        return w

    def _build_folder_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)
        row = QHBoxLayout(); row.setSpacing(8)
        self._folder_edit = QLineEdit(); self._folder_edit.setObjectName('field')
        self._folder_edit.setPlaceholderText('Путь к папке с видео...')
        self._folder_edit.textChanged.connect(self._on_folder_changed)
        row.addWidget(self._folder_edit)
        btn = QPushButton('Обзор'); btn.setObjectName('btn_secondary')
        btn.setFixedWidth(70); btn.clicked.connect(self._browse_folder)
        row.addWidget(btn)
        lay.addLayout(row)
        self._folder_info = _lbl('', 'hint'); lay.addWidget(self._folder_info)
        return w

    def _build_channel_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(8)

        row1 = QHBoxLayout(); row1.setSpacing(8)
        row1.addWidget(_lbl('Канал:'))
        self._ch_combo = _combo([])
        self._ch_combo.setToolTip('Выберите канал')
        self._ch_combo.currentIndexChanged.connect(self._load_channel_videos)
        row1.addWidget(self._ch_combo, stretch=1)
        lay.addLayout(row1)

        self._ch_list = QListWidget(); self._ch_list.setObjectName('ch_list')
        self._ch_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._ch_list.setFixedHeight(120)
        self._ch_list.setToolTip('Выберите одно или несколько видео (Ctrl+Click для множественного выбора)')
        self._ch_list.itemSelectionChanged.connect(self._on_channel_selection)
        lay.addWidget(self._ch_list)
        return w

    def _set_mode(self, idx):
        self._stack.setCurrentIndex(idx)
        self._paths = []
        self._selected_lbl.setText('')
        if idx == 2: self._refresh_channels()
        self.source_changed.emit()

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Выбрать видео', '',
            'Видео (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;Все файлы (*)'
        )
        if path: self._file_edit.setText(path)

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Выбрать папку')
        if path: self._folder_edit.setText(path)

    def _on_file_changed(self, path):
        path = path.strip()
        if os.path.isfile(path):
            self._paths = [path]
            try:
                svc = VideoService()
                info = svc.get_video_info(path)
                self._selected_lbl.setText(
                    f'✔  {info.resolution}  ·  {info.duration_str}  ·  {info.size_mb} MB'
                )
            except:
                self._selected_lbl.setText(f'✔  {os.path.basename(path)}')
        else:
            self._paths = []
            self._selected_lbl.setText('')
        self.source_changed.emit()

    def _on_folder_changed(self, path):
        path = path.strip()
        if os.path.isdir(path):
            files = [os.path.join(path, f) for f in os.listdir(path)
                     if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
            files.sort()
            self._paths = files
            self._folder_info.setText(f'Найдено видео: {len(files)}')
            self._selected_lbl.setText(f'✔  Папка: {len(files)} видео будут обработаны')
        else:
            self._paths = []
            self._folder_info.setText('')
            self._selected_lbl.setText('')
        self.source_changed.emit()

    def _refresh_channels(self):
        self._ch_combo.clear()
        try:
            channels = db.get_all_channels()
            for ch in channels:
                self._ch_combo.addItem(ch.get('title') or ch.get('url', '?'), ch['id'])
            if self._ch_combo.count() > 0:
                self._load_channel_videos(0)
        except: pass

    def _load_channel_videos(self, idx):
        self._ch_list.clear()
        self._paths = []
        ch_id = self._ch_combo.itemData(idx)
        self._channel_id = ch_id
        self._channel_name = self._ch_combo.currentText()
        if ch_id is None: return
        try:
            videos = db.get_videos_by_channel(ch_id, status='downloaded')
            for v in videos:
                fp = v.get('file_path', '')
                if fp and os.path.isfile(fp):
                    item = QListWidgetItem(v.get('title', os.path.basename(fp)))
                    item.setData(Qt.ItemDataRole.UserRole, (fp, v.get('title', '')))
                    item.setToolTip(fp)
                    self._ch_list.addItem(item)
        except: pass

    def _on_channel_selection(self):
        sel = self._ch_list.selectedItems()
        self._paths = [it.data(Qt.ItemDataRole.UserRole)[0] for it in sel]
        n = len(sel)
        self._selected_lbl.setText(f'✔  Выбрано: {n} видео' if n else '')
        self.source_changed.emit()

    def get_paths(self):
        """Возвращает список путей к видео для обработки."""
        return list(self._paths)

    def get_channel_info(self):
        """Возвращает (channel_id, channel_name) или (None, '')."""
        if self._mode_btns['channel'].isChecked():
            return self._channel_id, self._channel_name
        return None, ''

    def get_video_title(self, path):
        """Возвращает название видео (из канала или имя файла)."""
        if self._mode_btns['channel'].isChecked():
            for i in range(self._ch_list.count()):
                item = self._ch_list.item(i)
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and data[0] == path:
                    return data[1] or os.path.splitext(os.path.basename(path))[0]
        return os.path.splitext(os.path.basename(path))[0]


# ──────────────────────────────────────────────────────────────────────
# ПАНЕЛЬ: НАРЕЗКА
# ──────────────────────────────────────────────────────────────────────

class CutPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('section_card')
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        self._enabled = QCheckBox('✂  НАРЕЗКА'); self._enabled.setObjectName('chk')
        self._enabled.setStyleSheet('QCheckBox{color:#cdccca;font-size:12px;font-weight:700;}')
        self._enabled.toggled.connect(self._on_toggle)
        hdr.addWidget(self._enabled); hdr.addStretch()
        lay.addLayout(hdr)
        lay.addWidget(_hdiv())

        self._body = QWidget()
        body_lay = QGridLayout(self._body)
        body_lay.setSpacing(8)
        body_lay.setColumnMinimumWidth(0, 160)
        body_lay.setColumnStretch(1, 1)

        # Режим нарезки
        body_lay.addWidget(_lbl('Режим нарезки:'), 0, 0)
        mode_w = QWidget(); mode_lay = QHBoxLayout(mode_w)
        mode_lay.setContentsMargins(0,0,0,0); mode_lay.setSpacing(10)
        self._mode_time  = QRadioButton('По времени'); self._mode_time.setObjectName('radio')
        self._mode_count = QRadioButton('По количеству'); self._mode_count.setObjectName('radio')
        self._mode_time.setChecked(True)
        self._mode_time.toggled.connect(self._on_mode_toggle)
        mode_lay.addWidget(self._mode_time); mode_lay.addWidget(self._mode_count)
        mode_lay.addStretch()
        body_lay.addWidget(mode_w, 0, 1)

        # Длительность
        body_lay.addWidget(_lbl('Длительность клипа:'), 1, 0)
        dur_w = QWidget(); dur_lay = QHBoxLayout(dur_w)
        dur_lay.setContentsMargins(0,0,0,0); dur_lay.setSpacing(6)
        self._duration = _spin(1, 3600, 60, ' сек')
        self._duration.setToolTip('Длина каждого клипа в секундах')
        dur_lay.addWidget(self._duration); dur_lay.addStretch()
        body_lay.addWidget(dur_w, 1, 1)

        # Количество фрагментов
        self._count_row_lbl = _lbl('Количество клипов:')
        body_lay.addWidget(self._count_row_lbl, 2, 0)
        cnt_w = QWidget(); cnt_lay = QHBoxLayout(cnt_w)
        cnt_lay.setContentsMargins(0,0,0,0); cnt_lay.setSpacing(6)
        self._clip_count = _spin(2, 9999, 10, ' шт')
        self._clip_count.setToolTip('Видео будет разделено на N равных частей')
        cnt_lay.addWidget(self._clip_count)
        self._count_hint = _lbl('длительность подстроится автоматически', 'hint')
        cnt_lay.addWidget(self._count_hint); cnt_lay.addStretch()
        body_lay.addWidget(cnt_w, 2, 1)
        # По умолчанию скрываем строку количества
        self._count_row_lbl.hide(); cnt_w.hide()
        self._cnt_w = cnt_w  # сохраняем ссылку

        # Название файлов
        body_lay.addWidget(_lbl('Название нарезок:'), 3, 0)
        name_w = QWidget(); name_lay = QVBoxLayout(name_w)
        name_lay.setContentsMargins(0,0,0,0); name_lay.setSpacing(4)
        self._name_original = QRadioButton('Оригинальное название видео')
        self._name_original.setObjectName('radio'); self._name_original.setChecked(True)
        self._name_custom = QRadioButton('Своё название:')
        self._name_custom.setObjectName('radio')
        self._name_edit = QLineEdit(); self._name_edit.setObjectName('field')
        self._name_edit.setPlaceholderText('clip')
        self._name_edit.setEnabled(False)
        self._name_original.toggled.connect(lambda c: self._name_edit.setEnabled(not c))
        name_lay.addWidget(self._name_original)
        name_lay.addWidget(self._name_custom)
        name_lay.addWidget(self._name_edit)
        body_lay.addWidget(name_w, 3, 1)

        # Нумерация
        body_lay.addWidget(_lbl('Нумерация файлов:'), 4, 0)
        self._numbering = QCheckBox('Включить нумерацию (001, 002...)')
        self._numbering.setObjectName('chk'); self._numbering.setChecked(True)
        body_lay.addWidget(self._numbering, 4, 1)

        # Перекодировка
        body_lay.addWidget(_lbl('Перекодировать:'), 5, 0)
        self._reencode = QCheckBox('Libx264 (для дальнейшей склейки)')
        self._reencode.setObjectName('chk')
        self._reencode.setToolTip('Без перекодировки — быстро, но менее совместимо.\nВключи если клипы нужно дальше склеивать.')
        body_lay.addWidget(self._reencode, 5, 1)

        lay.addWidget(self._body)
        self._body.setEnabled(False)

    def _on_toggle(self, checked):
        self._body.setEnabled(checked)

    def _on_mode_toggle(self, time_checked):
        self._duration.setEnabled(time_checked)
        self._count_row_lbl.setVisible(not time_checked)
        self._cnt_w.setVisible(not time_checked)

    def is_enabled(self): return self._enabled.isChecked()

    def get_prefix(self, original_title=''):
        if self._name_original.isChecked():
            return _sanitize(original_title) if original_title else 'clip'
        return _sanitize(self._name_edit.text().strip()) or 'clip'

    def get_settings(self):
        by_count = self._mode_count.isChecked()
        return {
            'duration':   self._duration.value(),
            'clip_count': self._clip_count.value() if by_count else 0,
            'by_count':   by_count,
            'numbering':  self._numbering.isChecked(),
            'reencode':   self._reencode.isChecked(),
        }


# ──────────────────────────────────────────────────────────────────────
# ПАНЕЛЬ: КОМПОЗИЦИЯ (стекинг)
# ──────────────────────────────────────────────────────────────────────

class CompositionPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('section_card')
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        self._enabled = QCheckBox('🎞  КОМПОЗИЦИЯ / СТЕКИНГ')
        self._enabled.setObjectName('chk')
        self._enabled.setStyleSheet('QCheckBox{color:#cdccca;font-size:12px;font-weight:700;}')
        self._enabled.toggled.connect(self._on_toggle)
        hdr.addWidget(self._enabled); hdr.addStretch()
        lay.addLayout(hdr)
        lay.addWidget(_hdiv())

        self._body = QWidget()
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(0,0,0,0); body_lay.setSpacing(10)

        # Слоты
        self.slot_top    = VideoSlot('top')
        self.slot_bottom = VideoSlot('bottom')
        self.slot_bg     = VideoSlot('bg')
        body_lay.addWidget(self.slot_top)
        body_lay.addWidget(self.slot_bottom)
        body_lay.addWidget(self.slot_bg)

        # Аудио источник
        aud = QHBoxLayout(); aud.setSpacing(8)
        aud.addWidget(_lbl('Источник аудио:'))
        self._audio = _combo(['Центр (главное)', 'Верх (баннер)', 'Низ (фон)', 'Без звука'])
        self._audio.setToolTip('Звук из какого слота попадёт в итоговое видео')
        aud.addWidget(self._audio); aud.addStretch()
        body_lay.addLayout(aud)

        body_lay.addWidget(_hdiv())

        # Нарезать результат
        body_lay.addWidget(_hdiv())

        # ── Нарезка результата (встроенная) ──
        self._cut_after = QCheckBox('✂  Нарезать результат после рендеринга')
        self._cut_after.setObjectName('chk')
        body_lay.addWidget(self._cut_after)
        self._cut_after.toggled.connect(self._on_cut_toggle)

        # Контейнер настроек нарезки
        self._cut_box = QWidget()
        cut_lay = QGridLayout(self._cut_box)
        cut_lay.setContentsMargins(16, 4, 0, 0)
        cut_lay.setSpacing(6)

        # Режим
        cut_lay.addWidget(_lbl('Режим:'), 0, 0)
        mode_w2 = QWidget(); ml2 = QHBoxLayout(mode_w2)
        ml2.setContentsMargins(0,0,0,0); ml2.setSpacing(10)
        self._cmode_time  = QRadioButton('По времени'); self._cmode_time.setObjectName('radio')
        self._cmode_count = QRadioButton('По количеству'); self._cmode_count.setObjectName('radio')
        self._cmode_time.setChecked(True)
        self._cmode_time.toggled.connect(self._on_cut_mode_toggle)
        ml2.addWidget(self._cmode_time); ml2.addWidget(self._cmode_count); ml2.addStretch()
        cut_lay.addWidget(mode_w2, 0, 1)

        # Длительность
        self._cdur_lbl = _lbl('Длительность:')
        cut_lay.addWidget(self._cdur_lbl, 1, 0)
        cdw = QWidget(); cdl = QHBoxLayout(cdw)
        cdl.setContentsMargins(0,0,0,0); cdl.setSpacing(4)
        self._cduration = _spin(1, 3600, 60, ' сек')
        cdl.addWidget(self._cduration); cdl.addStretch()
        cut_lay.addWidget(cdw, 1, 1)

        # Количество
        self._ccnt_lbl = _lbl('Количество:')
        cut_lay.addWidget(self._ccnt_lbl, 2, 0)
        ccw = QWidget(); ccl = QHBoxLayout(ccw)
        ccl.setContentsMargins(0,0,0,0); ccl.setSpacing(4)
        self._cclip_count = _spin(2, 9999, 10, ' шт')
        self._ccount_hint = _lbl('время подстроится автоматически', 'hint')
        ccl.addWidget(self._cclip_count); ccl.addWidget(self._ccount_hint); ccl.addStretch()
        cut_lay.addWidget(ccw, 2, 1)

        # Перекодировка
        cut_lay.addWidget(_lbl('Перекодировать:'), 3, 0)
        self._creencode = QCheckBox('Да (медленнее, точнее)'); self._creencode.setObjectName('chk')
        cut_lay.addWidget(self._creencode, 3, 1)

        self._cut_box.hide()
        self._ccnt_lbl.hide(); ccw.hide()
        self._ccw = ccw
        body_lay.addWidget(self._cut_box)

        lay.addWidget(self._body)
        self._body.setEnabled(False)

    def _on_toggle(self, checked):
        self._body.setEnabled(checked)

    def _on_cut_toggle(self, checked):
        self._cut_box.setVisible(checked)

    def _on_cut_mode_toggle(self, time_checked):
        self._cdur_lbl.setEnabled(time_checked)
        self._cduration.setEnabled(time_checked)
        self._ccnt_lbl.setVisible(not time_checked)
        self._ccw.setVisible(not time_checked)

    def is_enabled(self): return self._enabled.isChecked()

    def get_settings(self):
        audio_map = ['center', 'top', 'bottom', 'none']
        by_count = self._cmode_count.isChecked()
        return {
            'top_path':    self.slot_top.resolve_path(),
            'bottom_path': self.slot_bottom.resolve_path(),
            'bg_path':     self.slot_bg.resolve_path(),
            'audio_source': audio_map[self._audio.currentIndex()],
            'cut_after':   self._cut_after.isChecked(),
            'cut_duration': self._cduration.value(),
            'cut_clip_count': self._cclip_count.value() if by_count else 0,
            'cut_reencode':  self._creencode.isChecked(),
        }


# ──────────────────────────────────────────────────────────────────────
# ПАНЕЛЬ: СУБТИТРЫ
# ──────────────────────────────────────────────────────────────────────

class SubtitlePanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('section_card')
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        self._enabled = QCheckBox('💬  СУБТИТРЫ')
        self._enabled.setObjectName('chk')
        self._enabled.setStyleSheet('QCheckBox{color:#cdccca;font-size:12px;font-weight:700;}')
        self._enabled.toggled.connect(self._on_toggle)
        hdr.addWidget(self._enabled); hdr.addStretch()
        lay.addLayout(hdr)
        lay.addWidget(_hdiv())

        self._body = QWidget()
        body_lay = QGridLayout(self._body)
        body_lay.setSpacing(8)
        body_lay.setColumnMinimumWidth(0, 130)
        body_lay.setColumnStretch(1, 1)

        # SRT файл
        body_lay.addWidget(_lbl('Файл субтитров:'), 0, 0)
        srt_row = QHBoxLayout(); srt_row.setSpacing(6)
        self._srt_edit = QLineEdit(); self._srt_edit.setObjectName('field')
        self._srt_edit.setPlaceholderText('Выберите .srt файл...')
        srt_row.addWidget(self._srt_edit)
        srt_btn = QPushButton('Обзор'); srt_btn.setObjectName('btn_secondary')
        srt_btn.setFixedWidth(70)
        srt_btn.clicked.connect(self._browse_srt)
        srt_row.addWidget(srt_btn)
        srt_w = QWidget(); srt_w.setLayout(srt_row)
        body_lay.addWidget(srt_w, 0, 1)

        body_lay.addWidget(_lbl('Размер шрифта:'), 1, 0)
        self._size = _spin(12, 72, 32, ' pt')
        body_lay.addWidget(self._size, 1, 1)

        body_lay.addWidget(_lbl('Цвет текста:'), 2, 0)
        self._color = _combo(['Белый', 'Жёлтый', 'Чёрный'])
        body_lay.addWidget(self._color, 2, 1)

        note = _lbl('⚠ Требуется ffmpeg с поддержкой libass', 'hint')
        body_lay.addWidget(note, 3, 0, 1, 2)

        lay.addWidget(self._body)
        self._body.setEnabled(False)

    def _on_toggle(self, checked):
        self._body.setEnabled(checked)

    def _browse_srt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Выбрать субтитры', '',
            'Субтитры (*.srt *.ass *.vtt);;Все файлы (*)'
        )
        if path: self._srt_edit.setText(path)

    def is_enabled(self): return self._enabled.isChecked()

    def get_settings(self):
        color_map = {'Белый': 'white', 'Жёлтый': 'yellow', 'Чёрный': 'black'}
        return {
            'subtitle_path':  self._srt_edit.text().strip() or None,
            'subtitle_size':  self._size.value(),
            'subtitle_color': color_map.get(self._color.currentText(), 'white'),
        }


# ──────────────────────────────────────────────────────────────────────
# ПАНЕЛЬ: ФОРМАТ И ПРОПОРЦИИ
# ──────────────────────────────────────────────────────────────────────

class FormatPanel(QFrame):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('section_card')
        self._active = 'original'
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        t = QLabel('🎬  ФОРМАТ И РАЗРЕШЕНИЕ'); t.setObjectName('section_title')
        hdr.addWidget(t); hdr.addStretch()
        lay.addLayout(hdr)
        lay.addWidget(_hdiv())

        # Кнопки форматов
        fmt_row = QHBoxLayout(); fmt_row.setSpacing(6)
        self._fmt_btns = {}
        self._fmt_group = QButtonGroup(self); self._fmt_group.setExclusive(True)
        for key, cfg in FORMAT_PRESETS.items():
            btn = QPushButton(f'{cfg["label"]}\n{cfg["ratio"]}')
            btn.setObjectName('fmt_btn'); btn.setCheckable(True)
            btn.setFixedSize(78, 48)
            btn.setToolTip(f'{cfg["label"]} — {cfg["ratio"]}\n{cfg["w"]}×{cfg["h"]} px' if cfg['w'] else 'Сохранять оригинальное разрешение')
            btn.clicked.connect(lambda _, k=key: self._select(k))
            self._fmt_btns[key] = btn
            self._fmt_group.addButton(btn)
            fmt_row.addWidget(btn)
        fmt_row.addStretch()
        lay.addLayout(fmt_row)
        self._fmt_btns['original'].setChecked(True)

        self._fmt_hint = _lbl('Оригинальные пропорции сохраняются', 'hint')
        lay.addWidget(self._fmt_hint)

        lay.addWidget(_hdiv())

        # Ручные пропорции
        self._custom_chk = QCheckBox('Задать пропорции вручную')
        self._custom_chk.setObjectName('chk')
        self._custom_chk.toggled.connect(self._on_custom_toggle)
        lay.addWidget(self._custom_chk)

        self._custom_body = QWidget()
        cust_lay = QGridLayout(self._custom_body)
        cust_lay.setSpacing(8); cust_lay.setColumnMinimumWidth(0, 130)
        cust_lay.addWidget(_lbl('Ширина (px):'), 0, 0)
        self._custom_w = _spin(100, 7680, 1080)
        cust_lay.addWidget(self._custom_w, 0, 1)
        cust_lay.addWidget(_lbl('Высота (px):'), 1, 0)
        self._custom_h = _spin(100, 7680, 1920)
        cust_lay.addWidget(self._custom_h, 1, 1)
        self._custom_body.setEnabled(False)
        lay.addWidget(self._custom_body)

        # Качество + фон
        grid2 = QGridLayout(); grid2.setSpacing(8); grid2.setColumnMinimumWidth(0, 130); grid2.setColumnStretch(1, 1)
        grid2.addWidget(_lbl('Качество кодирования:'), 0, 0)
        self._quality = _combo(['Быстро (fast)', 'Хорошо (medium)', 'Лучшее (slow)'])
        self._quality.setToolTip('fast — быстро\nmedium — баланс\nslow — максимальное качество')
        grid2.addWidget(self._quality, 0, 1)
        grid2.addWidget(_lbl('Цвет фона (паддинг):'), 1, 0)
        self._bg = _combo(['Чёрный', 'Белый', 'Серый'])
        self._bg.setToolTip('Цвет заливки пустых областей')
        grid2.addWidget(self._bg, 1, 1)
        lay.addLayout(grid2)

    def _select(self, key):
        self._active = key
        cfg = FORMAT_PRESETS[key]
        if cfg['w']:
            self._fmt_hint.setText(f'{cfg["w"]}×{cfg["h"]} px  —  {cfg["ratio"]}')
        else:
            self._fmt_hint.setText('Оригинальные пропорции сохраняются')
        self.changed.emit()

    def _on_custom_toggle(self, checked):
        self._custom_body.setEnabled(checked)
        if checked: self._active = 'custom'
        else: self._active = 'original'

    def get_settings(self):
        quality_map = {'Быстро (fast)': 'fast', 'Хорошо (medium)': 'medium', 'Лучшее (slow)': 'slow'}
        bg_map = {'Чёрный': 'black', 'Белый': 'white', 'Серый': 'gray'}
        cfg = FORMAT_PRESETS.get(self._active, FORMAT_PRESETS['original'])
        if self._custom_chk.isChecked():
            w, h = self._custom_w.value(), self._custom_h.value()
        else:
            w, h = cfg['w'], cfg['h']
        return {
            'format_key':     self._active,
            'output_width':   w or 1080,
            'output_height':  h or 1920,
            'top_h':          cfg.get('top', 0),
            'center_h':       cfg.get('center', 0) or (h or 1920),
            'bottom_h':       cfg.get('bottom', 0),
            'quality':        quality_map.get(self._quality.currentText(), 'fast'),
            'bg_color':       bg_map.get(self._bg.currentText(), 'black'),
        }


# ──────────────────────────────────────────────────────────────────────
# ПАНЕЛЬ: ПАРАМЕТРЫ ВЫВОДА
# ──────────────────────────────────────────────────────────────────────

class OutputPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('section_card')
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        t = QLabel('💾  ПАРАМЕТРЫ ВЫВОДА'); t.setObjectName('section_title')
        hdr.addWidget(t); hdr.addStretch()
        lay.addLayout(hdr)
        lay.addWidget(_hdiv())

        grid = QGridLayout(); grid.setSpacing(8)
        grid.setColumnMinimumWidth(0, 130); grid.setColumnStretch(1, 1)

        # Папка вывода
        grid.addWidget(_lbl('Папка вывода:'), 0, 0)
        out_row = QHBoxLayout(); out_row.setSpacing(6)
        self._out_edit = QLineEdit(); self._out_edit.setObjectName('field')
        self._out_edit.setPlaceholderText('processed\\название_канала\\название_видео  (авто)')
        self._out_edit.setToolTip('Оставь пустым для автоматического пути:\nprocessed\\канал\\видео')
        out_row.addWidget(self._out_edit)
        out_btn = QPushButton('Обзор'); out_btn.setObjectName('btn_secondary')
        out_btn.setFixedWidth(70); out_btn.clicked.connect(self._browse_out)
        out_row.addWidget(out_btn)
        out_w = QWidget(); out_w.setLayout(out_row)
        grid.addWidget(out_w, 0, 1)

        lay.addLayout(grid)
        lay.addWidget(_lbl('Если пусто — сохраняется в processed\\канал\\видео', 'hint'))

    def _browse_out(self):
        path = QFileDialog.getExistingDirectory(self, 'Выбрать папку вывода')
        if path: self._out_edit.setText(path)

    def get_output_dir(self, channel_name='', video_title=''):
        manual = self._out_edit.text().strip()
        if manual: return manual
        parts = ['processed']
        if channel_name: parts.append(_sanitize(channel_name))
        if video_title:  parts.append(_sanitize(video_title))
        return os.path.join(BASE_DIR, *parts)


# ──────────────────────────────────────────────────────────────────────
# КАРТОЧКА ЗАДАЧИ
# ──────────────────────────────────────────────────────────────────────

class TaskCard(QFrame):
    cancel_requested = pyqtSignal()

    def __init__(self, icon, op_name, desc, parent=None):
        super().__init__(parent)
        self.setObjectName('task_card')
        self._worker = None
        self._build(icon, op_name, desc)

    def _build(self, icon, op_name, desc):
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 10, 12, 10); lay.setSpacing(6)

        top = QHBoxLayout(); top.setSpacing(8)
        op_lbl = QLabel(f'{icon}  {op_name}'); op_lbl.setObjectName('task_op')
        top.addWidget(op_lbl)
        desc_lbl = QLabel(desc); desc_lbl.setObjectName('task_desc')
        fm = desc_lbl.fontMetrics()
        desc_lbl.setText(fm.elidedText(desc, Qt.TextElideMode.ElideMiddle, 260))
        top.addWidget(desc_lbl, stretch=1)
        self._cancel = QPushButton('✕'); self._cancel.setObjectName('task_cancel')
        self._cancel.setFixedSize(22, 22); self._cancel.clicked.connect(self._on_cancel)
        top.addWidget(self._cancel)
        lay.addLayout(top)

        self._bar = QProgressBar(); self._bar.setObjectName('task_bar')
        self._bar.setRange(0, 100); self._bar.setTextVisible(False)
        lay.addWidget(self._bar)

        bot = QHBoxLayout()
        self._msg = QLabel('Подготовка...'); self._msg.setObjectName('task_msg')
        bot.addWidget(self._msg, stretch=1)
        self._pct = QLabel('0%'); self._pct.setObjectName('task_op')
        self._pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        bot.addWidget(self._pct)
        lay.addLayout(bot)

    def attach(self, worker):
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_done)
        worker.error.connect(self._on_error)

    def _on_progress(self, pct, msg):
        self._bar.setValue(pct); self._pct.setText(f'{pct}%')
        if msg: self._msg.setText(msg)

    def _on_done(self, paths):
        self._bar.setValue(100); self._pct.setText('100%')
        self._msg.setStyleSheet('color:#6daa45; font-size:11px; font-weight:600;')
        self._msg.setText(f'Готово — {len(paths)} файл(ов)')
        self._cancel.hide(); self._worker = None

    def _on_error(self, msg):
        self._bar.setStyleSheet('QProgressBar::chunk{background:#dd6974;}')
        self._msg.setStyleSheet('color:#dd6974; font-size:11px;')
        self._msg.setText(f'Ошибка: {msg[:100]}')
        self._cancel.hide(); self._worker = None

    def _on_cancel(self):
        if self._worker and self._worker.isRunning(): self._worker.terminate()
        self.cancel_requested.emit()


# ──────────────────────────────────────────────────────────────────────
# ГЛАВНАЯ СТРАНИЦА
# ──────────────────────────────────────────────────────────────────────

class ProcessingPage(BasePage):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self._workers = []
        self._build()
        self.setStyleSheet(PAGE_QSS)

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Левая часть — настройки (скролл)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(420)
        left_scroll.setMaximumWidth(560)

        left_inner = QWidget(); left_inner.setObjectName('proc_page')
        left_lay = QVBoxLayout(left_inner)
        left_lay.setContentsMargins(16, 16, 16, 16)
        left_lay.setSpacing(12)

        # Заголовок
        hdr = QFrame(); hdr.setObjectName('proc_header')
        hdr_lay = QVBoxLayout(hdr); hdr_lay.setContentsMargins(0, 0, 0, 10); hdr_lay.setSpacing(2)
        hdr_lay.addWidget(QLabel('⚙  Обработка видео') if False else self._make_title())
        left_lay.addWidget(hdr)

        # Панели
        self.src_panel  = SourcePanel()
        self.cut_panel  = CutPanel()
        self.comp_panel = CompositionPanel()

        # Слот центра (главное видео) — в compositionPanel, но показываем отдельно для наглядности
        self._center_slot = VideoSlot('center')
        center_card, center_lay = _section_card('🎬  ГЛАВНОЕ ВИДЕО (центр)')
        center_lay.addWidget(self._center_slot)

        self.sub_panel  = SubtitlePanel()
        self.fmt_panel  = FormatPanel()
        self.out_panel  = OutputPanel()

        for w in [self.src_panel, self.cut_panel, center_card,
                  self.comp_panel, self.sub_panel, self.fmt_panel, self.out_panel]:
            left_lay.addWidget(w)

        # Ошибка + кнопка запуска
        self._err_lbl = _lbl('', 'err'); left_lay.addWidget(self._err_lbl)

        self._start_btn = QPushButton('▶  ЗАПУСТИТЬ ОБРАБОТКУ')
        self._start_btn.setObjectName('btn_start')
        self._start_btn.setToolTip('Применить все выбранные настройки к видео')
        self._start_btn.clicked.connect(self._start)
        left_lay.addWidget(self._start_btn)
        left_lay.addStretch()

        left_scroll.setWidget(left_inner)
        root.addWidget(left_scroll)

        # Правая часть — задачи
        right = QFrame(); right.setObjectName('tasks_panel')
        right_lay = QVBoxLayout(right); right_lay.setContentsMargins(16, 16, 16, 16); right_lay.setSpacing(10)

        tasks_hdr = QHBoxLayout()
        t = QLabel('ЗАДАЧИ'); t.setObjectName('tasks_title'); tasks_hdr.addWidget(t)
        tasks_hdr.addStretch()
        clr = QPushButton('Очистить'); clr.setObjectName('btn_secondary')
        clr.setFixedHeight(26); clr.clicked.connect(self._clear_tasks)
        tasks_hdr.addWidget(clr)
        right_lay.addLayout(tasks_hdr)

        tasks_scroll = QScrollArea(); tasks_scroll.setWidgetResizable(True)
        self._tasks_inner = QWidget(); self._tasks_inner.setObjectName('proc_page')
        self._tasks_lay = QVBoxLayout(self._tasks_inner)
        self._tasks_lay.setContentsMargins(0, 0, 0, 0); self._tasks_lay.setSpacing(8)
        self._tasks_lay.addStretch()
        tasks_scroll.setWidget(self._tasks_inner)
        right_lay.addWidget(tasks_scroll)

        self._no_tasks = QLabel('Нет активных задач'); self._no_tasks.setObjectName('no_tasks')
        self._no_tasks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_lay.addWidget(self._no_tasks)

        root.addWidget(right, stretch=1)

    def _make_title(self):
        w = QWidget()
        lay = QVBoxLayout(w); lay.setContentsMargins(0, 8, 0, 8); lay.setSpacing(2)
        t = QLabel('Обработка видео'); t.setObjectName('page_title')
        s = QLabel('Нарезка · Композиция · Субтитры · Форматы'); s.setObjectName('page_sub')
        lay.addWidget(t); lay.addWidget(s)
        return w

    def _start(self):
        self._err_lbl.setText('')

        paths = self.src_panel.get_paths()
        if not paths:
            self._err_lbl.setText('⚠ Выберите исходное видео')
            return

        center_path = self._center_slot.resolve_path()
        ch_id, ch_name = self.src_panel.get_channel_info()

        cut_settings  = self.cut_panel.get_settings()   if self.cut_panel.is_enabled()  else None
        comp_settings = self.comp_panel.get_settings()  if self.comp_panel.is_enabled() else None
        sub_settings  = self.sub_panel.get_settings()   if self.sub_panel.is_enabled()  else None
        fmt_settings  = self.fmt_panel.get_settings()

        for video_path in paths:
            video_title = self.src_panel.get_video_title(video_path)
            out_dir = self.out_panel.get_output_dir(ch_name, video_title)
            os.makedirs(out_dir, exist_ok=True)

            # ── НАРЕЗКА ──
            if cut_settings:
                prefix = self.cut_panel.get_prefix(video_title)
                worker = ProcessWorker(
                    'cut',
                    input_path=video_path,
                    output_dir=out_dir,
                    clip_duration=cut_settings['duration'],
                    clip_count=cut_settings.get('clip_count', 0),
                    prefix=prefix,
                    reencode=cut_settings['reencode'],
                )
                worker.start()
                self._add_task(worker, '✂', 'Нарезка', os.path.basename(video_path))

            # ── КОМПОЗИЦИЯ / СТЕКИНГ ──
            if comp_settings:
                stack_center = center_path or video_path
                if not stack_center:
                    self._err_lbl.setText('⚠ Укажи главное видео в слоте ЦЕНТР')
                    continue

                out_file = os.path.join(out_dir, f'composed_{_sanitize(video_title)}.mp4')
                cut_after = comp_settings.get('cut_after', False)

                stack_kwargs = dict(
                    center_path   = stack_center,
                    output_path   = out_file,
                    top_path      = comp_settings.get('top_path'),
                    bottom_path   = comp_settings.get('bottom_path'),
                    output_width  = fmt_settings['output_width'],
                    output_height = fmt_settings['output_height'],
                    top_h         = fmt_settings['top_h'],
                    center_h      = fmt_settings['center_h'],
                    bottom_h      = fmt_settings['bottom_h'],
                    audio_source  = comp_settings.get('audio_source', 'center'),
                    bg_color      = fmt_settings['bg_color'],
                    quality       = fmt_settings['quality'],
                )
                if sub_settings and sub_settings.get('subtitle_path'):
                    stack_kwargs.update(
                        subtitle_path  = sub_settings['subtitle_path'],
                        subtitle_size  = sub_settings['subtitle_size'],
                        subtitle_color = sub_settings['subtitle_color'],
                    )

                # Если нужна нарезка после — используем stack_and_cut
                if cut_after:
                    # Используем встроенные настройки нарезки из панели Композиции
                    _cut_dur = comp_settings.get('cut_duration', 60)
                    _cut_cnt = comp_settings.get('cut_clip_count', 0)
                    _cut_re  = comp_settings.get('cut_reencode', False)
                    stack_kwargs.update(
                        cut_duration   = _cut_dur,
                        cut_count      = _cut_cnt,
                        cut_prefix     = _sanitize(video_title) or 'clip',
                        cut_reencode   = _cut_re,
                        cut_output_dir = os.path.join(out_dir, 'clips'),
                    )
                    op = 'stack_and_cut'
                    icon, label = '🎞✂', 'Композиция + Нарезка'
                else:
                    op = 'stack'
                    icon, label = '🎞', 'Композиция'

                worker = ProcessWorker(op, **stack_kwargs)
                worker.start()
                self._add_task(worker, icon, label, os.path.basename(video_path))

        self._no_tasks.hide()

    def _add_task(self, worker, icon, op, desc):
        card = TaskCard(icon, op, desc)
        card.attach(worker)
        card.cancel_requested.connect(lambda: self._remove_task(card))
        self._workers.append(worker)
        # Вставляем перед stretch
        count = self._tasks_lay.count()
        self._tasks_lay.insertWidget(count - 1, card)

    def _remove_task(self, card):
        self._tasks_lay.removeWidget(card)
        card.deleteLater()
        if self._tasks_lay.count() <= 1:
            self._no_tasks.show()


    def apply_preset(self, data: dict):
        """Применяет пресет настроек к странице обработки."""
        try:
            if data.get('clip_enabled'):
                self.cut_panel._enabled.setChecked(True)
                if data.get('clip_duration'):
                    self.cut_panel._duration.setValue(int(data['clip_duration']))
            if data.get('stack_enabled'):
                self.comp_panel._enabled.setChecked(True)
                if data.get('top_folder'):
                    self.comp_panel.slot_top.set_path(data['top_folder'])
                if data.get('bottom_folder'):
                    self.comp_panel.slot_bottom.set_path(data['bottom_folder'])
            if data.get('output_format'):
                fmt = data['output_format']
                if fmt in self.fmt_panel._fmt_btns:
                    self.fmt_panel._fmt_btns[fmt].setChecked(True)
                    self.fmt_panel._select(fmt)
        except Exception:
            pass
    def _clear_tasks(self):
        while self._tasks_lay.count() > 1:
            item = self._tasks_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._no_tasks.show()
        self._workers.clear()
