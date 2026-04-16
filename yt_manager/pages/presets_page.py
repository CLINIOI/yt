# presets_page.py — Страница пресетов
#
# PresetCardWidget  — карточка в списке слева
# SettingsEditor    — форма редактора (4 вкладки)
# PresetsPage       — главная страница

import os
import json
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QSpinBox,
    QCheckBox, QComboBox, QListWidget, QListWidgetItem,
    QTabWidget, QFileDialog, QScrollArea, QSizePolicy,
    QSplitter, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor

from pages.base_page import BasePage
from db import db
from presets import (
    export_preset_file, export_all_presets_file,
    import_preset_file, apply_preset_to_config,
    DEFAULT_PRESET,
)

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'config.json',
)


# ──────────────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────────────

PAGE_STYLE = '''
QFrame#presets_toolbar { background:#1c1b19; border-bottom:1px solid #2d2c2a; }
QLabel#presets_title   { color:#cdccca; font-size:16px; font-weight:700; }

/* Список */
QListWidget#preset_list {
    background:#1c1b19; border:none;
    outline:none;
}
QListWidget#preset_list::item { border-radius:8px; padding:2px; }
QListWidget#preset_list::item:selected { background:transparent; }

/* Карточка */
QFrame#preset_card {
    background:#201f1d; border:1px solid #2d2c2a;
    border-radius:8px;
}
QFrame#preset_card[selected=true] {
    background:#1f2d2d; border-color:#4f98a3;
}
QLabel#card_name  { color:#cdccca; font-size:13px; font-weight:600; }
QLabel#card_desc  { color:#5a5957; font-size:11px; }
QLabel#card_date  { color:#3a3937; font-size:10px; }

/* Редактор */
QFrame#editor_panel { background:#171614; }
QFrame#editor_header {
    background:#1c1b19; border-bottom:1px solid #2d2c2a;
}
QLabel#editor_hint { color:#3a3937; font-size:13px; }

QLineEdit#ed_input {
    background:#201f1d; border:1px solid #393836;
    border-radius:6px; color:#cdccca;
    font-size:13px; padding:7px 10px;
}
QLineEdit#ed_input:focus { border-color:#4f98a3; }

QTextEdit#ed_textarea {
    background:#201f1d; border:1px solid #393836;
    border-radius:6px; color:#797876;
    font-size:12px; padding:8px 10px;
}
QTextEdit#ed_textarea:focus { border-color:#4f98a3; }

QTabWidget#settings_tabs::pane {
    background:#1c1b19; border:none;
}
QTabWidget#settings_tabs QTabBar::tab {
    background:#201f1d; color:#5a5957;
    padding:7px 16px; border:none;
    font-size:12px; font-weight:600;
}
QTabWidget#settings_tabs QTabBar::tab:selected {
    background:#1c1b19; color:#cdccca;
    border-bottom:2px solid #4f98a3;
}
QTabWidget#settings_tabs QTabBar::tab:hover:!selected { color:#cdccca; }

/* Секции в табах */
QLabel#tab_sec {
    color:#5a5957; font-size:10px; font-weight:700;
    letter-spacing:0.7px;
}
QFrame#tab_div { background:#2d2c2a; max-height:1px; }
QLabel#tab_field { color:#797876; font-size:12px; }

QSpinBox#ed_spin {
    background:#201f1d; border:1px solid #393836;
    border-radius:6px; color:#cdccca;
    font-size:12px; padding:5px 8px; min-width:80px;
}
QSpinBox#ed_spin:focus { border-color:#4f98a3; }
QSpinBox#ed_spin::up-button, QSpinBox#ed_spin::down-button {
    width:16px; border:none; background:#2d2c2a; border-radius:3px;
}

QCheckBox#ed_check {
    color:#cdccca; font-size:12px; spacing:8px;
}
QCheckBox#ed_check::indicator {
    width:16px; height:16px; border-radius:4px;
    border:1px solid #393836; background:#201f1d;
}
QCheckBox#ed_check::indicator:checked {
    background:#4f98a3; border-color:#4f98a3;
}

QComboBox#ed_combo {
    background:#201f1d; border:1px solid #393836;
    border-radius:6px; color:#cdccca;
    font-size:12px; padding:5px 10px;
}
QComboBox#ed_combo:focus { border-color:#4f98a3; }
QComboBox#ed_combo::drop-down { border:none; width:20px; }
QComboBox QAbstractItemView {
    background:#201f1d; color:#cdccca;
    border:1px solid #393836; outline:none;
}

QLineEdit#path_input {
    background:#201f1d; border:1px solid #393836;
    border-radius:6px; color:#cdccca;
    font-size:11px; padding:5px 8px;
}
QLineEdit#path_input:focus { border-color:#4f98a3; }

/* Action buttons */
QPushButton#save_btn {
    background:#01696f; color:#f9f8f5;
    border:none; border-radius:7px;
    font-size:13px; font-weight:700;
    padding:9px 20px;
}
QPushButton#save_btn:hover    { background:#0c4e54; }
QPushButton#save_btn:disabled { background:#2d2c2a; color:#5a5957; }

QPushButton#apply_btn {
    background:#2d2c2a; color:#4f98a3;
    border:1px solid #4f98a3; border-radius:7px;
    font-size:13px; font-weight:600;
    padding:9px 20px;
}
QPushButton#apply_btn:hover    { background:#313b3b; }
QPushButton#apply_btn:disabled { border-color:#2d2c2a; color:#3a3937; }

QPushButton#del_btn {
    background:transparent; color:#5a5957;
    border:1px solid #393836; border-radius:7px;
    font-size:13px; padding:9px 16px;
}
QPushButton#del_btn:hover { color:#dd6974; border-color:#dd6974; }

QPushButton#toolbar_btn {
    background:#2d2c2a; color:#797876;
    border:none; border-radius:6px;
    font-size:12px; padding:5px 12px;
}
QPushButton#toolbar_btn:hover { background:#393836; color:#cdccca; }

QPushButton#new_btn {
    background:#01696f; color:#f9f8f5;
    border:none; border-radius:6px;
    font-size:12px; font-weight:600; padding:5px 14px;
}
QPushButton#new_btn:hover { background:#0c4e54; }

/* Unsaved dot */
QLabel#unsaved_dot { color:#e8af34; font-size:14px; }

/* Scroll */
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { background:transparent; width:5px; }
QScrollBar::handle:vertical {
    background:#393836; border-radius:2px; min-height:20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
'''


# ──────────────────────────────────────────────────────────────────────
# КАРТОЧКА ПРЕСЕТА
# ──────────────────────────────────────────────────────────────────────

class PresetCardWidget(QFrame):
    def __init__(self, preset: dict, parent=None):
        super().__init__(parent)
        self.setObjectName('preset_card')
        self._preset = preset
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(2)

        name = self._preset.get('name', '—')
        desc = self._preset.get('description', '')
        raw_date = str(self._preset.get('created_at', '') or '')[:10]
        date_str  = raw_date or '—'

        name_lbl = QLabel(name)
        name_lbl.setObjectName('card_name')
        lay.addWidget(name_lbl)

        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setObjectName('card_desc')
            desc_lbl.setWordWrap(True)
            lay.addWidget(desc_lbl)

        date_lbl = QLabel(f'Создан: {date_str}')
        date_lbl.setObjectName('card_date')
        lay.addWidget(date_lbl)

    def set_selected(self, selected: bool):
        self.setProperty('selected', 'true' if selected else 'false')
        self.setStyleSheet(self.styleSheet())

    def preset(self) -> dict:
        return self._preset


# ──────────────────────────────────────────────────────────────────────
# ФОРМА РЕДАКТОРА НАСТРОЕК (4 ВКЛАДКИ)
# ──────────────────────────────────────────────────────────────────────

def _sec(text):
    lbl = QLabel(text.upper())
    lbl.setObjectName('tab_sec')
    div = QFrame()
    div.setObjectName('tab_div')
    div.setFixedHeight(1)
    return lbl, div

def _field(text):
    l = QLabel(text)
    l.setObjectName('tab_field')
    return l

def _spin(lo, hi, val, suffix=''):
    s = QSpinBox()
    s.setObjectName('ed_spin')
    s.setRange(lo, hi)
    s.setValue(val)
    if suffix: s.setSuffix(suffix)
    return s


class SettingsEditor(QWidget):
    changed = pyqtSignal()   # любое изменение поля

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._connect_signals()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setObjectName('settings_tabs')
        self._tabs.addTab(self._build_cut_tab(),   '✂  Нарезка')
        self._tabs.addTab(self._build_merge_tab(), '🔗 Склейка')
        self._tabs.addTab(self._build_stack_tab(), '⊞  Стекинг')
        self._tabs.addTab(self._build_paths_tab(), '📁 Папки')
        lay.addWidget(self._tabs)

    # ── Вкладка: Нарезка ─────────────────────────────────────────────
    def _build_cut_tab(self) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 20)
        lay.setSpacing(8)

        lbl, div = _sec('Нарезка')
        lay.addWidget(lbl); lay.addWidget(div)

        g = QGridLayout()
        g.setVerticalSpacing(6); g.setHorizontalSpacing(10)
        g.addWidget(_field('Длительность клипа'), 0, 0)
        self._cut_dur = _spin(1, 3600, 60, ' сек')
        g.addWidget(self._cut_dur, 0, 1)
        g.addWidget(_field('Префикс'), 1, 0)
        self._cut_prefix = QLineEdit('clip')
        self._cut_prefix.setObjectName('ed_input')
        self._cut_prefix.setMaximumWidth(140)
        g.addWidget(self._cut_prefix, 1, 1)
        lay.addLayout(g)

        self._cut_reencode = QCheckBox('Перекодировать (libx264)')
        self._cut_reencode.setObjectName('ed_check')
        lay.addWidget(self._cut_reencode)
        lay.addStretch()
        sa.setWidget(w)
        return sa

    # ── Вкладка: Склейка ──────────────────────────────────────────────
    def _build_merge_tab(self) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 20)
        lay.setSpacing(8)

        lbl, div = _sec('Склейка')
        lay.addWidget(lbl); lay.addWidget(div)

        self._merge_reencode = QCheckBox('Перекодировать (для разных форматов)')
        self._merge_reencode.setObjectName('ed_check')
        lay.addWidget(self._merge_reencode)
        lay.addStretch()
        sa.setWidget(w)
        return sa

    # ── Вкладка: Стекинг ──────────────────────────────────────────────
    def _build_stack_tab(self) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 20)
        lay.setSpacing(8)

        lbl, div = _sec('Стекинг')
        lay.addWidget(lbl); lay.addWidget(div)

        g = QGridLayout()
        g.setVerticalSpacing(6); g.setHorizontalSpacing(10)

        g.addWidget(_field('Соотношение Верх'), 0, 0)
        self._st_top = _spin(0, 20, 1)
        g.addWidget(self._st_top, 0, 1)

        g.addWidget(_field('Соотношение Центр'), 1, 0)
        self._st_center = _spin(1, 20, 3)
        g.addWidget(self._st_center, 1, 1)

        g.addWidget(_field('Соотношение Низ'), 2, 0)
        self._st_bottom = _spin(0, 20, 1)
        g.addWidget(self._st_bottom, 2, 1)

        g.addWidget(_field('Ширина'), 3, 0)
        self._st_width = _spin(360, 4096, 1080, ' px')
        g.addWidget(self._st_width, 3, 1)

        g.addWidget(_field('Высота'), 4, 0)
        self._st_height = _spin(360, 8192, 1920, ' px')
        g.addWidget(self._st_height, 4, 1)

        g.addWidget(_field('Аудио из'), 5, 0)
        self._st_audio = QComboBox()
        self._st_audio.setObjectName('ed_combo')
        self._st_audio.addItems(['Центр', 'Верх', 'Низ'])
        g.addWidget(self._st_audio, 5, 1)
        lay.addLayout(g)
        lay.addStretch()
        sa.setWidget(w)
        return sa

    # ── Вкладка: Папки ────────────────────────────────────────────────
    def _build_paths_tab(self) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 20)
        lay.setSpacing(8)

        lbl, div = _sec('Пути к папкам')
        lay.addWidget(lbl); lay.addWidget(div)

        self._paths: dict[str, QLineEdit] = {}
        for key, label in [
            ('downloads',   '📥  Загрузки'),
            ('processed',   '⚙   Обработанные'),
            ('backgrounds', '🖼  Фоны'),
            ('banners',     '🏷  Баннеры'),
        ]:
            lay.addWidget(_field(label))
            row = QHBoxLayout()
            row.setSpacing(6)
            edit = QLineEdit()
            edit.setObjectName('path_input')
            edit.setPlaceholderText(f'./{key}')
            self._paths[key] = edit
            row.addWidget(edit)
            browse = QPushButton('Обзор')
            browse.setObjectName('toolbar_btn')
            browse.setFixedWidth(60)
            _key = key
            browse.clicked.connect(
                lambda _, k=_key: self._browse_path(k))
            row.addWidget(browse)
            lay.addLayout(row)
        lay.addStretch()
        sa.setWidget(w)
        return sa

    def _browse_path(self, key: str):
        p = QFileDialog.getExistingDirectory(
            self, f'Выберите папку для {key}',
            self._paths[key].text() or os.path.expanduser('~'),
        )
        if p:
            self._paths[key].setText(p)
            self.changed.emit()

    # ── Сигналы changed ───────────────────────────────────────────────
    def _connect_signals(self):
        for w in [self._cut_dur, self._st_top, self._st_center,
                  self._st_bottom, self._st_width, self._st_height]:
            w.valueChanged.connect(self.changed)
        for w in [self._cut_reencode, self._merge_reencode]:
            w.stateChanged.connect(self.changed)
        for w in [self._cut_prefix, *self._paths.values()]:
            w.textChanged.connect(self.changed)
        self._st_audio.currentIndexChanged.connect(self.changed)

    # ── Загрузка / чтение данных ──────────────────────────────────────
    def load(self, data: dict):
        cut   = data.get('cut', {})
        merge = data.get('merge', {})
        stack = data.get('stack', {})
        paths = data.get('paths', {})

        self._cut_dur.setValue(cut.get('clip_duration', 60))
        self._cut_prefix.setText(cut.get('prefix', 'clip'))
        self._cut_reencode.setChecked(bool(cut.get('reencode', False)))

        self._merge_reencode.setChecked(bool(merge.get('reencode', False)))

        self._st_top.setValue(stack.get('ratio_top', 1))
        self._st_center.setValue(stack.get('ratio_center', 3))
        self._st_bottom.setValue(stack.get('ratio_bottom', 1))
        self._st_width.setValue(stack.get('output_width', 1080))
        self._st_height.setValue(stack.get('output_height', 1920))
        audio_map = {'center': 0, 'top': 1, 'bottom': 2}
        self._st_audio.setCurrentIndex(
            audio_map.get(stack.get('audio_source', 'center'), 0))

        for key, edit in self._paths.items():
            edit.setText(paths.get(key, ''))

    def collect(self) -> dict:
        audio_vals = ['center', 'top', 'bottom']
        return {
            'cut': {
                'clip_duration': self._cut_dur.value(),
                'prefix':        self._cut_prefix.text().strip() or 'clip',
                'reencode':      self._cut_reencode.isChecked(),
            },
            'merge': {
                'reencode': self._merge_reencode.isChecked(),
            },
            'stack': {
                'ratio_top':     self._st_top.value(),
                'ratio_center':  self._st_center.value(),
                'ratio_bottom':  self._st_bottom.value(),
                'output_width':  self._st_width.value(),
                'output_height': self._st_height.value(),
                'audio_source':  audio_vals[self._st_audio.currentIndex()],
            },
            'paths': {k: e.text().strip() for k, e in self._paths.items()},
        }


# ──────────────────────────────────────────────────────────────────────
# ГЛАВНАЯ СТРАНИЦА
# ──────────────────────────────────────────────────────────────────────

class PresetsPage(BasePage):
    preset_applied = pyqtSignal(dict)   # data dict → processing_page

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_preset: dict | None = None
        self._unsaved = False
        self._card_map: dict[int, PresetCardWidget] = {}   # list_row → card
        self._build_ui()
        self.setStyleSheet(PAGE_STYLE)
        self._load_presets()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_body(), stretch=1)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName('presets_toolbar')
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 16, 0)
        lay.setSpacing(8)

        lbl = QLabel('Пресеты')
        lbl.setObjectName('presets_title')
        lay.addWidget(lbl)
        lay.addStretch()

        for text, slot in [
            ('📥  Импорт', self._import_presets),
            ('📤  Экспорт', self._export_presets),
        ]:
            btn = QPushButton(text)
            btn.setObjectName('toolbar_btn')
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        lay.addSpacing(4)
        new_btn = QPushButton('+ Новый пресет')
        new_btn.setObjectName('new_btn')
        new_btn.clicked.connect(self._new_preset)
        lay.addWidget(new_btn)
        return bar

    def _build_body(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        # ── Левая панель: список ──
        left = QFrame()
        left.setStyleSheet('background:#1c1b19; border-right:1px solid #2d2c2a;')
        left.setFixedWidth(280)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(8, 8, 8, 8)
        left_lay.setSpacing(6)

        lbl = QLabel('СОХРАНЁННЫЕ ПРЕСЕТЫ')
        lbl.setStyleSheet('color:#5a5957; font-size:10px; font-weight:700; letter-spacing:0.7px; padding:4px 4px 2px;')
        left_lay.addWidget(lbl)

        self._preset_list = QListWidget()
        self._preset_list.setObjectName('preset_list')
        self._preset_list.setSpacing(4)
        self._preset_list.currentRowChanged.connect(self._on_preset_selected)
        left_lay.addWidget(self._preset_list)

        self._count_lbl = QLabel('0 пресетов')
        self._count_lbl.setStyleSheet('color:#3a3937; font-size:11px;                                       padding:0 4px;')
        left_lay.addWidget(self._count_lbl)
        splitter.addWidget(left)

        # ── Правая панель: редактор ──
        right = QFrame()
        right.setObjectName('editor_panel')
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        # Шапка редактора
        self._ed_header = QFrame()
        self._ed_header.setObjectName('editor_header')
        self._ed_header.setFixedHeight(48)
        hdr_lay = QHBoxLayout(self._ed_header)
        hdr_lay.setContentsMargins(20, 0, 16, 0)
        hdr_lay.setSpacing(8)

        self._ed_name = QLineEdit()
        self._ed_name.setObjectName('ed_input')
        self._ed_name.setPlaceholderText('Название пресета...')
        self._ed_name.textChanged.connect(self._mark_unsaved)
        hdr_lay.addWidget(self._ed_name, stretch=1)

        self._unsaved_dot = QLabel('●')
        self._unsaved_dot.setObjectName('unsaved_dot')
        self._unsaved_dot.setToolTip('Есть несохранённые изменения')
        self._unsaved_dot.hide()
        hdr_lay.addWidget(self._unsaved_dot)
        right_lay.addWidget(self._ed_header)

        # Описание
        desc_frame = QFrame()
        desc_frame.setStyleSheet('background:#1c1b19;')
        desc_lay = QHBoxLayout(desc_frame)
        desc_lay.setContentsMargins(20, 8, 20, 8)
        self._ed_desc = QTextEdit()
        self._ed_desc.setObjectName('ed_textarea')
        self._ed_desc.setPlaceholderText('Краткое описание пресета (необязательно)...')
        self._ed_desc.setFixedHeight(52)
        self._ed_desc.textChanged.connect(self._mark_unsaved)
        desc_lay.addWidget(self._ed_desc)
        right_lay.addWidget(desc_frame)

        # Редактор настроек
        self._editor = SettingsEditor()
        self._editor.changed.connect(self._mark_unsaved)
        right_lay.addWidget(self._editor, stretch=1)

        # Кнопки действий
        actions = QFrame()
        actions.setStyleSheet('background:#1c1b19; border-top:1px solid #2d2c2a;')
        act_lay = QHBoxLayout(actions)
        act_lay.setContentsMargins(20, 10, 20, 10)
        act_lay.setSpacing(8)

        self._save_btn = QPushButton('💾  Сохранить')
        self._save_btn.setObjectName('save_btn')
        self._save_btn.clicked.connect(self._save_preset)
        act_lay.addWidget(self._save_btn)

        self._apply_btn = QPushButton('✓  Применить')
        self._apply_btn.setObjectName('apply_btn')
        self._apply_btn.setToolTip('Применить настройки пресета к обработке')
        self._apply_btn.clicked.connect(self._apply_preset)
        act_lay.addWidget(self._apply_btn)

        act_lay.addStretch()

        self._del_btn = QPushButton('🗑  Удалить')
        self._del_btn.setObjectName('del_btn')
        self._del_btn.clicked.connect(self._delete_preset)
        self._del_btn.setEnabled(False)
        act_lay.addWidget(self._del_btn)
        right_lay.addWidget(actions)

        # Hint когда ничего не выбрано
        self._hint_lbl = QLabel('← Выберите пресет или создайте новый')
        self._hint_lbl.setObjectName('editor_hint')
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_lay.insertWidget(1, self._hint_lbl)

        self._set_editor_visible(False)
        splitter.addWidget(right)
        splitter.setSizes([280, 700])
        return splitter

    # ── Управление видимостью редактора ──────────────────────────────
    def _set_editor_visible(self, visible: bool):
        self._ed_header.setVisible(visible)
        self._editor.setVisible(visible)
        for w in [self._ed_desc.parent().parent()]:  # desc_frame through parent chain
            if hasattr(w, 'layout'):  # simplified
                pass
        # Direct approach:
        for child in self.findChildren(QFrame, 'editor_panel'):
            pass
        self._ed_desc.parent().setVisible(visible)
        self._hint_lbl.setVisible(not visible)
        self._save_btn.setEnabled(visible)
        self._apply_btn.setEnabled(visible)
        self._del_btn.setEnabled(visible and self._current_preset is not None
                                 and self._current_preset.get('id', 0) > 0)

    # ── Загрузка списка ───────────────────────────────────────────────
    def _load_presets(self):
        self._preset_list.clear()
        self._card_map.clear()
        try:
            presets = db.get_all_presets() or []
        except Exception:
            presets = []

        for p in presets:
            item = QListWidgetItem()
            card = PresetCardWidget(p)
            item.setSizeHint(QSize(0, card.sizeHint().height() + 8))
            self._preset_list.addItem(item)
            self._preset_list.setItemWidget(item, card)
            self._card_map[self._preset_list.row(item)] = card

        n = len(presets)
        noun = 'пресет' if n == 1 else ('пресета' if 2 <= n <= 4 else 'пресетов')
        self._count_lbl.setText(f'{n} {noun}')

    # ── Выбор пресета ─────────────────────────────────────────────────
    def _on_preset_selected(self, row: int):
        # Снять выделение с прошлой карточки
        for r, card in self._card_map.items():
            card.set_selected(r == row)

        item = self._preset_list.item(row)
        if item is None:
            return
        card = self._card_map.get(row)
        if card is None:
            return

        self._current_preset = card.preset()
        self._unsaved = False
        self._unsaved_dot.hide()
        self._set_editor_visible(True)

        self._ed_name.blockSignals(True)
        self._ed_desc.blockSignals(True)
        self._ed_name.setText(self._current_preset.get('name', ''))
        self._ed_desc.setPlainText(self._current_preset.get('description', '') or '')
        self._ed_name.blockSignals(False)
        self._ed_desc.blockSignals(False)

        data = self._current_preset.get('data') or {}
        self._editor.load(data)
        self._unsaved = False
        self._unsaved_dot.hide()
        self._del_btn.setEnabled(True)

    # ── Новый пресет ──────────────────────────────────────────────────
    def _new_preset(self):
        self._current_preset = None
        self._unsaved = False
        self._preset_list.clearSelection()
        for card in self._card_map.values():
            card.set_selected(False)

        self._set_editor_visible(True)
        self._del_btn.setEnabled(False)

        self._ed_name.blockSignals(True)
        self._ed_desc.blockSignals(True)
        self._ed_name.setText('')
        self._ed_desc.setPlainText('')
        self._ed_name.blockSignals(False)
        self._ed_desc.blockSignals(False)

        self._editor.load(DEFAULT_PRESET)
        self._unsaved = False
        self._unsaved_dot.hide()
        self._ed_name.setFocus()

    # ── Сохранение ────────────────────────────────────────────────────
    def _save_preset(self):
        name = self._ed_name.text().strip()
        if not name:
            self._ed_name.setPlaceholderText('⚠ Введите название')
            self._ed_name.setStyleSheet(
                self._ed_name.styleSheet() +
                'border-color:#dd6974;'
            )
            return
        self._ed_name.setStyleSheet('')

        data = self._editor.collect()
        desc = self._ed_desc.toPlainText().strip() or None

        try:
            if self._current_preset and self._current_preset.get('id', 0) > 0:
                db.update_preset(
                    self._current_preset['id'], name, data, desc)
            else:
                new_id = db.add_preset(name, data, desc)
                if new_id is None:
                    # Имя занято — добавляем суффикс
                    db.add_preset(f'{name} (2)', data, desc)
            self._unsaved = False
            self._unsaved_dot.hide()
            self._load_presets()
        except Exception as e:
            QMessageBox.warning(self, 'Ошибка', f'Не удалось сохранить:\n{e}')

    # ── Применение к обработке ────────────────────────────────────────
    def _apply_preset(self):
        data = self._editor.collect()
        apply_preset_to_config(data, CONFIG_PATH)
        self.preset_applied.emit(data)

    # ── Удаление ──────────────────────────────────────────────────────
    def _delete_preset(self):
        if not self._current_preset:
            return
        name = self._current_preset.get('name', '')
        reply = QMessageBox.question(
            self, 'Удалить пресет',
            f'Удалить пресет «{name}»?\nЭто действие необратимо.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            db.delete_preset(self._current_preset['id'])
            self._current_preset = None
            self._set_editor_visible(False)
            self._load_presets()
        except Exception as e:
            QMessageBox.warning(self, 'Ошибка', str(e))

    # ── Импорт ────────────────────────────────────────────────────────
    def _import_presets(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Импортировать пресеты',
            os.path.expanduser('~'),
            'Пресеты (*.json);;Все файлы (*)',
        )
        if not paths:
            return
        imported = 0
        for filepath in paths:
            items = import_preset_file(filepath)
            for p in items:
                name = p.get('name', 'Импортированный')
                data = p.get('data', {})
                desc = p.get('description', '')
                # Уникальное имя
                while db.preset_name_exists(name):
                    name = name + ' (импорт)'
                result = db.add_preset(name, data, desc or None)
                if result:
                    imported += 1
        if imported:
            self._load_presets()
            QMessageBox.information(
                self, 'Импорт завершён',
                f'Импортировано пресетов: {imported}',
            )
        else:
            QMessageBox.warning(
                self, 'Импорт', 'Не удалось импортировать ни одного пресета.\n'
                               'Проверь формат файла.',
            )

    # ── Экспорт ───────────────────────────────────────────────────────
    def _export_presets(self):
        try:
            presets = db.get_all_presets() or []
        except Exception:
            presets = []

        if not presets:
            QMessageBox.information(
                self, 'Экспорт', 'Нет сохранённых пресетов.')
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, 'Экспортировать пресеты',
            os.path.join(os.path.expanduser('~'), 'yt_manager_presets.json'),
            'JSON (*.json)',
        )
        if not filepath:
            return

        ok = export_all_presets_file(presets, filepath)
        if ok:
            QMessageBox.information(
                self, 'Экспорт завершён',
                f'Экспортировано {len(presets)} пресетов:\n{filepath}',
            )
        else:
            QMessageBox.warning(self, 'Ошибка', 'Не удалось сохранить файл.')

    # ── Маркер несохранённых изменений ────────────────────────────────
    def _mark_unsaved(self, *_):
        if not self._unsaved:
            self._unsaved = True
            self._unsaved_dot.show()
