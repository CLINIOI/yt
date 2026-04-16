# processing_page.py — Страница обработки видео
#
# CutTab     — нарезка по длительности
# MergeTab   — склейка списка файлов
# StackTab   — вертикальный стек (top/center/bottom)
# ProcessingTaskCard — карточка активной задачи с прогрессом
# ProcessingPage     — главная страница, объединяет всё

import os
import random
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QCheckBox,
    QComboBox, QListWidget, QListWidgetItem, QScrollArea,
    QTabWidget, QFileDialog, QAbstractItemView, QSizePolicy,
    QProgressBar, QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from pages.base_page import BasePage
from db import db
from video_service import VideoService, ProcessWorker, is_ffmpeg_available


# ──────────────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────────────

PAGE_STYLE = '''
/* Toolbar */
QFrame#proc_toolbar { background:#1c1b19; border-bottom:1px solid #2d2c2a; }
QLabel#proc_title   { color:#cdccca; font-size:16px; font-weight:700; }

/* Settings panel */
QTabWidget#proc_tabs::pane {
    background:#1c1b19; border:none;
}
QTabWidget#proc_tabs QTabBar::tab {
    background:#201f1d; color:#797876;
    padding:8px 18px; border:none;
    font-size:12px; font-weight:600;
}
QTabWidget#proc_tabs QTabBar::tab:selected {
    background:#1c1b19; color:#cdccca;
    border-bottom:2px solid #4f98a3;
}
QTabWidget#proc_tabs QTabBar::tab:hover:!selected { color:#cdccca; }

/* Sections */
QLabel#sec_label {
    color:#5a5957; font-size:10px; font-weight:700;
    letter-spacing:0.8px; text-transform:uppercase;
}
QFrame#sec_divider { background:#2d2c2a; max-height:1px; }

/* Inputs */
QLineEdit#proc_input {
    background:#201f1d; border:1px solid #393836;
    border-radius:6px; color:#cdccca;
    font-size:12px; padding:6px 10px;
}
QLineEdit#proc_input:focus { border-color:#4f98a3; }

QSpinBox#proc_spin {
    background:#201f1d; border:1px solid #393836;
    border-radius:6px; color:#cdccca;
    font-size:12px; padding:5px 8px; min-width:70px;
}
QSpinBox#proc_spin:focus { border-color:#4f98a3; }
QSpinBox#proc_spin::up-button, QSpinBox#proc_spin::down-button {
    width:16px; border:none; background:#2d2c2a; border-radius:3px;
}

QComboBox#proc_combo {
    background:#201f1d; border:1px solid #393836;
    border-radius:6px; color:#cdccca;
    font-size:12px; padding:5px 10px;
}
QComboBox#proc_combo:focus { border-color:#4f98a3; }
QComboBox#proc_combo::drop-down { border:none; width:20px; }
QComboBox QAbstractItemView {
    background:#201f1d; color:#cdccca;
    border:1px solid #393836; outline:none;
}

QCheckBox#proc_check {
    color:#cdccca; font-size:12px; spacing:8px;
}
QCheckBox#proc_check::indicator {
    width:16px; height:16px; border-radius:4px;
    border:1px solid #393836; background:#201f1d;
}
QCheckBox#proc_check::indicator:checked {
    background:#4f98a3; border-color:#4f98a3;
}

/* Merge list */
QListWidget#merge_list {
    background:#201f1d; border:1px solid #2d2c2a;
    border-radius:6px; color:#cdccca; font-size:12px;
    outline:none;
}
QListWidget#merge_list::item { padding:6px 10px; border-radius:4px; }
QListWidget#merge_list::item:selected {
    background:#313b3b; color:#4f98a3;
}
QListWidget#merge_list::item:hover:!selected { background:#262523; }

/* Browse button */
QPushButton#browse_btn {
    background:#2d2c2a; color:#cdccca; border:none;
    border-radius:6px; font-size:11px; padding:6px 12px;
}
QPushButton#browse_btn:hover { background:#393836; }

/* Action buttons */
QPushButton#start_btn {
    background:#01696f; color:#f9f8f5;
    border:none; border-radius:7px;
    font-size:13px; font-weight:700;
    padding:10px 0; min-height:38px;
}
QPushButton#start_btn:hover    { background:#0c4e54; }
QPushButton#start_btn:disabled { background:#2d2c2a; color:#5a5957; }

QPushButton#icon_btn {
    background:#2d2c2a; color:#797876; border:none;
    border-radius:5px; font-size:13px;
    padding:4px 9px; min-width:28px; min-height:28px;
}
QPushButton#icon_btn:hover { background:#393836; color:#cdccca; }
QPushButton#icon_btn:disabled { color:#3a3937; }

/* Task cards */
QFrame#task_card {
    background:#201f1d; border:1px solid #2d2c2a;
    border-radius:10px;
}
QLabel#task_op     { color:#4f98a3; font-size:11px; font-weight:700; letter-spacing:0.5px; }
QLabel#task_desc   { color:#cdccca; font-size:12px; }
QLabel#task_msg    { color:#5a5957; font-size:11px; }
QLabel#task_done   { color:#6daa45; font-size:11px; font-weight:600; }
QLabel#task_error  { color:#dd6974; font-size:11px; }

QPushButton#task_cancel {
    background:transparent; border:none;
    color:#3a3937; font-size:14px; border-radius:4px; padding:2px 6px;
}
QPushButton#task_cancel:hover { color:#dd6974; background:#2d2018; }

QProgressBar#task_bar {
    background:#2d2c2a; border:none; border-radius:3px;
    max-height:4px; min-height:4px;
}
QProgressBar#task_bar::chunk { background:#4f98a3; border-radius:3px; }
QProgressBar#task_bar[done=true]::chunk  { background:#6daa45; }
QProgressBar#task_bar[error=true]::chunk { background:#dd6974; }

/* Right panel */
QFrame#right_panel { background:#171614; border-left:1px solid #2d2c2a; }
QLabel#right_title {
    color:#5a5957; font-size:11px; font-weight:700;
    letter-spacing:0.6px;
}
QLabel#no_tasks {
    color:#3a3937; font-size:13px;
}

/* Scroll */
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { background:transparent; width:5px; }
QScrollBar::handle:vertical {
    background:#393836; border-radius:2px; min-height:20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }

/* ── Composition Tab styles ── */
QFrame#slot_card { background:#1c1b19; border:1px solid #2d2c2a; border-radius:8px; margin-bottom:2px; }
QLabel#slot_desc { color:#797876; font-size:11px; }
QLabel#slot_req  { color:#5a5957; font-size:10px; }
QLabel#slot_path_empty  { color:#5a5957; font-size:11px; font-style:italic; }
QLabel#slot_path_file   { color:#4f98a3; font-size:11px; }
QLabel#slot_path_folder { color:#6daa45; font-size:11px; }
QPushButton#slot_file_btn, QPushButton#slot_folder_btn {
    background:#28251d; border:1px solid #393836; border-radius:5px;
    color:#cdccca; font-size:11px; padding:3px 10px;
}
QPushButton#slot_file_btn:hover, QPushButton#slot_folder_btn:hover {
    background:#2d2c2a; border-color:#4f98a3;
}
QPushButton#slot_clear_btn { background:#28251d; border:1px solid #393836; border-radius:5px; color:#797876; font-size:10px; }
QPushButton#slot_clear_btn:hover { color:#dd6974; border-color:#dd6974; }
QPushButton#fmt_btn { background:#1c1b19; border:1px solid #393836; border-radius:7px; color:#797876; font-size:10px; font-weight:600; }
QPushButton#fmt_btn:hover { border-color:#5a5957; color:#cdccca; }
QPushButton#fmt_btn_active { background:#01696f22; border:2px solid #4f98a3; border-radius:7px; color:#4f98a3; font-size:10px; font-weight:700; }
QLabel#proc_hint { color:#5a5957; font-size:10px; padding-left:2px; }
QCheckBox#proc_chk { color:#cdccca; font-size:12px; }
'''


# ──────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ВИДЖЕТЫ
# ──────────────────────────────────────────────────────────────────────

def _section(title: str) -> tuple:
    lbl = QLabel(title.upper())
    lbl.setObjectName('sec_label')
    div = QFrame()
    div.setObjectName('sec_divider')
    div.setFixedHeight(1)
    return lbl, div


def _spin(lo: int, hi: int, val: int, suffix: str = '') -> QSpinBox:
    s = QSpinBox()
    s.setObjectName('proc_spin')
    s.setRange(lo, hi)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    return s


def _label_field(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet('color:#797876; font-size:12px;')
    return lbl


class FileBrowseWidget(QWidget):
    path_changed = pyqtSignal(str)

    def __init__(self, mode: str = 'file', placeholder: str = 'Выберите файл...',
                 filter_str: str = 'Видео (*.mp4 *.mkv *.avi *.mov *.webm);;Все файлы (*)',
                 parent=None):
        self._filter_str = filter_str
        super().__init__(parent)
        self._mode = mode   # 'file' | 'dir' | 'save'
        self._build(placeholder)

    def _build(self, placeholder: str):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._edit = QLineEdit()
        self._edit.setObjectName('proc_input')
        self._edit.setPlaceholderText(placeholder)
        self._edit.textChanged.connect(self.path_changed)
        lay.addWidget(self._edit)

        btn = QPushButton('Обзор')
        btn.setObjectName('browse_btn')
        btn.setFixedWidth(64)
        btn.clicked.connect(self._browse)
        lay.addWidget(btn)

    def _browse(self):
        if self._mode == 'folder':
            path = QFileDialog.getExistingDirectory(self, 'Выберите папку', self._edit.text())
        elif self._mode == 'save':
            path, _ = QFileDialog.getSaveFileName(
                self, 'Сохранить как', self._edit.text(),
                'Видео (*.mp4 *.mkv *.avi);;Все файлы (*)'
            )
        else:
            flt = getattr(self, '_filter_str', 'Видео (*.mp4 *.mkv *.avi *.mov *.webm);;Все файлы (*)')
            path, _ = QFileDialog.getOpenFileName(self, 'Выбрать файл', self._edit.text(), flt)
        if path:
            self.set_path(path)

    def path(self) -> str:
        return self._edit.text().strip()

    def set_path(self, p: str):
        self._edit.setText(p)


class ProcessingTaskCard(QFrame):
    cancel_requested = pyqtSignal()

    def __init__(self, op_icon: str, op_name: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName('task_card')
        self._worker: Optional[ProcessWorker] = None
        self._build(op_icon, op_name, desc)

    def _build(self, icon: str, op_name: str, desc: str):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(6)

        # Верхняя строка: иконка + имя операции + описание + отмена
        top = QHBoxLayout()
        top.setSpacing(8)

        op_lbl = QLabel(f'{icon}  {op_name}')
        op_lbl.setObjectName('task_op')
        top.addWidget(op_lbl)

        self._desc = QLabel(desc)
        self._desc.setObjectName('task_desc')
        fm = self._desc.fontMetrics()
        self._desc.setText(fm.elidedText(desc, Qt.TextElideMode.ElideMiddle, 260))
        top.addWidget(self._desc, stretch=1)

        self._cancel_btn = QPushButton('✕')
        self._cancel_btn.setObjectName('task_cancel')
        self._cancel_btn.setFixedSize(22, 22)
        self._cancel_btn.clicked.connect(self._on_cancel)
        top.addWidget(self._cancel_btn)
        lay.addLayout(top)

        # Прогресс-бар
        self._bar = QProgressBar()
        self._bar.setObjectName('task_bar')
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        lay.addWidget(self._bar)

        # Строка статуса
        bot = QHBoxLayout()
        self._msg_lbl = QLabel('Подготовка...')
        self._msg_lbl.setObjectName('task_msg')
        bot.addWidget(self._msg_lbl, stretch=1)
        self._pct_lbl = QLabel('0%')
        self._pct_lbl.setObjectName('task_op')
        self._pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        bot.addWidget(self._pct_lbl)
        lay.addLayout(bot)

    def attach_worker(self, worker: ProcessWorker):
        self._worker = worker
        worker.progress.connect(self.update_progress)
        worker.finished.connect(self.set_done)
        worker.error.connect(self.set_error)

    def update_progress(self, pct: int, msg: str):
        self._bar.setValue(pct)
        self._pct_lbl.setText(f'{pct}%')
        if msg:
            self._msg_lbl.setText(msg)

    def set_done(self, output_paths: list):
        self._bar.setValue(100)
        self._bar.setProperty('done', 'true')
        self._bar.setStyleSheet(self._bar.styleSheet())
        self._pct_lbl.setText('100%')
        count = len(output_paths)
        noun  = 'файл' if count == 1 else 'файлов'
        self._msg_lbl.setObjectName('task_done')
        self._msg_lbl.setStyleSheet('color:#6daa45; font-size:11px; font-weight:600;')
        self._msg_lbl.setText(f'Готово — {count} {noun}')
        self._cancel_btn.hide()
        self._worker = None

    def set_error(self, msg: str):
        self._bar.setProperty('error', 'true')
        self._bar.setStyleSheet(self._bar.styleSheet())
        self._msg_lbl.setStyleSheet('color:#dd6974; font-size:11px;')
        self._msg_lbl.setText(f'Ошибка: {msg[:90]}')
        self._cancel_btn.hide()
        self._worker = None

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self.cancel_requested.emit()


# ──────────────────────────────────────────────────────────────────────
# ВКЛАДКИ НАСТРОЕК
# ──────────────────────────────────────────────────────────────────────

class CutTab(QScrollArea):
    task_started = pyqtSignal(object, str, str)   # worker, icon, desc

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(16, 14, 16, 20)
        self._lay.setSpacing(8)
        self._build()
        self.setWidget(inner)

    def _build(self):
        lay = self._lay

        # Исходный файл
        lbl, div = _section('Исходный файл')
        lay.addWidget(lbl)
        lay.addWidget(div)
        self._input = FileBrowseWidget('file', 'Выберите видеофайл...')
        lay.addWidget(self._input)
        self._info_lbl = QLabel('')
        self._info_lbl.setStyleSheet('color:#5a5957; font-size:11px;')
        self._info_lbl.setWordWrap(True)
        lay.addWidget(self._info_lbl)
        self._input.path_changed.connect(self._on_input_changed)

        lay.addSpacing(8)

        # Настройки нарезки
        lbl, div = _section('Настройки нарезки')
        lay.addWidget(lbl)
        lay.addWidget(div)

        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        grid.setHorizontalSpacing(10)

        grid.addWidget(_label_field('Длительность клипа'), 0, 0)
        self._duration = _spin(1, 3600, 60, ' сек')
        grid.addWidget(self._duration, 0, 1)

        grid.addWidget(_label_field('Префикс имени'), 1, 0)
        self._prefix = QLineEdit('clip')
        self._prefix.setObjectName('proc_input')
        self._prefix.setMaximumWidth(120)
        grid.addWidget(self._prefix, 1, 1)

        lay.addLayout(grid)

        self._reencode = QCheckBox('Перекодировать (libx264)')
        self._reencode.setObjectName('proc_check')
        self._reencode.setToolTip(
            'Включи если клипы нужно дальше склеивать.\n'
            'Без перекодировки — быстро, но менее совместимо.'
        )
        lay.addWidget(self._reencode)

        lay.addSpacing(8)

        # Выходная папка
        lbl, div = _section('Выходная папка')
        lay.addWidget(lbl)
        lay.addWidget(div)
        self._output_dir = FileBrowseWidget('dir', 'Папка для клипов...')
        lay.addWidget(self._output_dir)

        lay.addSpacing(12)

        # Кнопка запуска
        self._start_btn = QPushButton('▶  Запустить нарезку')
        self._start_btn.setObjectName('start_btn')
        self._start_btn.clicked.connect(self._start)
        lay.addWidget(self._start_btn)
        lay.addStretch()


    def apply_preset(self, data: dict):
        """Применяет секцию 'cut' из пресета."""
        if 'clip_duration' in data:
            self._duration.setValue(int(data['clip_duration']))
        if 'prefix' in data:
            self._prefix.setText(str(data.get('prefix', 'clip')))
        if 'reencode' in data:
            self._reencode.setChecked(bool(data['reencode']))

    def _on_input_changed(self, path: str):
        if not os.path.isfile(path):
            self._info_lbl.setText('')
            return
        try:
            svc  = VideoService()
            info = svc.get_video_info(path)
            dur  = int(self._duration.value())
            n    = max(1, int(info.duration // dur)
                       + (1 if info.duration % dur > 1 else 0))
            self._info_lbl.setText(
                f'{info.resolution}  ·  {info.duration_str}  ·  fps {info.fps:.2f}  '
                f'→  ~{n} клипов по {dur}с'
            )
        except Exception:
            self._info_lbl.setText('')

    def _start(self):
        inp = self._input.path()
        out = self._output_dir.path()
        if not inp or not os.path.isfile(inp):
            self._info_lbl.setText('⚠ Укажи исходный видеофайл')
            return
        if not out:
            self._info_lbl.setText('⚠ Укажи выходную папку')
            return

        worker = ProcessWorker(
            'cut',
            input_path=inp,
            output_dir=out,
            clip_duration=self._duration.value(),
            prefix=self._prefix.text().strip() or 'clip',
            reencode=self._reencode.isChecked(),
        )
        worker.start()
        desc = os.path.basename(inp)
        self.task_started.emit(worker, '✂', f'Нарезка · {desc}')


class MergeTab(QScrollArea):
    task_started = pyqtSignal(object, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(16, 14, 16, 20)
        self._lay.setSpacing(8)
        self._build()
        self.setWidget(inner)

    def _build(self):
        lay = self._lay

        # Список файлов
        lbl, div = _section('Файлы для склейки')
        lay.addWidget(lbl)
        lay.addWidget(div)

        # Тулбар списка
        bar = QHBoxLayout()
        bar.setSpacing(4)
        for icon, tip, slot in [
            ('+', 'Добавить файлы', self._add_files),
            ('−', 'Удалить выбранный', self._remove_selected),
            ('↑', 'Вверх', self._move_up),
            ('↓', 'Вниз', self._move_down),
        ]:
            btn = QPushButton(icon)
            btn.setObjectName('icon_btn')
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        bar.addStretch()
        self._count_lbl = QLabel('0 файлов')
        self._count_lbl.setStyleSheet('color:#5a5957; font-size:11px;')
        bar.addWidget(self._count_lbl)
        lay.addLayout(bar)

        self._list = QListWidget()
        self._list.setObjectName('merge_list')
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setFixedHeight(180)
        self._list.model().rowsInserted.connect(self._update_count)
        self._list.model().rowsRemoved.connect(self._update_count)
        lay.addWidget(self._list)

        lay.addSpacing(6)

        # Настройки
        lbl, div = _section('Настройки')
        lay.addWidget(lbl)
        lay.addWidget(div)

        self._reencode = QCheckBox('Перекодировать (для разных форматов)')
        self._reencode.setObjectName('proc_check')
        lay.addWidget(self._reencode)

        lay.addSpacing(8)

        # Выходной файл
        lbl, div = _section('Выходной файл')
        lay.addWidget(lbl)
        lay.addWidget(div)
        self._output = FileBrowseWidget('save', 'output_merged.mp4')
        lay.addWidget(self._output)

        lay.addSpacing(12)

        self._err_lbl = QLabel('')
        self._err_lbl.setStyleSheet('color:#dd6974; font-size:11px;')
        lay.addWidget(self._err_lbl)

        self._start_btn = QPushButton('▶  Запустить склейку')
        self._start_btn.setObjectName('start_btn')
        self._start_btn.clicked.connect(self._start)
        lay.addWidget(self._start_btn)
        lay.addStretch()


    def apply_preset(self, data: dict):
        """Применяет секцию 'merge' из пресета."""
        if 'reencode' in data:
            self._reencode.setChecked(bool(data['reencode']))

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Добавить файлы',
            os.path.expanduser('~'),
            'Видео (*.mp4 *.mkv *.avi *.mov *.webm)',
        )
        for p in paths:
            item = QListWidgetItem(os.path.basename(p))
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(p)
            self._list.addItem(item)

    def _remove_selected(self):
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))

    def _move_up(self):
        row = self._list.currentRow()
        if row > 0:
            item = self._list.takeItem(row)
            self._list.insertItem(row - 1, item)
            self._list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._list.currentRow()
        if row < self._list.count() - 1:
            item = self._list.takeItem(row)
            self._list.insertItem(row + 1, item)
            self._list.setCurrentRow(row + 1)

    def _update_count(self):
        n = self._list.count()
        self._count_lbl.setText(f'{n} файл{'ов' if n != 1 else ""}')

    def _start(self):
        paths = [self._list.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self._list.count())]
        out   = self._output.path()
        self._err_lbl.setText('')
        if len(paths) < 2:
            self._err_lbl.setText('⚠ Добавь минимум 2 файла')
            return
        if not out:
            self._err_lbl.setText('⚠ Укажи выходной файл')
            return

        worker = ProcessWorker(
            'merge',
            input_paths=paths,
            output_path=out,
            reencode=self._reencode.isChecked(),
        )
        worker.start()
        self.task_started.emit(worker, '🔗', f'Склейка · {len(paths)} файлов')



# ── FORMAT PRESETS ────────────────────────────────────────────────────
FORMAT_PRESETS = {
    'tiktok': {
        'label': 'TikTok',  'icon': '📱', 'ratio': '9:16',
        'w': 1080, 'h': 1920, 'top': 320, 'mid': 1280, 'bot': 320,
    },
    'reels': {
        'label': 'Reels',   'icon': '🎞', 'ratio': '9:16',
        'w': 1080, 'h': 1920, 'top': 240, 'mid': 1440, 'bot': 240,
    },
    'shorts': {
        'label': 'Shorts',  'icon': '▶',  'ratio': '9:16',
        'w': 1080, 'h': 1920, 'top': 0,   'mid': 1920, 'bot': 0,
    },
    'square': {
        'label': 'Square',  'icon': '⬜', 'ratio': '1:1',
        'w': 1080, 'h': 1080, 'top': 200, 'mid': 680,  'bot': 200,
    },
    'youtube': {
        'label': 'YouTube', 'icon': '📺', 'ratio': '16:9',
        'w': 1920, 'h': 1080, 'top': 0,   'mid': 1080, 'bot': 0,
    },
}

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.ts', '.flv'}

def _pick_video_from_folder(folder: str) -> str:
    """Выбирает случайное видео из папки (рекурсивно, 1 уровень)."""
    import random as _random
    files = [
        os.path.join(folder, f) for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in VIDEO_EXTS
    ]
    if not files:
        raise FileNotFoundError(f'Нет видео-файлов в папке: {folder}')
    return _random.choice(files)


def _resolve_slot(path: str) -> str:
    """Файл → вернуть путь; папка → выбрать случайное видео."""
    if not path:
        return ''
    if os.path.isfile(path):
        return path
    if os.path.isdir(path):
        return _pick_video_from_folder(path)
    return path


# ── SLOT CARD ─────────────────────────────────────────────────────────
class SlotCard(QFrame):
    """
    Карточка видео-слота: Файл + Папка + отображение пути.
    Три слота: ЦЕНТР (обязателен), ВЕРХ (баннер), НИЗ (фон).
    """
    path_changed = pyqtSignal(str)

    _SLOT_CFG = {
        'center': {'icon': '▶', 'label': 'ЦЕНТР',
                   'desc': 'Главное видео · хронометраж = длине этого видео',
                   'accent': '#4f98a3', 'req': True},
        'top':    {'icon': '▲', 'label': 'ВЕРХ',
                   'desc': 'Баннер / брендинг (необязательно)',
                   'accent': '#6daa45', 'req': False},
        'bottom': {'icon': '▼', 'label': 'НИЗ',
                   'desc': 'Фоновое видео / геймплей (необязательно)',
                   'accent': '#a86fdf', 'req': False},
    }

    def __init__(self, slot_id: str, parent=None):
        super().__init__(parent)
        cfg = self._SLOT_CFG[slot_id]
        self._slot_id = slot_id
        self._path    = ''
        self._accent  = cfg['accent']
        self._req     = cfg['req']
        self._build(cfg)

    def _build(self, cfg: dict):
        self.setObjectName('slot_card')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # ── Заголовок ──
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        badge = QLabel(f'{cfg["icon"]}  {cfg["label"]}')
        badge.setObjectName('slot_badge')
        badge.setStyleSheet(
            f'background:{self._accent}22; color:{self._accent};'
            f' border:1px solid {self._accent}44;'
            f' border-radius:4px; padding:1px 8px;'
            f' font-size:11px; font-weight:700;'
        )
        hdr.addWidget(badge)

        req_lbl = QLabel('обязательно' if self._req else 'необязательно')
        req_lbl.setObjectName('slot_req')
        req_lbl.setStyleSheet(
            'color:#5a5957; font-size:10px; padding-left:4px;'
        )
        hdr.addWidget(req_lbl)
        hdr.addStretch()
        lay.addLayout(hdr)

        # ── Описание ──
        desc = QLabel(cfg['desc'])
        desc.setObjectName('slot_desc')
        lay.addWidget(desc)

        # ── Кнопки выбора ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._file_btn = QPushButton('📄  Файл')
        self._file_btn.setObjectName('slot_file_btn')
        self._file_btn.clicked.connect(self._pick_file)
        btn_row.addWidget(self._file_btn)

        self._folder_btn = QPushButton('📁  Папка')
        self._folder_btn.setObjectName('slot_folder_btn')
        self._folder_btn.clicked.connect(self._pick_folder)
        btn_row.addWidget(self._folder_btn)

        if not self._req:
            self._clear_btn = QPushButton('✕')
            self._clear_btn.setObjectName('slot_clear_btn')
            self._clear_btn.setFixedWidth(28)
            self._clear_btn.setToolTip('Очистить слот')
            self._clear_btn.clicked.connect(self._clear)
            btn_row.addWidget(self._clear_btn)

        btn_row.addStretch()
        lay.addLayout(btn_row)

        # ── Путь ──
        self._path_lbl = QLabel('Не выбрано')
        self._path_lbl.setObjectName('slot_path_empty')
        self._path_lbl.setWordWrap(True)
        lay.addWidget(self._path_lbl)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Выберите видео', '',
            'Видео (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;Все файлы (*)'
        )
        if path:
            self._set_path(path)

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Выберите папку с видео')
        if path:
            self._set_path(path)

    def _clear(self):
        self._set_path('')

    def _set_path(self, path: str):
        self._path = path
        if not path:
            self._path_lbl.setText('Не выбрано')
            self._path_lbl.setObjectName('slot_path_empty')
        elif os.path.isdir(path):
            try:
                files = [f for f in os.listdir(path)
                         if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
                self._path_lbl.setText(f'📁  {os.path.basename(path)}  ({len(files)} видео)')
            except Exception:
                self._path_lbl.setText(f'📁  {path}')
            self._path_lbl.setObjectName('slot_path_folder')
        else:
            self._path_lbl.setText(f'📄  {os.path.basename(path)}')
            self._path_lbl.setObjectName('slot_path_file')
        self._path_lbl.style().unpolish(self._path_lbl)
        self._path_lbl.style().polish(self._path_lbl)
        self.path_changed.emit(path)

    def path(self) -> str:
        return self._path

    def set_path(self, p: str):
        self._set_path(p)


# ── COMPOSITION TAB ───────────────────────────────────────────────────
class CompositionTab(QScrollArea):
    """
    Вкладка «Композиция»:
    - Выбор формата (TikTok / Reels / Shorts / Square / YouTube)
    - Три слота: ЦЕНТР (главное), ВЕРХ (баннер), НИЗ (фон)
    - Выбор файла или папки для каждого слота
    - Источник аудио
    - Субтитры (SRT файл)
    - Настройки вывода (папка, качество, цвет фона)
    - Запуск обработки
    """
    task_started = pyqtSignal(object, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._active_format = 'tiktok'
        inner = QWidget()
        self._lay = QVBoxLayout(inner)
        self._lay.setContentsMargins(16, 14, 16, 20)
        self._lay.setSpacing(10)
        self._build()
        self.setWidget(inner)

    def _build(self):
        lay = self._lay

        # ── Формат ──────────────────────────────────────────────────
        fmt_lbl, fmt_div = _section('Формат вывода')
        lay.addWidget(fmt_lbl)
        lay.addWidget(fmt_div)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(6)
        self._fmt_btns: dict[str, QPushButton] = {}
        for key, cfg in FORMAT_PRESETS.items():
            btn = QPushButton(f'{cfg["icon"]}  {cfg["label"]}\n{cfg["ratio"]}')
            btn.setObjectName('fmt_btn_active' if key == self._active_format else 'fmt_btn')
            btn.setFixedSize(86, 52)
            btn.clicked.connect(lambda _, k=key: self._select_format(k))
            self._fmt_btns[key] = btn
            fmt_row.addWidget(btn)
        fmt_row.addStretch()
        lay.addLayout(fmt_row)

        # Текущие размеры
        self._fmt_hint = QLabel('')
        self._fmt_hint.setObjectName('proc_hint')
        lay.addWidget(self._fmt_hint)
        self._update_format_hint()

        lay.addSpacing(4)

        # ── Слоты видео ─────────────────────────────────────────────
        slots_lbl, slots_div = _section('Видео-слоты')
        lay.addWidget(slots_lbl)
        lay.addWidget(slots_div)

        # ЦЕНТР — главное
        self._slot_center = SlotCard('center')
        lay.addWidget(self._slot_center)

        # ВЕРХ — баннер
        self._slot_top = SlotCard('top')
        lay.addWidget(self._slot_top)

        # НИЗ — фоновое видео
        self._slot_bottom = SlotCard('bottom')
        lay.addWidget(self._slot_bottom)

        lay.addSpacing(4)

        # ── Настройки аудио ─────────────────────────────────────────
        aud_lbl, aud_div = _section('Аудио')
        lay.addWidget(aud_lbl)
        lay.addWidget(aud_div)

        aud_row = QHBoxLayout()
        aud_row.setSpacing(10)
        aud_row.addWidget(_label_field('Источник звука'))
        self._audio_src = QComboBox()
        self._audio_src.setObjectName('proc_combo')
        self._audio_src.addItems(['Центр (главное видео)', 'Верх (баннер)', 'Низ (фон)'])
        self._audio_map = ['center', 'top', 'bottom']
        aud_row.addWidget(self._audio_src)
        aud_row.addStretch()
        lay.addLayout(aud_row)

        hint_aud = QLabel('Остальные слоты будут без звука')
        hint_aud.setObjectName('proc_hint')
        lay.addWidget(hint_aud)

        lay.addSpacing(4)

        # ── Субтитры ────────────────────────────────────────────────
        sub_lbl, sub_div = _section('Субтитры (необязательно)')
        lay.addWidget(sub_lbl)
        lay.addWidget(sub_div)

        sub_toggle_row = QHBoxLayout()
        self._sub_chk = QCheckBox('Добавить субтитры из SRT-файла')
        self._sub_chk.setObjectName('proc_chk')
        self._sub_chk.toggled.connect(self._on_sub_toggled)
        sub_toggle_row.addWidget(self._sub_chk)
        sub_toggle_row.addStretch()
        lay.addLayout(sub_toggle_row)

        self._sub_group = QWidget()
        sub_g_lay = QGridLayout(self._sub_group)
        sub_g_lay.setContentsMargins(0, 4, 0, 0)
        sub_g_lay.setSpacing(6)

        sub_g_lay.addWidget(_label_field('Файл SRT'), 0, 0)
        self._sub_file = FileBrowseWidget('file', 'Выберите .srt файл...',
                                          filter_str='Субтитры (*.srt *.ass *.vtt);;Все (*)')
        sub_g_lay.addWidget(self._sub_file, 0, 1)

        sub_g_lay.addWidget(_label_field('Размер шрифта'), 1, 0)
        self._sub_size = _spin(14, 72, 32, ' pt')
        sub_g_lay.addWidget(self._sub_size, 1, 1)

        sub_g_lay.addWidget(_label_field('Цвет текста'), 2, 0)
        self._sub_color = QComboBox()
        self._sub_color.setObjectName('proc_combo')
        self._sub_color.addItems(['Белый', 'Жёлтый', 'Чёрный'])
        self._sub_color_map = ['white', 'yellow', 'black']
        sub_g_lay.addWidget(self._sub_color, 2, 1)

        self._sub_group.hide()
        lay.addWidget(self._sub_group)

        sub_note = QLabel('⚠ Субтитры требуют ffmpeg с поддержкой libass')
        sub_note.setObjectName('proc_hint')
        lay.addWidget(sub_note)

        lay.addSpacing(4)

        # ── Вывод ───────────────────────────────────────────────────
        out_lbl, out_div = _section('Настройки вывода')
        lay.addWidget(out_lbl)
        lay.addWidget(out_div)

        grid = QGridLayout()
        grid.setSpacing(6)

        grid.addWidget(_label_field('Папка вывода'), 0, 0)
        self._output_dir = FileBrowseWidget('folder', 'Папка для сохранения...')
        grid.addWidget(self._output_dir, 0, 1)

        grid.addWidget(_label_field('Качество'), 1, 0)
        self._quality = QComboBox()
        self._quality.setObjectName('proc_combo')
        self._quality.addItems(['Быстро (fast)', 'Хорошо (medium)', 'Лучшее (slow)'])
        self._quality_map = ['fast', 'good', 'best']
        grid.addWidget(self._quality, 1, 1)

        grid.addWidget(_label_field('Цвет фона'), 2, 0)
        self._bg_color = QComboBox()
        self._bg_color.setObjectName('proc_combo')
        self._bg_color.addItems(['Чёрный', 'Белый', 'Серый'])
        self._bg_color_map = ['black', 'white', 'gray']
        grid.addWidget(self._bg_color, 2, 1)

        grid.addWidget(_label_field('Имя файла'), 3, 0)
        self._out_name = QLineEdit()
        self._out_name.setObjectName('proc_input')
        self._out_name.setPlaceholderText('output_{timestamp}.mp4  (авто если пусто)')
        grid.addWidget(self._out_name, 3, 1)

        lay.addLayout(grid)

        lay.addSpacing(8)

        # ── Ошибки / кнопка ─────────────────────────────────────────
        self._err_lbl = QLabel('')
        self._err_lbl.setStyleSheet('color:#dd6974; font-size:11px;')
        lay.addWidget(self._err_lbl)

        self._start_btn = QPushButton('▶▶  ОБРАБОТАТЬ')
        self._start_btn.setObjectName('start_btn')
        self._start_btn.clicked.connect(self._start)
        lay.addWidget(self._start_btn)
        lay.addStretch()

    # ── Обработчики ──────────────────────────────────────────────────

    def _select_format(self, key: str):
        prev = self._active_format
        self._active_format = key
        self._fmt_btns[prev].setObjectName('fmt_btn')
        self._fmt_btns[prev].style().unpolish(self._fmt_btns[prev])
        self._fmt_btns[prev].style().polish(self._fmt_btns[prev])
        self._fmt_btns[key].setObjectName('fmt_btn_active')
        self._fmt_btns[key].style().unpolish(self._fmt_btns[key])
        self._fmt_btns[key].style().polish(self._fmt_btns[key])
        self._update_format_hint()

    def _update_format_hint(self):
        cfg = FORMAT_PRESETS[self._active_format]
        parts = [f'{cfg["w"]}×{cfg["h"]}px']
        if cfg['top'] > 0:
            parts.append(f'верх {cfg["top"]}px')
        parts.append(f'центр {cfg["mid"]}px')
        if cfg['bot'] > 0:
            parts.append(f'низ {cfg["bot"]}px')
        self._fmt_hint.setText('  ·  '.join(parts))

    def _on_sub_toggled(self, checked: bool):
        self._sub_group.setVisible(checked)

    def _start(self):
        from datetime import datetime
        self._err_lbl.setText('')

        center = _resolve_slot(self._slot_center.path())
        if not center or not os.path.isfile(center):
            self._err_lbl.setText('⚠ Укажи ЦЕНТР-видео (главный файл)')
            return

        top    = _resolve_slot(self._slot_top.path())    or None
        bottom = _resolve_slot(self._slot_bottom.path()) or None

        out_dir = self._output_dir.path()
        if not out_dir:
            out_dir = os.path.join(os.path.dirname(center), 'processed')
        os.makedirs(out_dir, exist_ok=True)

        name = self._out_name.text().strip()
        if not name:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            name = f'output_{self._active_format}_{ts}.mp4'
        if not name.lower().endswith('.mp4'):
            name += '.mp4'
        output_path = os.path.join(out_dir, name)

        fmt = FORMAT_PRESETS[self._active_format]

        sub_path  = None
        sub_size  = 32
        sub_color = 'white'
        if self._sub_chk.isChecked():
            sub_path  = self._sub_file.path() or None
            sub_size  = self._sub_size.value()
            sub_color = self._sub_color_map[self._sub_color.currentIndex()]

        worker = ProcessWorker(
            'stack',
            center_path   = center,
            top_path      = top,
            bottom_path   = bottom,
            output_path   = output_path,
            output_width  = fmt['w'],
            output_height = fmt['h'],
            top_h         = fmt['top'],
            center_h      = fmt['mid'],
            bottom_h      = fmt['bot'],
            audio_source  = self._audio_map[self._audio_src.currentIndex()],
            subtitle_path = sub_path,
            subtitle_size = sub_size,
            subtitle_color= sub_color,
            bg_color      = self._bg_color_map[self._bg_color.currentIndex()],
            quality       = self._quality_map[self._quality.currentIndex()],
        )
        worker.start()
        desc = f'Композиция · {fmt["label"]} {fmt["ratio"]}'
        self.task_started.emit(worker, '📱', desc)

    def apply_preset(self, data: dict):
        if 'format' in data and data['format'] in FORMAT_PRESETS:
            self._select_format(data['format'])
        if 'audio_source' in data:
            idx = {'center': 0, 'top': 1, 'bottom': 2}.get(data['audio_source'], 0)
            self._audio_src.setCurrentIndex(idx)
        if 'quality' in data:
            idx = {'fast': 0, 'good': 1, 'best': 2}.get(data['quality'], 0)
            self._quality.setCurrentIndex(idx)
        if 'center_path' in data: self._slot_center.set_path(data['center_path'])
        if 'top_path'    in data: self._slot_top.set_path(data['top_path'])
        if 'bottom_path' in data: self._slot_bottom.set_path(data['bottom_path'])
        if 'output_dir'  in data: self._output_dir.set_path(data['output_dir'])




class ProcessingPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_cards: list[ProcessingTaskCard] = []
        self._build_ui()
        self.setStyleSheet(PAGE_STYLE)

        # Предупреждение если ffmpeg не найден
        if not is_ffmpeg_available():
            self._ffmpeg_warn.show()
        else:
            self._ffmpeg_warn.hide()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_body(), stretch=1)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName('proc_toolbar')
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 16, 0)
        lbl = QLabel('Обработка видео')
        lbl.setObjectName('proc_title')
        lay.addWidget(lbl)
        lay.addStretch()

        self._ffmpeg_warn = QLabel('⚠ ffmpeg не найден — обработка недоступна')
        self._ffmpeg_warn.setStyleSheet('color:#e8af34; font-size:11px;')
        lay.addWidget(self._ffmpeg_warn)
        return bar

    def _build_body(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        # ── Левая панель: вкладки настроек ──
        self._tabs = QTabWidget()
        self._tabs.setObjectName('proc_tabs')
        self._tabs.setFixedWidth(340)

        self._cut_tab   = CutTab()
        self._merge_tab = MergeTab()
        self._comp_tab = CompositionTab()

        self._tabs.addTab(self._cut_tab,   '✂  Нарезка')
        self._tabs.addTab(self._merge_tab, '🔗 Склейка')
        self._tabs.addTab(self._comp_tab, '📱  Композиция')

        for tab in [self._cut_tab, self._merge_tab, self._comp_tab]:
            tab.task_started.connect(self._on_task_started)

        splitter.addWidget(self._tabs)

        # ── Правая панель: активные задачи ──
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([340, 620])
        return splitter

    def _build_right_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName('right_panel')
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        hdr = QHBoxLayout()
        title = QLabel('АКТИВНЫЕ ЗАДАЧИ')
        title.setObjectName('right_title')
        hdr.addWidget(title)
        hdr.addStretch()
        outer.addLayout(hdr)

        # Scroll area для карточек задач
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        self._tasks_layout = QVBoxLayout(container)
        self._tasks_layout.setContentsMargins(0, 0, 0, 0)
        self._tasks_layout.setSpacing(8)

        self._no_tasks_lbl = QLabel('Нет активных задач\nЗапусти нарезку, склейку или стекинг')
        self._no_tasks_lbl.setObjectName('no_tasks')
        self._no_tasks_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_tasks_lbl.setWordWrap(True)
        self._tasks_layout.addWidget(self._no_tasks_lbl)
        self._tasks_layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll, stretch=1)

        return panel

    # ── Управление карточками задач ───────────────────────────────────

    def _on_task_started(self, worker: ProcessWorker, icon: str, desc: str):
        self._no_tasks_lbl.hide()
        card = ProcessingTaskCard(icon, icon + ' ' + desc.split('·')[0].strip(), desc)
        card.attach_worker(worker)
        card.cancel_requested.connect(lambda c=card: self._remove_card(c))
        worker.finished.connect(lambda _paths, c=card: self._on_worker_done(c))
        worker.error.connect(   lambda _msg,   c=card: self._on_worker_done(c))
        self._task_cards.append(card)
        idx = self._tasks_layout.count() - 1   # before stretch
        self._tasks_layout.insertWidget(idx, card)

    def _on_worker_done(self, card: ProcessingTaskCard):
        # Карточка остаётся видимой с итоговым статусом, не удаляем сразу
        pass

    def _remove_card(self, card: ProcessingTaskCard):
        self._tasks_layout.removeWidget(card)
        card.deleteLater()
        if card in self._task_cards:
            self._task_cards.remove(card)
        if not self._task_cards:
            self._no_tasks_lbl.show()

    def apply_preset(self, data: dict):
        """Применяет данные пресета ко всем трём вкладкам."""
        if 'cut'   in data: self._cut_tab.apply_preset(data['cut'])
        if 'merge' in data: self._merge_tab.apply_preset(data['merge'])
        if 'stack' in data: self._comp_tab.apply_preset(data.get('stack', data))

