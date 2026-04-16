# folders_page.py — Мониторинг папок
#
# FolderSizeWorker  — считает размер папок в фоне
# FolderTreeWidget  — дерево папок проекта
# FileTableWidget   — список файлов с сортировкой
# DiskUsageWidget   — бар использования диска
# FoldersPage       — главная страница

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from enum import Enum

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QMenu, QAbstractItemView, QSizePolicy,
    QProgressBar, QScrollArea, QApplication, QMessageBox,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer,
    QFileSystemWatcher, QSize,
)


from PyQt6.QtGui import QColor, QFont, QCursor, QPixmap
from pages.base_page import BasePage
from db import db


# ──────────────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────────────

PAGE_STYLE = '''
QFrame#folders_toolbar { background:#1c1b19; border-bottom:1px solid #2d2c2a; }
QLabel#folders_title   { color:#cdccca; font-size:16px; font-weight:700; }

/* Дерево папок */
QTreeWidget#folder_tree {
    background:#1c1b19; border:none;
    outline:none; font-size:12px;
}
QTreeWidget#folder_tree::item {
    padding:5px 4px; border-radius:5px;
    color:#cdccca;
}
QTreeWidget#folder_tree::item:selected {
    background:#313b3b; color:#4f98a3;
}
QTreeWidget#folder_tree::item:hover:!selected { background:#262523; }
QTreeWidget#folder_tree::branch { background:transparent; }
QTreeWidget#folder_tree::branch:open:has-children {
    image:none; border-image:none;
}
QHeaderView::section {
    background:#201f1d; color:#5a5957;
    font-size:11px; font-weight:600;
    border:none; padding:6px 10px;
    border-bottom:1px solid #2d2c2a;
}

/* Таблица файлов */
QTableWidget#file_table {
    background:#171614; border:none;
    gridline-color:#201f1d;
    outline:none; font-size:12px;
    color:#cdccca;
}
QTableWidget#file_table::item { padding:4px 8px; }
QTableWidget#file_table::item:selected {
    background:#313b3b; color:#4f98a3;
}
QTableWidget#file_table::item:hover:!selected { background:#201f1d; }

/* Левая панель */
QFrame#left_panel { background:#1c1b19; border-right:1px solid #2d2c2a; }
QLabel#tree_section {
    color:#5a5957; font-size:10px; font-weight:700;
    letter-spacing:0.8px; padding:0 4px;
}

/* Disk usage */
QFrame#usage_frame {
    background:#201f1d; border-radius:8px;
    border:1px solid #2d2c2a;
}
QLabel#usage_name  { color:#797876; font-size:11px; font-weight:600; }
QLabel#usage_size  { color:#5a5957; font-size:11px; }
QLabel#usage_free  { color:#4f98a3; font-size:11px; }
QProgressBar#usage_bar {
    background:#2d2c2a; border:none; border-radius:3px;
    max-height:4px; min-height:4px;
}
QProgressBar#usage_bar::chunk { background:#4f98a3; border-radius:3px; }
QProgressBar#usage_bar[warn=true]::chunk  { background:#e8af34; }
QProgressBar#usage_bar[alert=true]::chunk { background:#dd6974; }

/* Кнопки */
QPushButton#tool_btn {
    background:#2d2c2a; color:#797876;
    border:none; border-radius:6px;
    font-size:12px; padding:5px 12px;
}
QPushButton#tool_btn:hover { background:#393836; color:#cdccca; }

QPushButton#danger_btn {
    background:transparent; color:#5a5957;
    border:1px solid #393836; border-radius:6px;
    font-size:12px; padding:5px 12px;
}
QPushButton#danger_btn:hover { color:#dd6974; border-color:#dd6974; }

/* Статус-бар */
QFrame#status_bar {
    background:#1c1b19; border-top:1px solid #2d2c2a;
    max-height:28px; min-height:28px;
}
QLabel#status_txt { color:#5a5957; font-size:11px; }
QLabel#status_path { color:#3a3937; font-size:11px; }

/* Пустое состояние */
QLabel#empty_lbl { color:#3a3937; font-size:13px; }

/* Скролл */
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { background:transparent; width:5px; }
QScrollBar::handle:vertical {
    background:#393836; border-radius:2px; min-height:20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }

/* ── Предпросмотр ── */
QFrame#preview_panel {
    background:#1c1b19; border-left:1px solid #2d2c2a;
}
QFrame#thumb_frame {
    background:#171614; border-radius:6px;
    border:1px solid #2d2c2a;
}
QLabel#thumb_placeholder {
    color:#3a3937; font-size:32px;
}
QLabel#preview_name {
    color:#cdccca; font-size:12px; font-weight:600;
    padding:2px 0;
}
QLabel#preview_meta {
    color:#797876; font-size:11px;
}
QPushButton#preview_play_btn {
    background:#01696f22; border:1px solid #4f98a3;
    border-radius:6px; color:#4f98a3;
    font-size:12px; font-weight:600;
    padding:6px 10px;
}
QPushButton#preview_play_btn:hover {
    background:#01696f44; border-color:#4f98a3;
}
QPushButton#preview_play_btn:disabled {
    background:transparent; border-color:#2d2c2a; color:#3a3937;
}
/* Кнопка удаления в тулбаре таблицы */
QPushButton#tool_btn_danger {
    background:#a13544; border:none; border-radius:5px;
    color:#f9f8f5; font-size:12px; padding:4px 10px;
}
QPushButton#tool_btn_danger:hover  { background:#c24a59; }
QPushButton#tool_btn_danger:disabled { background:#2d2c2a; color:#3a3937; }
'''


# ──────────────────────────────────────────────────────────────────────
# УТИЛИТЫ
# ──────────────────────────────────────────────────────────────────────

def human_size(n: int) -> str:
    for unit in ('Б', 'КБ', 'МБ', 'ГБ', 'ТБ'):
        if abs(n) < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} ПБ'


def fmt_mtime(path: str) -> str:
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d  %H:%M')
    except OSError:
        return '—'


def open_in_explorer(path: str):
    try:
        if sys.platform == 'win32':
            if os.path.isfile(path):
                subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
            else:
                os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', path])
        else:
            d = path if os.path.isdir(path) else os.path.dirname(path)
            subprocess.Popen(['xdg-open', d])
    except Exception:
        pass


def open_with_player(path: str):
    try:
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass


def load_config_paths() -> dict:
    cfg_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config.json',
    )
    defaults = {
        'downloads':   './downloads',
        'processed':   './processed',
        'backgrounds': './backgrounds',
        'banners':     './banners',
    }
    try:
        with open(cfg_path, encoding='utf-8') as fh:
            cfg = json.load(fh)
        return {**defaults, **cfg.get('paths', {})}
    except Exception:
        return defaults


VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.ts', '.m4v'}
IMG_EXTS   = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}

FOLDER_ICONS = {
    'downloads':   '📥',
    'processed':   '⚙',
    'backgrounds': '🖼',
    'banners':     '🏷',
    'clips':       '✂',
    'merged':      '🔗',
    'stacked':     '⊞',
    'channel':     '📂',
    'default':     '📁',
}

EXT_ICONS = {
    '.mp4': '🎬', '.mkv': '🎬', '.avi': '🎬', '.mov': '🎬',
    '.webm': '🎬', '.flv': '🎬', '.ts': '🎬', '.m4v': '🎬',
    '.jpg': '🖼', '.jpeg': '🖼', '.png': '🖼', '.gif': '🖼', '.webp': '🖼',
    '.mp3': '🎵', '.aac': '🎵', '.wav': '🎵', '.m4a': '🎵',
    '.json': '📄', '.txt': '📄', '.csv': '📄',
}


# ──────────────────────────────────────────────────────────────────────
# ФОНОВЫЙ ВОРКЕР: РАЗМЕР ПАПОК
# ──────────────────────────────────────────────────────────────────────

class FolderSizeWorker(QThread):
    size_calculated = pyqtSignal(str, int)   # path, size_bytes
    all_done        = pyqtSignal()

    def __init__(self, paths: list, parent=None):
        super().__init__(parent)
        self._paths = paths

    def run(self):
        for path in self._paths:
            if not os.path.isdir(path):
                self.size_calculated.emit(path, 0)
                continue
            total = 0
            try:
                for dirpath, _, filenames in os.walk(path):
                    for fn in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, fn))
                        except OSError:
                            pass
            except OSError:
                pass
            self.size_calculated.emit(path, total)
        self.all_done.emit()


# ──────────────────────────────────────────────────────────────────────
# ДИСК: СТАТИСТИКА
# ──────────────────────────────────────────────────────────────────────

class DiskUsageWidget(QFrame):
    def __init__(self, root_path: str, parent=None):
        super().__init__(parent)
        self.setObjectName('usage_frame')
        self._path = root_path
        self._build()
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        self._name = QLabel('Диск')
        self._name.setObjectName('usage_name')
        top.addWidget(self._name)
        top.addStretch()
        self._free_lbl = QLabel('')
        self._free_lbl.setObjectName('usage_free')
        top.addWidget(self._free_lbl)
        lay.addLayout(top)

        self._bar = QProgressBar()
        self._bar.setObjectName('usage_bar')
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        lay.addWidget(self._bar)

        self._size_lbl = QLabel('')
        self._size_lbl.setObjectName('usage_size')
        lay.addWidget(self._size_lbl)

    def refresh(self):
        try:
            usage = shutil.disk_usage(self._path if os.path.exists(self._path)
                                      else '.')
            pct  = int(usage.used / usage.total * 100)
            free = human_size(usage.free)
            used = human_size(usage.used)
            total= human_size(usage.total)

            drive = os.path.splitdrive(self._path)[0] or '/'
            self._name.setText(f'Диск  {drive}')
            self._free_lbl.setText(f'{free} свободно')
            self._size_lbl.setText(f'{used} из {total}  ({pct}%)')
            self._bar.setValue(pct)

            self._bar.setProperty('warn', 'true' if pct > 80 else 'false')
            self._bar.setProperty('alert', 'true' if pct > 92 else 'false')
            self._bar.setStyleSheet(self._bar.styleSheet())
        except Exception:
            self._name.setText('Диск')


# ──────────────────────────────────────────────────────────────────────
# ДЕРЕВО ПАПОК
# ──────────────────────────────────────────────────────────────────────

class FolderTreeWidget(QTreeWidget):
    folder_selected = pyqtSignal(str)   # path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('folder_tree')
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.setExpandsOnDoubleClick(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.itemClicked.connect(self._on_item_click)
        self._paths = {}
        self._size_items: dict[str, QTreeWidgetItem] = {}

    def load(self, config_paths: dict):
        self.clear()
        self._paths = config_paths
        self._size_items.clear()

        root_order = [
            ('downloads',   '📥  Загрузки'),
            ('processed',   '⚙   Обработанные'),
            ('backgrounds', '🖼  Фоны'),
            ('banners',     '🏷  Баннеры'),
        ]
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        for key, label in root_order:
            raw = config_paths.get(key, f'./{key}')
            abs_p = os.path.normpath(
                os.path.join(base, raw) if not os.path.isabs(raw) else raw
            )

            root_item = QTreeWidgetItem([label])
            root_item.setData(0, Qt.ItemDataRole.UserRole, abs_p)
            root_item.setData(0, Qt.ItemDataRole.UserRole + 1, key)
            self._make_bold(root_item)
            self.addTopLevelItem(root_item)
            self._size_items[abs_p] = root_item

            if os.path.isdir(abs_p):
                self._load_children(root_item, abs_p, key)
                root_item.setExpanded(True)
            else:
                placeholder = QTreeWidgetItem(['  Папка не найдена'])
                placeholder.setForeground(0, QColor('#3a3937'))
                root_item.addChild(placeholder)

    def _load_children(self, parent: QTreeWidgetItem, path: str, parent_type: str):
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
        except PermissionError:
            return

        for entry in entries:
            if not entry.is_dir():
                continue
            name = entry.name
            # Определяем иконку по имени подпапки
            icon = FOLDER_ICONS.get(name.lower(),
                   FOLDER_ICONS.get(parent_type, FOLDER_ICONS['default']))
            label = f'{icon}  {name}'
            child = QTreeWidgetItem([label])
            child.setData(0, Qt.ItemDataRole.UserRole, entry.path)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, name.lower())
            parent.addChild(child)
            self._size_items[entry.path] = child
            # Рекурсивно только для processed (clips/merged/stacked)
            if parent_type == 'processed':
                self._load_children(child, entry.path, name.lower())

    def _make_bold(self, item: QTreeWidgetItem):
        font = item.font(0)
        if font.pointSize() <= 0:
            font.setPointSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        item.setFont(0, font)

    def update_size(self, path: str, size: int):
        item = self._size_items.get(path)
        if item:
            current = item.text(0)
            # Обрезаем старый размер если есть
            if '  ·  ' in current:
                current = current.split('  ·  ')[0]
            item.setText(0, f'{current}  ·  {human_size(size)}')

    def _on_item_click(self, item: QTreeWidgetItem):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.isdir(path):
            self.folder_selected.emit(path)

    def _context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            'QMenu { background:#201f1d; color:#cdccca; border:1px solid #393836; }'
            'QMenu::item { padding:6px 20px; }'
            'QMenu::item:selected { background:#313b3b; color:#4f98a3; }'
        )
        act_open = menu.addAction('📂  Открыть в проводнике')
        act_open.triggered.connect(lambda: open_in_explorer(path))
        act_refresh = menu.addAction('🔄  Обновить')
        act_refresh.triggered.connect(lambda: self.folder_selected.emit(path))
        menu.exec(QCursor.pos())


# ──────────────────────────────────────────────────────────────────────
# ТАБЛИЦА ФАЙЛОВ
# ──────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────
# УТИЛИТЫ: продолжительность видео
# ──────────────────────────────────────────────────────────────────────

def fmt_duration(secs) -> str:
    try:
        s = int(float(secs))
    except (TypeError, ValueError):
        return '—'
    if s < 0:
        return '—'
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f'{h}:{m:02d}:{sec:02d}'
    return f'{m}:{sec:02d}'


def probe_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=8,
        )
        val = r.stdout.strip()
        return float(val) if val else 0.0
    except Exception:
        return 0.0


def probe_resolution(path: str) -> str:
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error',
             '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height',
             '-of', 'csv=s=x:p=0', path],
            capture_output=True, text=True, timeout=8,
        )
        val = r.stdout.strip()
        return val if 'x' in val else ''
    except Exception:
        return ''


class _NumItem(QTableWidgetItem):
    def __lt__(self, other) -> bool:
        a = self.data(Qt.ItemDataRole.UserRole) or 0
        b = other.data(Qt.ItemDataRole.UserRole) or 0
        try:
            return a < b
        except TypeError:
            return False


class VideoDurationWorker(QThread):
    duration_ready = pyqtSignal(str, float)

    def __init__(self, paths: list, parent=None):
        super().__init__(parent)
        self._paths = paths
        self._stop  = False

    def stop(self):
        self._stop = True

    def run(self):
        for path in self._paths:
            if self._stop:
                break
            self.duration_ready.emit(path, probe_duration(path))


class ThumbnailWorker(QThread):
    done = pyqtSignal(str)

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self._path = video_path

    def run(self):
        import hashlib, tempfile
        try:
            h = hashlib.md5(self._path.encode()).hexdigest()[:14]
            thumb = os.path.join(tempfile.gettempdir(), f'ytmgr_{h}.jpg')
            if os.path.isfile(thumb):
                self.done.emit(thumb)
                return
            subprocess.run(
                ['ffmpeg', '-i', self._path,
                 '-vf', 'thumbnail,scale=300:-2',
                 '-frames:v', '1', '-y', thumb],
                capture_output=True, timeout=12,
            )
            if os.path.isfile(thumb):
                self.done.emit(thumb)
        except Exception:
            pass


class VideoPreviewPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('preview_panel')
        self.setMinimumWidth(240)
        self.setMaximumWidth(300)
        self._current_path = ''
        self._thumb_worker = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 10, 12)
        lay.setSpacing(8)
        sec = QLabel('ПРЕДПРОСМОТР')
        sec.setObjectName('tree_section')
        lay.addWidget(sec)
        self._thumb_frame = QFrame()
        self._thumb_frame.setObjectName('thumb_frame')
        self._thumb_frame.setFixedHeight(160)
        tf = QVBoxLayout(self._thumb_frame)
        tf.setContentsMargins(4, 4, 4, 4)
        self._thumb_lbl = QLabel('🎬')
        self._thumb_lbl.setObjectName('thumb_placeholder')
        self._thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf.addWidget(self._thumb_lbl)
        lay.addWidget(self._thumb_frame)
        self._name_lbl = QLabel('—')
        self._name_lbl.setObjectName('preview_name')
        self._name_lbl.setWordWrap(True)
        lay.addWidget(self._name_lbl)
        self._res_lbl  = QLabel('')
        self._dur_lbl  = QLabel('')
        self._size_lbl = QLabel('')
        self._date_lbl = QLabel('')
        for lbl in [self._res_lbl, self._dur_lbl, self._size_lbl, self._date_lbl]:
            lbl.setObjectName('preview_meta')
            lay.addWidget(lbl)
        lay.addStretch()
        self._play_btn = QPushButton('▶  Открыть в плеере')
        self._play_btn.setObjectName('preview_play_btn')
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._play)
        lay.addWidget(self._play_btn)
        self._reveal_btn = QPushButton('📂  В проводнике')
        self._reveal_btn.setObjectName('tool_btn')
        self._reveal_btn.setEnabled(False)
        self._reveal_btn.clicked.connect(self._reveal)
        lay.addWidget(self._reveal_btn)

    def clear(self):
        self._current_path = ''
        self._name_lbl.setText('—')
        for lbl in [self._res_lbl, self._dur_lbl, self._size_lbl, self._date_lbl]:
            lbl.setText('')
        self._thumb_lbl.setPixmap(QPixmap())
        self._thumb_lbl.setText('🎬')
        self._play_btn.setEnabled(False)
        self._reveal_btn.setEnabled(False)

    def show_file(self, path: str):
        if not path or not os.path.isfile(path):
            self.clear()
            return
        self._current_path = path
        name = os.path.basename(path)
        self._name_lbl.setText(name if len(name) <= 36 else name[:34] + '…')
        try:
            self._size_lbl.setText(f'💾  {human_size(os.path.getsize(path))}')
        except OSError:
            self._size_lbl.setText('')
        try:
            ts = os.path.getmtime(path)
            self._date_lbl.setText(
                '📅  ' + datetime.fromtimestamp(ts).strftime('%d.%m.%Y  %H:%M'))
        except OSError:
            self._date_lbl.setText('')
        ext = os.path.splitext(path)[1].lower()
        is_video = ext in VIDEO_EXTS
        self._play_btn.setEnabled(is_video)
        self._reveal_btn.setEnabled(True)
        if is_video:
            self._dur_lbl.setText('⏱  ...')
            self._res_lbl.setText('📐  ...')
            self._thumb_lbl.setPixmap(QPixmap())
            self._thumb_lbl.setText('⏳')
            self._thumb_worker = ThumbnailWorker(path)
            self._thumb_worker.done.connect(self._on_thumb)
            self._thumb_worker.start()
            QTimer.singleShot(50, lambda: self._load_meta(path))
        else:
            self._dur_lbl.setText('')
            self._res_lbl.setText('')
            self._thumb_lbl.setPixmap(QPixmap())
            self._thumb_lbl.setText(EXT_ICONS.get(ext, '📄'))

    def _load_meta(self, path: str):
        if path != self._current_path:
            return
        dur = probe_duration(path)
        res = probe_resolution(path)
        self._dur_lbl.setText(f'⏱  {fmt_duration(dur)}' if dur else '⏱  —')
        self._res_lbl.setText(f'📐  {res}' if res else '')

    def _on_thumb(self, thumb_path: str):
        if not thumb_path or not os.path.isfile(thumb_path):
            self._thumb_lbl.setText('🎬')
            return
        pix = QPixmap(thumb_path)
        if not pix.isNull():
            pix = pix.scaled(280, 152,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._thumb_lbl.setPixmap(pix)
            self._thumb_lbl.setText('')
        else:
            self._thumb_lbl.setText('🎬')

    def _play(self):
        if self._current_path:
            open_with_player(self._current_path)

    def _reveal(self):
        if self._current_path:
            open_in_explorer(self._current_path)


class FileTableWidget(QFrame):
    """
    Панель просмотра содержимого папки.
    Колонки: Файл | Длина | Размер | Изменён | Тип
    - Сортировка по клику на заголовок (▲/▼)
    - Длительности видео загружаются в фоне
    - Delete через кнопку в тулбаре и контекстное меню (с подтверждением)
    - Сигнал file_selected(path) для панели предпросмотра
    """
    file_selected    = pyqtSignal(str)
    file_deleted     = pyqtSignal(str)
    folder_refreshed = pyqtSignal()

    # Индексы колонок
    COL_NAME  = 0
    COL_DUR   = 1
    COL_SIZE  = 2
    COL_MTIME = 3
    COL_EXT   = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path = ''
        self._dur_worker: VideoDurationWorker = None
        self._path_to_row: dict[str, int] = {}
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Тулбар ──────────────────────────────────────────────────
        bar = QFrame()
        bar.setStyleSheet('background:#1c1b19; border-bottom:1px solid #2d2c2a;')
        bar.setFixedHeight(40)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 0, 12, 0)
        bar_lay.setSpacing(8)

        self._path_lbl = QLabel('Выберите папку в дереве')
        self._path_lbl.setStyleSheet('color:#5a5957; font-size:11px;')
        bar_lay.addWidget(self._path_lbl, stretch=1)

        self._open_btn = QPushButton('📂  Открыть')
        self._open_btn.setObjectName('tool_btn')
        self._open_btn.setToolTip('Открыть папку в проводнике')
        self._open_btn.clicked.connect(self._open_folder)
        bar_lay.addWidget(self._open_btn)

        self._del_btn = QPushButton('🗑  Удалить')
        self._del_btn.setObjectName('tool_btn_danger')
        self._del_btn.setToolTip('Удалить выбранный файл')
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._delete_selected)
        bar_lay.addWidget(self._del_btn)

        self._refresh_btn = QPushButton('🔄')
        self._refresh_btn.setObjectName('tool_btn')
        self._refresh_btn.setFixedSize(32, 28)
        self._refresh_btn.setToolTip('Обновить список')
        self._refresh_btn.clicked.connect(lambda: self.load_folder(self._current_path))
        bar_lay.addWidget(self._refresh_btn)

        lay.addWidget(bar)

        # ── Пустое состояние ──────────────────────────────────────────
        self._empty = QLabel('\n📁\n\nВыберите папку в дереве слева')
        self._empty.setObjectName('empty_lbl')
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._empty)

        # ── Таблица ───────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setObjectName('file_table')
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ['ФАЙЛ', 'ДЛИНА', 'РАЗМЕР', 'ИЗМЕНЁН', 'ТИП'])

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_NAME,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(self.COL_DUR,   QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(self.COL_SIZE,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(self.COL_MTIME, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(self.COL_EXT,   QHeaderView.ResizeMode.Fixed)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(self.COL_MTIME, Qt.SortOrder.DescendingOrder)
        hdr.sectionClicked.connect(self._on_sort_col)

        self._table.setColumnWidth(self.COL_DUR,   72)
        self._table.setColumnWidth(self.COL_SIZE,  84)
        self._table.setColumnWidth(self.COL_MTIME, 130)
        self._table.setColumnWidth(self.COL_EXT,   50)

        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(False)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setDefaultSectionSize(34)

        self._table.doubleClicked.connect(self._on_double_click)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.hide()
        lay.addWidget(self._table, stretch=1)

    # ── Загрузка папки ─────────────────────────────────────────────────

    def load_folder(self, path: str):
        self._current_path = path
        self._path_lbl.setText(
            path if len(path) <= 55 else '…' + path[-52:])

        # Останавливаем предыдущий воркер
        if self._dur_worker and self._dur_worker.isRunning():
            self._dur_worker.stop()

        if not os.path.isdir(path):
            self._show_empty(f'⚠\n\nПапка не найдена:\n{path}')
            return

        try:
            entries = sorted(
                [e for e in os.scandir(path) if e.is_file()],
                key=lambda e: e.stat().st_mtime, reverse=True,
            )
        except PermissionError:
            entries = []

        if not entries:
            self._show_empty('📭\n\nПапка пуста')
            return

        self._empty.hide()
        self._table.show()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._path_to_row.clear()

        video_paths: list[str] = []

        for entry in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            ext  = os.path.splitext(entry.name)[1].lower()
            icon = EXT_ICONS.get(ext, '📄')

            # 0 — Имя
            name_item = QTableWidgetItem(f'{icon}  {entry.name}')
            name_item.setData(Qt.ItemDataRole.UserRole, entry.path)
            self._table.setItem(row, self.COL_NAME, name_item)

            # 1 — Длина (заглушка для видео; числовая сортировка)
            dur_item = _NumItem('')
            dur_item.setData(Qt.ItemDataRole.UserRole, 0)
            dur_item.setForeground(QColor('#5a5957'))
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if ext in VIDEO_EXTS:
                dur_item.setText('...')
                video_paths.append(entry.path)
                self._path_to_row[entry.path] = row
            self._table.setItem(row, self.COL_DUR, dur_item)

            # 2 — Размер (числовая сортировка по байтам)
            try:
                size_b = entry.stat().st_size
            except OSError:
                size_b = 0
            size_item = _NumItem(human_size(size_b))
            size_item.setData(Qt.ItemDataRole.UserRole, size_b)
            size_item.setForeground(QColor('#797876'))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, self.COL_SIZE, size_item)

            # 3 — Дата (строка YYYY-MM-DD HH:MM — сортируется корректно)
            mtime = fmt_mtime(entry.path)
            mt_item = QTableWidgetItem(mtime)
            mt_item.setData(Qt.ItemDataRole.UserRole, mtime)
            mt_item.setForeground(QColor('#5a5957'))
            mt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, self.COL_MTIME, mt_item)

            # 4 — Тип
            ext_item = QTableWidgetItem(ext or '—')
            ext_item.setForeground(QColor('#3a3937'))
            ext_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, self.COL_EXT, ext_item)

        # Включаем сортировку и применяем текущий индикатор
        self._table.setSortingEnabled(True)
        hdr = self._table.horizontalHeader()
        self._table.sortByColumn(hdr.sortIndicatorSection(), hdr.sortIndicatorOrder())

        # Фоновый воркер длительностей
        if video_paths:
            self._dur_worker = VideoDurationWorker(video_paths)
            self._dur_worker.duration_ready.connect(self._on_duration_ready)
            self._dur_worker.start()

        self.folder_refreshed.emit()

    def _on_duration_ready(self, path: str, seconds: float):
        """Обновляем длительность в таблице когда воркер прислал результат."""
        if path not in self._path_to_row:
            return
        # path_to_row хранит начальный row, но после сортировки нужен поиск
        for row in range(self._table.rowCount()):
            item = self._table.item(row, self.COL_NAME)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                dur_item = self._table.item(row, self.COL_DUR)
                if dur_item:
                    self._table.setSortingEnabled(False)
                    dur_item.setText(fmt_duration(seconds))
                    dur_item.setData(Qt.ItemDataRole.UserRole, int(seconds))
                    self._table.setSortingEnabled(True)
                break

    def _on_sort_col(self, col: int):
        """Не сортируем по ДЛИНА пока идёт загрузка воркера."""
        pass  # Qt сам управляет ▲▼; оставляем как хук для будущей логики

    def _show_empty(self, msg: str):
        self._empty.setText(f'\n{msg}')
        self._empty.show()
        self._table.hide()
        self._path_to_row.clear()

    # ── Выбор / взаимодействие ────────────────────────────────────────

    def _on_selection_changed(self):
        path = self._selected_path()
        self._del_btn.setEnabled(bool(path) and os.path.isfile(path))
        self.file_selected.emit(path)

    def _selected_path(self) -> str:
        row = self._table.currentRow()
        if row < 0:
            return ''
        item = self._table.item(row, self.COL_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item else ''

    def _on_double_click(self):
        p = self._selected_path()
        if p and os.path.isfile(p):
            open_with_player(p)

    def _open_folder(self):
        if self._current_path:
            open_in_explorer(self._current_path)

    # ── Удаление ──────────────────────────────────────────────────────

    def _delete_selected(self):
        path = self._selected_path()
        if path:
            self._delete_file(path)

    def _delete_file(self, path: str):
        from PyQt6.QtWidgets import QMessageBox
        name = os.path.basename(path)
        reply = QMessageBox.question(
            self, 'Удалить файл?',
            f'Удалить файл:\n\n{name}\n\nЭто действие необратимо.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(path)
            self.file_deleted.emit(path)
            self.load_folder(self._current_path)
        except OSError as e:
            from PyQt6.QtWidgets import QMessageBox as MB
            MB.warning(self, 'Ошибка', f'Не удалось удалить файл:\n{e}')

    # ── Контекстное меню ──────────────────────────────────────────────

    def _show_context_menu(self, pos):
        path = self._selected_path()
        if not path:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            'QMenu{background:#201f1d;color:#cdccca;border:1px solid #393836;}'
            'QMenu::item{padding:6px 20px;}'
            'QMenu::item:selected{background:#313b3b;color:#4f98a3;}'
            'QMenu::separator{background:#2d2c2a;height:1px;margin:4px 0;}'
        )
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            a = menu.addAction('▶  Открыть в плеере')
            a.triggered.connect(lambda: open_with_player(path))
        a2 = menu.addAction('📂  Показать в проводнике')
        a2.triggered.connect(lambda: open_in_explorer(path))
        menu.addSeparator()
        a3 = menu.addAction('📋  Копировать путь')
        a3.triggered.connect(lambda: QApplication.clipboard().setText(path))
        menu.addSeparator()
        a4 = menu.addAction('🗑  Удалить файл')
        a4.setEnabled(os.path.isfile(path))
        a4.triggered.connect(lambda: self._delete_file(path))
        menu.exec(QCursor.pos())

    # ── Статистика для статус-бара ─────────────────────────────────────

    def file_count(self) -> int:
        return self._table.rowCount()

    def total_size(self) -> int:
        total = 0
        for row in range(self._table.rowCount()):
            item = self._table.item(row, self.COL_SIZE)
            if item:
                total += item.data(Qt.ItemDataRole.UserRole) or 0
        return total




class FoldersPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._config_paths = load_config_paths()
        self._size_worker: FolderSizeWorker = None
        self._watcher = QFileSystemWatcher(self)
        self._build_ui()
        self.setStyleSheet(PAGE_STYLE)
        QTimer.singleShot(200, self._initial_load)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_body(), stretch=1)
        root.addWidget(self._build_status_bar())

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName('folders_toolbar')
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 16, 0)
        lay.setSpacing(10)

        lbl = QLabel('Мониторинг папок')
        lbl.setObjectName('folders_title')
        lay.addWidget(lbl)
        lay.addStretch()

        refresh_btn = QPushButton('🔄  Обновить всё')
        refresh_btn.setObjectName('tool_btn')
        refresh_btn.clicked.connect(self._full_refresh)
        lay.addWidget(refresh_btn)

        return bar

    def _build_body(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        # ── Левая панель: дерево + диск ──
        left = QFrame()
        left.setObjectName('left_panel')
        left.setMinimumWidth(260)
        left.setMaximumWidth(340)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(10, 10, 10, 10)
        left_lay.setSpacing(8)

        tree_lbl = QLabel('СТРУКТУРА ПРОЕКТА')
        tree_lbl.setObjectName('tree_section')
        left_lay.addWidget(tree_lbl)

        self._tree = FolderTreeWidget()
        self._tree.folder_selected.connect(self._on_folder_selected)
        left_lay.addWidget(self._tree, stretch=1)

        # Использование диска
        disk_lbl = QLabel('ДИСК')
        disk_lbl.setObjectName('tree_section')
        left_lay.addWidget(disk_lbl)

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dl_raw = self._config_paths.get('downloads', './downloads')
        dl_abs = os.path.join(base, dl_raw) if not os.path.isabs(dl_raw) else dl_raw
        self._disk_widget = DiskUsageWidget(dl_abs)
        left_lay.addWidget(self._disk_widget)

        splitter.addWidget(left)

        # ── Средняя панель: таблица файлов ──
        self._file_table = FileTableWidget()
        self._file_table.setMinimumWidth(380)
        self._file_table.file_selected.connect(self._on_file_selected)
        splitter.addWidget(self._file_table)

        # ── Правая панель: предпросмотр ──
        self._preview = VideoPreviewPanel()
        splitter.addWidget(self._preview)

        splitter.setSizes([280, 620, 260])
        return splitter

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName('status_bar')
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(20)

        self._status_files = QLabel('0 файлов')
        self._status_files.setObjectName('status_txt')
        lay.addWidget(self._status_files)

        self._status_size = QLabel('')
        self._status_size.setObjectName('status_txt')
        lay.addWidget(self._status_size)

        lay.addStretch()

        self._status_path = QLabel('')
        self._status_path.setObjectName('status_path')
        lay.addWidget(self._status_path)

        return bar

    # ── Загрузка и обновление ─────────────────────────────────────────

    def _initial_load(self):
        self._tree.load(self._config_paths)
        self._start_size_worker()
        self._setup_watcher()

    def _full_refresh(self):
        self._config_paths = load_config_paths()
        self._tree.load(self._config_paths)
        self._start_size_worker()
        self._disk_widget.refresh()
        if self._file_table._current_path:
            self._file_table.load_folder(self._file_table._current_path)

    def _start_size_worker(self):
        if self._size_worker and self._size_worker.isRunning():
            return
        base  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        paths = []
        for raw in self._config_paths.values():
            abs_p = os.path.join(base, raw) if not os.path.isabs(raw) else raw
            if os.path.isdir(abs_p):
                paths.append(abs_p)
        if not paths:
            return
        self._size_worker = FolderSizeWorker(paths)
        self._size_worker.size_calculated.connect(self._tree.update_size)
        self._size_worker.start()

    def _setup_watcher(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for raw in self._config_paths.values():
            abs_p = os.path.join(base, raw) if not os.path.isabs(raw) else raw
            if os.path.isdir(abs_p) and abs_p not in self._watcher.directories():
                self._watcher.addPath(abs_p)
        self._watcher.directoryChanged.connect(self._on_dir_changed)

    def _on_file_selected(self, path: str):
        self._preview.show_file(path)

    def _on_folder_selected(self, path: str):
        self._file_table.load_folder(path)
        self._update_status()
        p = path
        self._status_path.setText(
            p if len(p) <= 60 else '...' + p[-57:]
        )

    def _on_dir_changed(self, path: str):
        if path == self._file_table._current_path:
            self._file_table.load_folder(path)
            self._update_status()

    def _update_status(self):
        n    = self._file_table.file_count()
        size = self._file_table.total_size()
        noun = 'файл' if n == 1 else ('файла' if 2 <= n <= 4 else 'файлов')
        self._status_files.setText(f'{n} {noun}')
        self._status_size.setText(human_size(size) if size > 0 else '')