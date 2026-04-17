# processing_page.py — Страница обработки видео (редизайн v2)
#
# Два сегмента:
#   Сегмент 1 — НАРЕЗКА: выбор источника + параметры нарезки
#   Сегмент 2 — КОМПОЗИЦИЯ: главный ролик + баннер + удержание + фон + нарезка результата
#
# Настройки очистки: удалять скачанное / удалять после композиции

import os
import re
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QCheckBox,
    QComboBox, QListWidget, QListWidgetItem, QScrollArea,
    QFileDialog, QSizePolicy, QProgressBar,
    QButtonGroup, QRadioButton, QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont

from pages.base_page import BasePage
from db import db
from video_service import VideoService, ProcessWorker, is_ffmpeg_available

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.ts', '.flv'}
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ──────────────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────────────

PAGE_QSS = """
QWidget#proc_page { background: #171614; }

/* Заголовок сегмента */
QFrame#seg_header {
    background: #1c1b19;
    border: 1px solid #2d2c2a;
    border-radius: 10px 10px 0 0;
    border-bottom: none;
}
QLabel#seg_num {
    background: #4f98a3; color: #171614;
    font-size: 11px; font-weight: 800;
    border-radius: 10px;
    min-width: 20px; min-height: 20px;
    max-width: 20px; max-height: 20px;
    qproperty-alignment: AlignCenter;
}
QLabel#seg_title { color: #cdccca; font-size: 14px; font-weight: 700; }
QLabel#seg_sub   { color: #5a5957; font-size: 11px; }

/* Тело сегмента */
QFrame#seg_body {
    background: #1c1b19;
    border: 1px solid #2d2c2a;
    border-radius: 0 0 10px 10px;
}

/* Внутренняя карточка */
QFrame#inner_card {
    background: #201f1d;
    border: 1px solid #2d2c2a;
    border-radius: 8px;
}
QLabel#card_title {
    color: #797876; font-size: 10px;
    font-weight: 700; letter-spacing: 1px;
}

/* Переключатели режима источника */
QPushButton#mode_btn {
    background: #201f1d; color: #797876;
    border: 1px solid #2d2c2a; border-radius: 7px;
    font-size: 11px; font-weight: 600;
    padding: 8px 14px;
}
QPushButton#mode_btn:hover   { border-color: #4f98a3; color: #cdccca; }
QPushButton#mode_btn:checked {
    background: #1a3535; color: #4f98a3;
    border-color: #4f98a3; font-weight: 700;
}

/* Слот видео */
QFrame#slot_card {
    background: #201f1d; border: 1px solid #2d2c2a;
    border-radius: 8px;
}
QFrame#slot_card[filled="true"]    { border-color: #01696f; }
QFrame#slot_card[required="true"]  { border-left: 3px solid #4f98a3; }
QLabel#slot_title  { color: #797876; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; }
QLabel#slot_path   { color: #4f98a3; font-size: 11px; }
QLabel#slot_empty  { color: #3a3937; font-size: 11px; font-style: italic; }
QLabel#slot_info   { color: #5a5957; font-size: 10px; }
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

/* Список файлов (для папки/проект) */
QListWidget#file_list {
    background: #201f1d; border: 1px solid #2d2c2a;
    border-radius: 6px; color: #cdccca; font-size: 11px; outline: none;
}
QListWidget#file_list::item { padding: 5px 10px; border-radius: 4px; }
QListWidget#file_list::item:selected { background: #313b3b; color: #4f98a3; }
QListWidget#file_list::item:hover:!selected { background: #262523; }

/* Поля */
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

/* Разделитель */
QFrame#hdiv { background: #2d2c2a; max-height: 1px; border: none; }

/* Кнопки действий */
QPushButton#btn_start {
    background: #01696f; color: #f9f8f5; border: none;
    border-radius: 8px; font-size: 13px; font-weight: 700;
    padding: 12px 0; min-height: 44px;
}
QPushButton#btn_start:hover    { background: #0c4e54; }
QPushButton#btn_start:disabled { background: #2d2c2a; color: #5a5957; }

QPushButton#btn_secondary {
    background: #28251d; border: 1px solid #393836;
    border-radius: 7px; color: #cdccca; font-size: 12px; padding: 7px 16px;
}
QPushButton#btn_secondary:hover { background: #2d2c2a; border-color: #5a5957; }

/* Карточка задачи */
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
QProgressBar#task_bar {
    background: #2d2c2a; border: none; border-radius: 3px;
    max-height: 4px; min-height: 4px;
}
QProgressBar#task_bar::chunk { background: #4f98a3; border-radius: 3px; }

/* Правая панель задач */
QFrame#tasks_panel { background: #171614; border-left: 1px solid #2d2c2a; }
QLabel#tasks_title { color: #5a5957; font-size: 10px; font-weight: 700; letter-spacing: 0.8px; }
QLabel#no_tasks { color: #2d2c2a; font-size: 13px; }

/* Настройки очистки */
QFrame#cleanup_card {
    background: #1c1b19; border: 1px solid #2d2c2a;
    border-radius: 8px; border-left: 3px solid #bb653b;
}
QLabel#cleanup_title { color: #bb653b; font-size: 11px; font-weight: 700; }

/* Scroll */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 5px; }
QScrollBar::handle:vertical { background: #2d2c2a; border-radius: 2px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* Misc */
QLabel#lbl      { color: #797876; font-size: 12px; }
QLabel#hint     { color: #3a3937; font-size: 10px; font-style: italic; }
QLabel#badge_req { color: #bb653b; font-size: 9px; font-weight: 700;
                   background: #2a1a10; border-radius: 3px; padding: 1px 5px; }
QLabel#badge_opt { color: #5a5957; font-size: 9px; font-weight: 700;
                   background: #22211f; border-radius: 3px; padding: 1px 5px; }
"""


# ──────────────────────────────────────────────────────────────────────
# УТИЛИТЫ
# ──────────────────────────────────────────────────────────────────────

def _hdiv():
    f = QFrame(); f.setObjectName('hdiv')
    f.setFrameShape(QFrame.Shape.HLine)
    return f

def _lbl(text, obj='lbl'):
    l = QLabel(text); l.setObjectName(obj)
    return l

def _spin(mn, mx, val, suffix=''):
    s = QSpinBox(); s.setObjectName('spin')
    s.setRange(mn, mx); s.setValue(val)
    if suffix: s.setSuffix(suffix)
    return s

def _combo(items):
    c = QComboBox(); c.setObjectName('combo')
    for i in items: c.addItem(i)
    return c

def _sanitize(name: str) -> str:
    return re.sub(r'[/:*?<>|\\]', '_', name).strip()[:80]

def _pick_random_video(folder: str) -> Optional[str]:
    import random
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
    return random.choice(files) if files else None

def _scan_project_folders() -> dict:
    """Возвращает {папка_название: [список файлов]} из downloads/ и processed/."""
    result = {}
    for base in ['downloads', 'processed', 'clips']:
        base_path = os.path.join(BASE_DIR, base)
        if not os.path.isdir(base_path):
            continue
        for sub in os.listdir(base_path):
            sub_path = os.path.join(base_path, sub)
            if os.path.isdir(sub_path):
                files = [os.path.join(sub_path, f) for f in os.listdir(sub_path)
                         if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
                if files:
                    result[f'{base}/{sub}'] = files
        # Видео прямо в корне папки
        root_files = [os.path.join(base_path, f) for f in os.listdir(base_path)
                      if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
        if root_files:
            result[base] = root_files
    return result


# ──────────────────────────────────────────────────────────────────────
# ДИАЛОГ: ВЫБОР ВИДЕО ИЗ ПАПОК ПРОЕКТА
# ──────────────────────────────────────────────────────────────────────

class ProjectVideoPicker:
    def __new__(cls, parent=None):
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                      QComboBox, QListWidget, QListWidgetItem,
                                      QDialogButtonBox, QLabel, QSplitter)
        dlg = QDialog(parent)
        dlg.setWindowTitle('Выбрать видео из проекта')
        dlg.setMinimumSize(560, 420)
        dlg.setStyleSheet(PAGE_QSS + "QDialog{background:#1c1b19;}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(_lbl('Папка проекта:'))
        folder_combo = QComboBox(); folder_combo.setObjectName('combo')

        folders = _scan_project_folders()
        for folder_name, files in folders.items():
            folder_combo.addItem(f'📁  {folder_name}  ({len(files)} файлов)', files)

        if folder_combo.count() == 0:
            folder_combo.addItem('— нет видео в папках проекта —', [])

        lay.addWidget(folder_combo)

        vlist = QListWidget(); vlist.setObjectName('file_list')
        lay.addWidget(vlist)

        hint = _lbl('Двойной клик или ОК для выбора', 'hint')
        lay.addWidget(hint)

        dlg._selected = ''

        def _load(idx):
            vlist.clear()
            files = folder_combo.itemData(idx) or []
            for fp in files:
                item = QListWidgetItem(f'🎬  {os.path.basename(fp)}')
                item.setData(Qt.ItemDataRole.UserRole, fp)
                item.setToolTip(fp)
                vlist.addItem(item)

        folder_combo.currentIndexChanged.connect(_load)
        if folder_combo.count() > 0:
            _load(0)

        def _accept():
            sel = vlist.selectedItems()
            if sel:
                dlg._selected = sel[0].data(Qt.ItemDataRole.UserRole)
            dlg.accept()

        vlist.itemDoubleClicked.connect(lambda _: _accept())

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(_accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        dlg.selected_path = lambda: dlg._selected
        return dlg


# ──────────────────────────────────────────────────────────────────────
# ДИАЛОГ: ВЫБОР ИЗ СКАЧАННЫХ КАНАЛОВ
# ──────────────────────────────────────────────────────────────────────

class ChannelVideoPicker:
    def __new__(cls, parent=None):
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QComboBox,
                                      QListWidget, QListWidgetItem,
                                      QDialogButtonBox)
        dlg = QDialog(parent)
        dlg.setWindowTitle('Выбрать видео из канала')
        dlg.setMinimumSize(520, 400)
        dlg.setStyleSheet(PAGE_QSS + "QDialog{background:#1c1b19;}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lay.addWidget(_lbl('Канал:'))
        ch_combo = QComboBox(); ch_combo.setObjectName('combo')
        channels = []
        try:
            channels = db.get_all_channels()
        except Exception:
            pass
        for ch in channels:
            ch_combo.addItem(ch.get('title') or ch.get('url', '?'), ch['id'])
        if ch_combo.count() == 0:
            ch_combo.addItem('— нет каналов —', None)
        lay.addWidget(ch_combo)

        vlist = QListWidget(); vlist.setObjectName('file_list')
        lay.addWidget(vlist)

        dlg._selected = ''

        def _load(idx):
            vlist.clear()
            ch_id = ch_combo.itemData(idx)
            if ch_id is None:
                return
            try:
                videos = db.get_videos_by_channel(ch_id, status='downloaded')
                for v in videos:
                    fp = v.get('file_path', '')
                    if fp and os.path.isfile(fp):
                        item = QListWidgetItem(f'🎬  {v.get("title", os.path.basename(fp))}')
                        item.setData(Qt.ItemDataRole.UserRole, fp)
                        item.setToolTip(fp)
                        vlist.addItem(item)
            except Exception:
                pass

        ch_combo.currentIndexChanged.connect(_load)
        if ch_combo.count() > 0:
            _load(0)

        def _accept():
            sel = vlist.selectedItems()
            if sel:
                dlg._selected = sel[0].data(Qt.ItemDataRole.UserRole)
            dlg.accept()

        vlist.itemDoubleClicked.connect(lambda _: _accept())

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(_accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        dlg.selected_path = lambda: dlg._selected
        return dlg


# ──────────────────────────────────────────────────────────────────────
# ВИДЖЕТ СЛОТА ВИДЕО (один ролик с кнопками выбора)
# ──────────────────────────────────────────────────────────────────────

class VideoSlot(QFrame):
    """Слот для одного видеофайла с тремя способами выбора."""
    changed = pyqtSignal()

    def __init__(self, title='ВИДЕО', icon='🎬', required=False, parent=None):
        super().__init__(parent)
        self.setObjectName('slot_card')
        self._title_text = title
        self._icon = icon
        self._required = required
        self._path = ''
        self._is_folder = False
        self.setProperty('required', 'true' if required else 'false')
        self.setProperty('filled', 'false')
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # Заголовок строки
        hdr = QHBoxLayout(); hdr.setSpacing(6)
        icon_lbl = QLabel(self._icon)
        icon_lbl.setStyleSheet('font-size:14px;')
        hdr.addWidget(icon_lbl)
        t = QLabel(self._title_text); t.setObjectName('slot_title')
        hdr.addWidget(t)
        hdr.addStretch()
        badge = QLabel('обязательно' if self._required else 'необязательно')
        badge.setObjectName('badge_req' if self._required else 'badge_opt')
        hdr.addWidget(badge)
        self._clear_btn = QPushButton('✕')
        self._clear_btn.setObjectName('slot_clear')
        self._clear_btn.setFixedSize(22, 22)
        self._clear_btn.setToolTip('Очистить')
        self._clear_btn.clicked.connect(self.clear)
        self._clear_btn.hide()
        hdr.addWidget(self._clear_btn)
        lay.addLayout(hdr)

        # Путь
        self._path_lbl = QLabel('Не выбрано')
        self._path_lbl.setObjectName('slot_empty')
        self._path_lbl.setWordWrap(True)
        lay.addWidget(self._path_lbl)

        # Инфо
        self._info_lbl = QLabel('')
        self._info_lbl.setObjectName('slot_info')
        lay.addWidget(self._info_lbl)

        # Кнопки выбора
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        for text, tip, slot in [
            ('📄  Файл',    'Выбрать видеофайл с ПК',          self._pick_file),
            ('📁  Папка',   'Выбрать папку (случайное видео)',  self._pick_folder),
            ('📂  Проект',  'Выбрать из папок проекта',        self._pick_project),
            ('📺  Канал',   'Выбрать из скачанных каналов',    self._pick_channel),
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
        if path:
            self._set(path, is_folder=False)

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Выберите папку с видео')
        if path:
            self._set(path, is_folder=True)

    def _pick_project(self):
        dlg = ProjectVideoPicker(self)
        if dlg.exec():
            p = dlg.selected_path()
            if p:
                self._set(p, is_folder=False)

    def _pick_channel(self):
        dlg = ChannelVideoPicker(self)
        if dlg.exec():
            p = dlg.selected_path()
            if p:
                self._set(p, is_folder=False)

    def _set(self, path, is_folder=False):
        self._path = path
        self._is_folder = is_folder
        self.setProperty('filled', 'true')
        self.style().unpolish(self); self.style().polish(self)
        self._clear_btn.show()
        self._path_lbl.setObjectName('slot_path')
        if is_folder:
            try:
                files = [f for f in os.listdir(path)
                         if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
                self._path_lbl.setText(f'📁  {os.path.basename(path)}  ({len(files)} видео)')
                self._info_lbl.setText('Случайное видео при каждом запуске')
            except Exception:
                self._path_lbl.setText(f'📁  {path}')
        else:
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

    def resolve_path(self) -> Optional[str]:
        if not self._path: return None
        if self._is_folder: return _pick_random_video(self._path)
        return self._path

    def path(self) -> str: return self._path
    def is_empty(self) -> bool: return not bool(self._path)

    def set_path(self, path: str):
        if path: self._set(path, is_folder=os.path.isdir(path))


# ──────────────────────────────────────────────────────────────────────
# ИСТОЧНИК ВИДЕО — для сегмента «НАРЕЗКА» (множественный выбор)
# ──────────────────────────────────────────────────────────────────────

class SourceSelector(QFrame):
    """
    Выбор одного или нескольких видео для нарезки.
    Режимы: Файл | Папка | Из папок проекта
    """
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('inner_card')
        self._paths = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        t = QLabel('📥  ИСТОЧНИК ВИДЕО'); t.setObjectName('card_title')
        lay.addWidget(t)
        lay.addWidget(_hdiv())

        # Кнопки режима
        mode_row = QHBoxLayout(); mode_row.setSpacing(6)
        self._grp = QButtonGroup(self); self._grp.setExclusive(True)
        self._btns = {}
        for key, label in [
            ('file',    '📄  Файл'),
            ('folder',  '📁  Папка'),
            ('project', '📂  Папки проекта'),
        ]:
            btn = QPushButton(label); btn.setObjectName('mode_btn')
            btn.setCheckable(True); btn.setFixedHeight(34)
            self._grp.addButton(btn)
            self._btns[key] = btn
            mode_row.addWidget(btn)
        mode_row.addStretch()
        self._btns['file'].setChecked(True)
        lay.addLayout(mode_row)

        # Стек: одиночный / список
        self._single_row = QHBoxLayout(); self._single_row.setSpacing(6)
        self._single_edit = QLineEdit(); self._single_edit.setObjectName('field')
        self._single_edit.setPlaceholderText('Путь к видеофайлу...')
        self._single_edit.setReadOnly(True)
        self._single_row.addWidget(self._single_edit)
        pick_btn = QPushButton('Обзор'); pick_btn.setObjectName('btn_secondary')
        pick_btn.setFixedWidth(74); pick_btn.clicked.connect(self._pick_file)
        self._single_row.addWidget(pick_btn)
        self._single_w = QWidget(); self._single_w.setLayout(self._single_row)
        lay.addWidget(self._single_w)

        # Список файлов (папка / проект)
        self._list_w = QWidget()
        list_lay = QVBoxLayout(self._list_w); list_lay.setContentsMargins(0,0,0,0); list_lay.setSpacing(6)
        list_ctrl = QHBoxLayout(); list_ctrl.setSpacing(6)
        self._pick_folder_btn = QPushButton('📁  Выбрать папку')
        self._pick_folder_btn.setObjectName('btn_secondary')
        self._pick_folder_btn.clicked.connect(self._pick_folder)
        self._pick_project_btn = QPushButton('📂  Выбрать из проекта')
        self._pick_project_btn.setObjectName('btn_secondary')
        self._pick_project_btn.clicked.connect(self._pick_project_folder)
        self._clear_list_btn = QPushButton('Очистить')
        self._clear_list_btn.setObjectName('btn_secondary')
        self._clear_list_btn.clicked.connect(self._clear_list)
        list_ctrl.addWidget(self._pick_folder_btn)
        list_ctrl.addWidget(self._pick_project_btn)
        list_ctrl.addStretch()
        list_ctrl.addWidget(self._clear_list_btn)
        list_lay.addLayout(list_ctrl)

        self._file_list = QListWidget(); self._file_list.setObjectName('file_list')
        self._file_list.setMaximumHeight(160)
        list_lay.addWidget(self._file_list)
        self._list_hint = _lbl('Настройки применятся ко всем файлам', 'hint')
        list_lay.addWidget(self._list_hint)

        self._list_w.hide()
        lay.addWidget(self._list_w)

        # Подключаем переключатели
        self._btns['file'].toggled.connect(lambda c: self._on_mode('file', c))
        self._btns['folder'].toggled.connect(lambda c: self._on_mode('folder', c))
        self._btns['project'].toggled.connect(lambda c: self._on_mode('project', c))

    def _on_mode(self, mode, checked):
        if not checked: return
        self._single_w.setVisible(mode == 'file')
        self._list_w.setVisible(mode in ('folder', 'project'))
        if mode == 'folder':
            self._pick_folder_btn.show()
            self._pick_project_btn.hide()
        else:
            self._pick_folder_btn.hide()
            self._pick_project_btn.show()
        self._paths = []
        self._single_edit.clear()
        self._file_list.clear()
        self.changed.emit()

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Выберите видео', '',
            'Видео (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;Все файлы (*)'
        )
        if path:
            self._paths = [path]
            self._single_edit.setText(path)
            self.changed.emit()

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Выберите папку с видео')
        if folder:
            files = sorted([
                os.path.join(folder, f) for f in os.listdir(folder)
                if os.path.splitext(f)[1].lower() in VIDEO_EXTS
            ])
            self._paths = files
            self._populate_list(files)
            self.changed.emit()

    def _pick_project_folder(self):
        folders = _scan_project_folders()
        if not folders:
            return
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle('Выбрать папку проекта')
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet(PAGE_QSS + "QDialog{background:#1c1b19;}")
        dlg_lay = QVBoxLayout(dlg)
        dlg_lay.setContentsMargins(16, 16, 16, 16); dlg_lay.setSpacing(10)
        dlg_lay.addWidget(_lbl('Папка:'))
        combo = QComboBox(); combo.setObjectName('combo')
        for name, files in folders.items():
            combo.addItem(f'📁  {name}  ({len(files)} файлов)', files)
        dlg_lay.addWidget(combo)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        dlg_lay.addWidget(btns)
        if dlg.exec():
            files = combo.currentData() or []
            self._paths = files
            self._populate_list(files)
            self.changed.emit()

    def _populate_list(self, files):
        self._file_list.clear()
        for fp in files:
            item = QListWidgetItem(f'🎬  {os.path.basename(fp)}')
            item.setData(Qt.ItemDataRole.UserRole, fp)
            item.setToolTip(fp)
            self._file_list.addItem(item)

    def _clear_list(self):
        self._paths = []
        self._file_list.clear()
        self.changed.emit()

    def get_paths(self) -> list:
        return [p for p in self._paths if os.path.isfile(p)]

    def is_empty(self) -> bool:
        return len(self.get_paths()) == 0


# ──────────────────────────────────────────────────────────────────────
# НАСТРОЙКИ НАРЕЗКИ (переиспользуется в обоих сегментах)
# ──────────────────────────────────────────────────────────────────────

class CutSettings(QFrame):
    """Блок настроек нарезки: режим, длительность/кол-во, нумерация, имя."""

    def __init__(self, title='✂  НАРЕЗКА НА СЕГМЕНТЫ', parent=None):
        super().__init__(parent)
        self.setObjectName('inner_card')
        self._title = title
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)

        # Заголовок с переключателем вкл/выкл
        hdr = QHBoxLayout()
        self._enabled = QCheckBox(self._title)
        self._enabled.setObjectName('chk')
        self._enabled.setStyleSheet('QCheckBox{color:#cdccca;font-size:12px;font-weight:700;} '
                                     'QCheckBox::indicator{width:16px;height:16px;border-radius:4px;'
                                     'border:1px solid #393836;background:#201f1d;} '
                                     'QCheckBox::indicator:checked{background:#4f98a3;border-color:#4f98a3;}')
        self._enabled.toggled.connect(self._on_toggle)
        hdr.addWidget(self._enabled); hdr.addStretch()
        lay.addLayout(hdr)
        lay.addWidget(_hdiv())

        self._body = QWidget()
        body = QGridLayout(self._body)
        body.setSpacing(8); body.setColumnMinimumWidth(0, 140); body.setColumnStretch(1, 1)

        # Режим нарезки
        body.addWidget(_lbl('Режим нарезки:'), 0, 0)
        mode_w = QWidget(); ml = QHBoxLayout(mode_w)
        ml.setContentsMargins(0,0,0,0); ml.setSpacing(12)
        self._by_time  = QRadioButton('По длительности'); self._by_time.setObjectName('radio')
        self._by_count = QRadioButton('По количеству');   self._by_count.setObjectName('radio')
        self._by_time.setChecked(True)
        self._by_time.toggled.connect(self._on_mode_toggle)
        ml.addWidget(self._by_time); ml.addWidget(self._by_count); ml.addStretch()
        body.addWidget(mode_w, 0, 1)

        # Длительность
        self._dur_lbl = _lbl('Длительность (сек):')
        body.addWidget(self._dur_lbl, 1, 0)
        dur_w = QWidget(); dl = QHBoxLayout(dur_w)
        dl.setContentsMargins(0,0,0,0); dl.setSpacing(6)
        self._duration = _spin(1, 7200, 60, ' сек')
        dl.addWidget(self._duration)
        dl.addWidget(_lbl('(каждый сегмент)', 'hint'))
        dl.addStretch()
        body.addWidget(dur_w, 1, 1)

        # Количество
        self._cnt_lbl = _lbl('Количество сегментов:')
        body.addWidget(self._cnt_lbl, 2, 0)
        cnt_w = QWidget(); cl = QHBoxLayout(cnt_w)
        cl.setContentsMargins(0,0,0,0); cl.setSpacing(6)
        self._clip_count = _spin(2, 9999, 10, ' шт')
        cl.addWidget(self._clip_count)
        cl.addWidget(_lbl('длительность подстроится автоматически', 'hint'))
        cl.addStretch()
        body.addWidget(cnt_w, 2, 1)
        self._cnt_lbl.hide(); cnt_w.hide()
        self._cnt_w = cnt_w

        # Нумерация
        body.addWidget(_lbl('Нумерация:'), 3, 0)
        num_w = QWidget(); nl = QHBoxLayout(num_w)
        nl.setContentsMargins(0,0,0,0); nl.setSpacing(12)
        self._num_on  = QRadioButton('Включить  (001, 002...)'); self._num_on.setObjectName('radio')
        self._num_off = QRadioButton('Выключить'); self._num_off.setObjectName('radio')
        self._num_on.setChecked(True)
        nl.addWidget(self._num_on); nl.addWidget(self._num_off); nl.addStretch()
        body.addWidget(num_w, 3, 1)

        # Имя файла
        body.addWidget(_lbl('Имя файла:'), 4, 0)
        name_w = QWidget(); nml = QHBoxLayout(name_w)
        nml.setContentsMargins(0,0,0,0); nml.setSpacing(6)
        self._name_auto   = QRadioButton('Из исходного'); self._name_auto.setObjectName('radio')
        self._name_custom = QRadioButton('Своё:');        self._name_custom.setObjectName('radio')
        self._name_auto.setChecked(True)
        self._name_edit = QLineEdit(); self._name_edit.setObjectName('field')
        self._name_edit.setPlaceholderText('clip')
        self._name_edit.setEnabled(False)
        self._name_auto.toggled.connect(lambda c: self._name_edit.setEnabled(not c))
        nml.addWidget(self._name_auto); nml.addWidget(self._name_custom)
        nml.addWidget(self._name_edit); nml.addStretch()
        body.addWidget(name_w, 4, 1)

        # Перекодировка
        body.addWidget(_lbl('Перекодировать:'), 5, 0)
        self._reencode = QCheckBox('Libx264 (для дальнейшей склейки)')
        self._reencode.setObjectName('chk')
        body.addWidget(self._reencode, 5, 1)

        lay.addWidget(self._body)
        self._body.setEnabled(False)

    def _on_toggle(self, checked):
        self._body.setEnabled(checked)

    def _on_mode_toggle(self, time_checked):
        self._dur_lbl.setEnabled(time_checked)
        self._duration.setEnabled(time_checked)
        self._cnt_lbl.setVisible(not time_checked)
        self._cnt_w.setVisible(not time_checked)

    def is_enabled(self) -> bool:
        return self._enabled.isChecked()

    def get_prefix(self, original_title='') -> str:
        if self._name_auto.isChecked():
            return _sanitize(original_title) if original_title else 'clip'
        return _sanitize(self._name_edit.text().strip()) or 'clip'

    def get_settings(self) -> dict:
        by_count = self._by_count.isChecked()
        return {
            'enabled':    self.is_enabled(),
            'duration':   self._duration.value(),
            'clip_count': self._clip_count.value() if by_count else 0,
            'by_count':   by_count,
            'numbering':  self._num_on.isChecked(),
            'reencode':   self._reencode.isChecked(),
        }


# ──────────────────────────────────────────────────────────────────────
# СЕГМЕНТ 1: НАРЕЗКА
# ──────────────────────────────────────────────────────────────────────

class SegmentCut(QWidget):
    """
    Сегмент 1 — Нарезка:
      • Выбор источника (файл / папка / папки проекта)
      • Настройки нарезки на сегменты
      • Папка вывода
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Заголовок сегмента
        hdr = QFrame(); hdr.setObjectName('seg_header')
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 12, 16, 12)
        hdr_lay.setSpacing(10)
        num = QLabel('1'); num.setObjectName('seg_num')
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_lay.addWidget(num)
        info = QVBoxLayout(); info.setSpacing(2)
        info.addWidget(_make_seg_title('НАРЕЗКА'))
        info.addWidget(_lbl('Выберите видео и параметры нарезки на сегменты', 'seg_sub'))
        hdr_lay.addLayout(info)
        hdr_lay.addStretch()
        lay.addWidget(hdr)

        # Тело сегмента
        body = QFrame(); body.setObjectName('seg_body')
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 16, 16, 16)
        body_lay.setSpacing(12)

        # Источник
        self.source = SourceSelector()
        body_lay.addWidget(self.source)

        # Нарезка
        self.cut = CutSettings('✂  НАРЕЗКА НА СЕГМЕНТЫ')
        body_lay.addWidget(self.cut)

        # Папка вывода
        out_card = QFrame(); out_card.setObjectName('inner_card')
        out_lay = QVBoxLayout(out_card)
        out_lay.setContentsMargins(14, 12, 14, 12); out_lay.setSpacing(8)
        out_lay.addWidget(_lbl('💾  ПАПКА ВЫВОДА', 'card_title'))
        out_lay.addWidget(_hdiv())
        out_row = QHBoxLayout(); out_row.setSpacing(6)
        self._out_edit = QLineEdit(); self._out_edit.setObjectName('field')
        self._out_edit.setPlaceholderText('processed/  (авто)')
        out_row.addWidget(self._out_edit)
        out_btn = QPushButton('Обзор'); out_btn.setObjectName('btn_secondary')
        out_btn.setFixedWidth(74)
        out_btn.clicked.connect(self._browse_out)
        out_row.addWidget(out_btn)
        out_lay.addLayout(out_row)
        out_lay.addWidget(_lbl('Оставь пустым — сохранится в processed/название_видео', 'hint'))
        body_lay.addWidget(out_card)

        lay.addWidget(body)

    def _browse_out(self):
        p = QFileDialog.getExistingDirectory(self, 'Папка вывода')
        if p: self._out_edit.setText(p)

    def get_output_dir(self, title='') -> str:
        manual = self._out_edit.text().strip()
        if manual: return manual
        parts = [BASE_DIR, 'processed']
        if title: parts.append(_sanitize(title))
        return os.path.join(*parts)

    def is_ready(self) -> bool:
        return not self.source.is_empty() and self.cut.is_enabled()


# ──────────────────────────────────────────────────────────────────────
# СЕГМЕНТ 2: КОМПОЗИЦИЯ
# ──────────────────────────────────────────────────────────────────────

class SegmentCompose(QWidget):
    """
    Сегмент 2 — Композиция:
      • Главный ролик (центр)
      • Баннер (верх, вплотную к главному)
      • Видео удержания (низ, вплотную к главному)
      • Фон (закрывает промежутки)
      • Нарезка результата
      • Папка вывода
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Заголовок сегмента
        hdr = QFrame(); hdr.setObjectName('seg_header')
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 12, 16, 12)
        hdr_lay.setSpacing(10)
        num = QLabel('2'); num.setObjectName('seg_num')
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_lay.addWidget(num)
        info = QVBoxLayout(); info.setSpacing(2)
        info.addWidget(_make_seg_title('КОМПОЗИЦИЯ'))
        info.addWidget(_lbl('Сложите видео в вертикальный стек и нарежьте результат', 'seg_sub'))
        hdr_lay.addLayout(info)
        hdr_lay.addStretch()
        lay.addWidget(hdr)

        # Тело сегмента
        body = QFrame(); body.setObjectName('seg_body')
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 16, 16, 16)
        body_lay.setSpacing(12)

        # ── Схема композиции ──
        scheme_card = QFrame(); scheme_card.setObjectName('inner_card')
        scheme_lay = QVBoxLayout(scheme_card)
        scheme_lay.setContentsMargins(14, 12, 14, 12); scheme_lay.setSpacing(4)
        scheme_lay.addWidget(_lbl('🎨  СХЕМА СТЕКА', 'card_title'))
        scheme_lay.addWidget(_hdiv())
        scheme_info = QLabel(
            '  ┌─────────────────────┐\n'
            '  │   📢 БАННЕР (верх)  │  ← вплотную к главному\n'
            '  ├─────────────────────┤\n'
            '  │  🎬 ГЛАВНЫЙ РОЛИК   │  ← центр (обязательно)\n'
            '  ├─────────────────────┤\n'
            '  │  🎮 УДЕРЖАНИЕ (низ) │  ← вплотную к главному\n'
            '  └─────────────────────┘\n'
            '  🖼 ФОН — за всем стеком, закрывает промежутки'
        )
        scheme_info.setStyleSheet('color:#3a3937; font-size:11px; font-family:monospace;')
        scheme_lay.addWidget(scheme_info)
        body_lay.addWidget(scheme_card)

        # ── Слоты видео ──
        slots_card = QFrame(); slots_card.setObjectName('inner_card')
        slots_lay = QVBoxLayout(slots_card)
        slots_lay.setContentsMargins(14, 12, 14, 14); slots_lay.setSpacing(10)
        slots_lay.addWidget(_lbl('🎬  ВИДЕО СЛОТЫ', 'card_title'))
        slots_lay.addWidget(_hdiv())

        self.slot_main   = VideoSlot('ГЛАВНЫЙ РОЛИК  —  по центру',  '🎬', required=True)
        self.slot_banner = VideoSlot('БАННЕР  —  сверху вплотную',   '📢', required=False)
        self.slot_hold   = VideoSlot('УДЕРЖАНИЕ  —  снизу вплотную', '🎮', required=False)
        self.slot_bg     = VideoSlot('ФОН  —  задний план',          '🖼', required=False)

        slots_lay.addWidget(self.slot_main)
        slots_lay.addWidget(self.slot_banner)
        slots_lay.addWidget(self.slot_hold)
        slots_lay.addWidget(self.slot_bg)
        body_lay.addWidget(slots_card)

        # ── Аудио + формат ──
        af_card = QFrame(); af_card.setObjectName('inner_card')
        af_lay = QVBoxLayout(af_card)
        af_lay.setContentsMargins(14, 12, 14, 12); af_lay.setSpacing(8)
        af_lay.addWidget(_lbl('⚙  НАСТРОЙКИ РЕНДЕРА', 'card_title'))
        af_lay.addWidget(_hdiv())
        af_grid = QGridLayout(); af_grid.setSpacing(8)
        af_grid.setColumnMinimumWidth(0, 140); af_grid.setColumnStretch(1, 1)

        af_grid.addWidget(_lbl('Источник аудио:'), 0, 0)
        self._audio = _combo(['Главный ролик (центр)', 'Баннер (верх)', 'Удержание (низ)', 'Без звука'])
        af_grid.addWidget(self._audio, 0, 1)

        af_grid.addWidget(_lbl('Формат вывода:'), 1, 0)
        self._fmt = _combo(['TikTok  9:16  1080×1920', 'Reels  9:16  1080×1920',
                            'Shorts  9:16  1080×1920', 'Квадрат  1:1  1080×1080',
                            'YouTube  16:9  1920×1080', 'Оригинал'])
        af_grid.addWidget(self._fmt, 1, 1)

        af_grid.addWidget(_lbl('Цвет фона:'), 2, 0)
        self._bg_color = _combo(['Чёрный', 'Белый', 'Серый'])
        af_grid.addWidget(self._bg_color, 2, 1)

        af_grid.addWidget(_lbl('Качество:'), 3, 0)
        self._quality = _combo(['Быстро (fast)', 'Хорошо (medium)', 'Лучшее (slow)'])
        af_grid.addWidget(self._quality, 3, 1)

        af_lay.addLayout(af_grid)
        body_lay.addWidget(af_card)

        # ── Нарезка результата ──
        self.cut = CutSettings('✂  НАРЕЗАТЬ РЕЗУЛЬТАТ ПОСЛЕ РЕНДЕРА')
        body_lay.addWidget(self.cut)

        # ── Папка вывода ──
        out_card = QFrame(); out_card.setObjectName('inner_card')
        out_lay = QVBoxLayout(out_card)
        out_lay.setContentsMargins(14, 12, 14, 12); out_lay.setSpacing(8)
        out_lay.addWidget(_lbl('💾  ПАПКА ВЫВОДА', 'card_title'))
        out_lay.addWidget(_hdiv())
        out_row = QHBoxLayout(); out_row.setSpacing(6)
        self._out_edit = QLineEdit(); self._out_edit.setObjectName('field')
        self._out_edit.setPlaceholderText('processed/composition/  (авто)')
        out_row.addWidget(self._out_edit)
        out_btn = QPushButton('Обзор'); out_btn.setObjectName('btn_secondary')
        out_btn.setFixedWidth(74)
        out_btn.clicked.connect(self._browse_out)
        out_row.addWidget(out_btn)
        out_lay.addLayout(out_row)
        out_lay.addWidget(_lbl('Оставь пустым — сохранится в processed/composition/', 'hint'))
        body_lay.addWidget(out_card)

        lay.addWidget(body)

    def _browse_out(self):
        p = QFileDialog.getExistingDirectory(self, 'Папка вывода')
        if p: self._out_edit.setText(p)

    def get_output_dir(self) -> str:
        manual = self._out_edit.text().strip()
        if manual: return manual
        return os.path.join(BASE_DIR, 'processed', 'composition')

    def get_render_settings(self) -> dict:
        fmt_map = {
            0: {'w': 1080, 'h': 1920, 'key': 'tiktok'},
            1: {'w': 1080, 'h': 1920, 'key': 'reels'},
            2: {'w': 1080, 'h': 1920, 'key': 'shorts'},
            3: {'w': 1080, 'h': 1080, 'key': 'square'},
            4: {'w': 1920, 'h': 1080, 'key': 'youtube'},
            5: {'w': 0,    'h': 0,    'key': 'original'},
        }
        fmt = fmt_map.get(self._fmt.currentIndex(), fmt_map[0])
        quality_map = {'Быстро (fast)': 'fast', 'Хорошо (medium)': 'medium', 'Лучшее (slow)': 'slow'}
        bg_map = {'Чёрный': 'black', 'Белый': 'white', 'Серый': 'gray'}
        audio_map = ['center', 'top', 'bottom', 'none']
        return {
            'output_width':  fmt['w'],
            'output_height': fmt['h'],
            'format_key':    fmt['key'],
            'quality':       quality_map.get(self._quality.currentText(), 'fast'),
            'bg_color':      bg_map.get(self._bg_color.currentText(), 'black'),
            'audio_source':  audio_map[self._audio.currentIndex()],
            'main_path':     self.slot_main.resolve_path(),
            'top_path':      self.slot_banner.resolve_path(),
            'bottom_path':   self.slot_hold.resolve_path(),
            'bg_path':       self.slot_bg.resolve_path(),
        }

    def is_ready(self) -> bool:
        return not self.slot_main.is_empty()


# ──────────────────────────────────────────────────────────────────────
# ПАНЕЛЬ ОЧИСТКИ
# ──────────────────────────────────────────────────────────────────────

class CleanupPanel(QFrame):
    """Настройки автоматического удаления файлов после обработки."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('cleanup_card')
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        hdr = QHBoxLayout(); hdr.setSpacing(8)
        hdr.addWidget(QLabel('🗑')); hdr.addWidget(_lbl('АВТООЧИСТКА', 'cleanup_title'))
        hdr.addStretch()
        lay.addLayout(hdr)
        lay.addWidget(_hdiv())
        lay.addWidget(_lbl('После завершения нарезки автоматически удалять:', 'hint'))

        self._del_downloaded = QCheckBox('Удалять скачанные видео (downloads/)')
        self._del_downloaded.setObjectName('chk')
        self._del_downloaded.setToolTip(
            'Удалить исходные файлы из папки downloads/ после того, как нарезка завершена'
        )
        lay.addWidget(self._del_downloaded)

        self._del_composed = QCheckBox('Удалять видео после композиции (processed/composition/)')
        self._del_composed.setObjectName('chk')
        self._del_composed.setToolTip(
            'Удалить результат рендера композиции после того, как он нарезан на клипы'
        )
        lay.addWidget(self._del_composed)

        warn = _lbl('⚠  Удаление необратимо — убедитесь что нарезка прошла успешно', 'hint')
        warn.setStyleSheet('color:#bb653b; font-size:10px;')
        lay.addWidget(warn)

    def get_settings(self) -> dict:
        return {
            'delete_downloaded': self._del_downloaded.isChecked(),
            'delete_composed':   self._del_composed.isChecked(),
        }


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
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self.cancel_requested.emit()


# ──────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ЗАГОЛОВКОВ
# ──────────────────────────────────────────────────────────────────────

def _make_seg_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName('seg_title')
    return lbl


# ──────────────────────────────────────────────────────────────────────
# ГЛАВНАЯ СТРАНИЦА ОБРАБОТКИ
# ──────────────────────────────────────────────────────────────────────

class ProcessingPage(BasePage):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self._workers = []
        self._build()
        self.setStyleSheet(PAGE_QSS)
        self.setObjectName('proc_page')

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Левая колонка: прокручиваемые настройки ──
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(440)
        # Без MaximumWidth — левая колонка растягивается на всё доступное пространство

        left_inner = QWidget(); left_inner.setObjectName('proc_page')
        left_lay = QVBoxLayout(left_inner)
        left_lay.setContentsMargins(16, 16, 16, 16)
        left_lay.setSpacing(20)

        # Заголовок страницы
        page_hdr = QFrame()
        page_hdr.setStyleSheet('background: #1c1b19; border-bottom: 1px solid #2d2c2a; border-radius: 0;')
        ph_lay = QHBoxLayout(page_hdr); ph_lay.setContentsMargins(4, 8, 4, 12)
        ph_info = QVBoxLayout(); ph_info.setSpacing(2)
        title_lbl = QLabel('⚙  Обработка видео')
        title_lbl.setStyleSheet('color:#cdccca; font-size:15px; font-weight:700;')
        sub_lbl = QLabel('Нарезка исходников и сборка вертикального стека')
        sub_lbl.setStyleSheet('color:#5a5957; font-size:11px;')
        ph_info.addWidget(title_lbl); ph_info.addWidget(sub_lbl)
        ph_lay.addLayout(ph_info); ph_lay.addStretch()
        left_lay.addWidget(page_hdr)

        # Сегмент 1: Нарезка
        self.seg_cut = SegmentCut()
        left_lay.addWidget(self.seg_cut)

        # Сегмент 2: Композиция
        self.seg_compose = SegmentCompose()
        left_lay.addWidget(self.seg_compose)

        # Автоочистка
        self.cleanup = CleanupPanel()
        left_lay.addWidget(self.cleanup)

        # Кнопки запуска
        btn_card = QFrame(); btn_card.setObjectName('inner_card')
        btn_lay = QVBoxLayout(btn_card)
        btn_lay.setContentsMargins(14, 12, 14, 14); btn_lay.setSpacing(8)

        self._btn_cut = QPushButton('✂  Запустить нарезку  (Сегмент 1)')
        self._btn_cut.setObjectName('btn_start')
        self._btn_cut.clicked.connect(self._run_cut)
        btn_lay.addWidget(self._btn_cut)

        self._btn_compose = QPushButton('🎞  Запустить композицию  (Сегмент 2)')
        self._btn_compose.setObjectName('btn_start')
        self._btn_compose.setStyleSheet(
            'QPushButton#btn_start{background:#437a22;}'
            'QPushButton#btn_start:hover{background:#2e5c10;}'
            'QPushButton#btn_start:disabled{background:#2d2c2a;color:#5a5957;}'
        )
        self._btn_compose.clicked.connect(self._run_compose)
        btn_lay.addWidget(self._btn_compose)

        left_lay.addWidget(btn_card)
        left_lay.addStretch()

        left_scroll.setWidget(left_inner)
        root.addWidget(left_scroll, stretch=1)  # занимает всё доступное место

        # ── Правая колонка: активные задачи ──
        right = QFrame(); right.setObjectName('tasks_panel')
        right.setFixedWidth(300)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(12, 16, 12, 16)
        right_lay.setSpacing(10)

        tasks_hdr = QLabel('ЗАДАЧИ'); tasks_hdr.setObjectName('tasks_title')
        right_lay.addWidget(tasks_hdr)
        right_lay.addWidget(_hdiv())

        self._tasks_scroll = QScrollArea()
        self._tasks_scroll.setWidgetResizable(True)
        self._tasks_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tasks_inner = QWidget()
        self._tasks_lay = QVBoxLayout(self._tasks_inner)
        self._tasks_lay.setContentsMargins(0, 0, 0, 0)
        self._tasks_lay.setSpacing(8)
        self._tasks_lay.addStretch()
        self._tasks_scroll.setWidget(self._tasks_inner)
        right_lay.addWidget(self._tasks_scroll, stretch=1)  # растягивается по высоте

        self._no_tasks_lbl = QLabel('Нет активных задач')
        self._no_tasks_lbl.setObjectName('no_tasks')
        self._no_tasks_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_lay.addWidget(self._no_tasks_lbl)

        root.addWidget(right)

    # ── Запуск нарезки ─────────────────────────────────────────────

    def _run_cut(self):
        if self.seg_cut.source.is_empty():
            self._show_error('Выберите видео в Сегменте 1 (Источник видео)')
            return
        if not self.seg_cut.cut.is_enabled():
            self._show_error('Включите нарезку в Сегменте 1')
            return

        paths = self.seg_cut.source.get_paths()
        cut_cfg = self.seg_cut.cut.get_settings()
        cleanup = self.cleanup.get_settings()

        for path in paths:
            title = os.path.splitext(os.path.basename(path))[0]
            out_dir = self.seg_cut.get_output_dir(title)
            os.makedirs(out_dir, exist_ok=True)
            prefix = self.seg_cut.cut.get_prefix(title)

            # ProcessWorker(operation, **kwargs) — operation первым аргументом
            # cut_video принимает: input_path, output_dir, clip_duration, clip_count, prefix, reencode
            clip_duration = cut_cfg.get('duration', 60)
            clip_count    = cut_cfg.get('clip_count', 0) if cut_cfg.get('by_count') else 0

            worker = ProcessWorker(
                'cut',
                input_path    = path,
                output_dir    = out_dir,
                prefix        = prefix,
                clip_duration = clip_duration,
                clip_count    = clip_count,
                reencode      = cut_cfg.get('reencode', False),
            )
            card = TaskCard('✂', 'Нарезка', os.path.basename(path))
            card.attach(worker)
            card.cancel_requested.connect(lambda c=card: self._remove_task(c))
            self._add_task(card)
            self._workers.append(worker)
            worker.start()

            # Автоочистка после завершения
            if cleanup.get('delete_downloaded'):
                worker.finished.connect(lambda _, p=path: self._safe_delete(p))

    # ── Запуск композиции ──────────────────────────────────────────

    def _run_compose(self):
        if self.seg_compose.slot_main.is_empty():
            self._show_error('Выберите главный ролик в Сегменте 2 (Главный ролик — центр)')
            return

        render  = self.seg_compose.get_render_settings()
        cut_cfg = self.seg_compose.cut.get_settings()
        cleanup = self.cleanup.get_settings()
        out_dir = self.seg_compose.get_output_dir()
        os.makedirs(out_dir, exist_ok=True)

        main_path = render['main_path']
        if not main_path:
            self._show_error('Не удалось определить путь к главному ролику')
            return

        main_name = os.path.splitext(os.path.basename(main_path))[0]
        prefix    = self.seg_compose.cut.get_prefix(main_name)

        # stack_output_path — путь к результату стекинга
        stack_out = os.path.join(out_dir, f'{_sanitize(main_name)}_composed.mp4')

        # Новый stack_videos сам читает размеры видео — не нужно передавать top_h/center_h/bottom_h
        # output_width/output_height — размер итогового холста (экрана)
        out_w = render.get('output_width', 1080)
        out_h = render.get('output_height', 1920)
        # Для 'original' берём размеры самого главного видео
        if render.get('format_key') == 'original' or (out_w == 0 and out_h == 0):
            try:
                ci = VideoService().get_video_info(main_path)
                out_w = ci.width  or 1080
                out_h = ci.height or 1920
            except Exception:
                out_w, out_h = 1080, 1920

        if cut_cfg.get('enabled'):
            clip_duration = cut_cfg.get('duration', 60)
            clip_count    = cut_cfg.get('clip_count', 0) if cut_cfg.get('by_count') else 0
            worker = ProcessWorker(
                'stack_and_cut',
                center_path    = main_path,
                output_path    = stack_out,
                top_path       = render.get('top_path'),
                bottom_path    = render.get('bottom_path'),
                bg_path        = render.get('bg_path'),
                output_width   = out_w,
                output_height  = out_h,
                audio_source   = render.get('audio_source', 'center'),
                bg_color       = render.get('bg_color', 'black'),
                quality        = render.get('quality', 'fast'),
                cut_duration   = clip_duration,
                cut_count      = clip_count,
                cut_prefix     = prefix,
                cut_reencode   = cut_cfg.get('reencode', False),
                cut_output_dir = out_dir,
            )
        else:
            worker = ProcessWorker(
                'stack',
                center_path   = main_path,
                output_path   = stack_out,
                top_path      = render.get('top_path'),
                bottom_path   = render.get('bottom_path'),
                bg_path       = render.get('bg_path'),
                output_width  = out_w,
                output_height = out_h,
                audio_source  = render.get('audio_source', 'center'),
                bg_color      = render.get('bg_color', 'black'),
                quality       = render.get('quality', 'fast'),
            )

        card = TaskCard('🎞', 'Композиция', main_name)
        card.attach(worker)
        card.cancel_requested.connect(lambda c=card: self._remove_task(c))
        self._add_task(card)
        self._workers.append(worker)
        worker.start()

        # Автоочистка скомпонованного файла после нарезки
        if cleanup.get('delete_composed') and cut_cfg.get('enabled'):
            worker.finished.connect(lambda _, p=stack_out: self._safe_delete(p))

    # ── Управление карточками задач ────────────────────────────────

    def _add_task(self, card: TaskCard):
        self._no_tasks_lbl.hide()
        self._tasks_lay.insertWidget(self._tasks_lay.count() - 1, card)

    def _remove_task(self, card: TaskCard):
        card.setParent(None)
        card.deleteLater()
        if self._tasks_lay.count() <= 1:
            self._no_tasks_lbl.show()

    def _safe_delete(self, path: str):
        """Безопасно удаляет файл если он существует."""
        try:
            if path and os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass

    def _show_error(self, msg: str):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(self, 'Ошибка', msg)
