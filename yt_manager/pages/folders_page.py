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
    QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QMenu, QAbstractItemView, QSizePolicy,
    QProgressBar, QScrollArea, QApplication, QMessageBox,
    QTabWidget,
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
            ('clips',       '✂   Нарезки'),
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
            # Рекурсивно для processed и clips
            if parent_type in ('processed', 'clips'):
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


def _format_duration(seconds: float) -> str:
    """H:MM:SS или M:SS."""
    try:
        s = int(float(seconds) or 0)
    except (TypeError, ValueError):
        return ''
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _lookup_duration_in_db(path: str) -> float:
    """Ищет длительность видео по file_path в таблице videos. 0.0 если нет."""
    try:
        row = db.conn.execute(
            "SELECT duration FROM videos WHERE file_path = ? LIMIT 1",
            (path,),
        ).fetchone()
        if row:
            return float(row["duration"] or 0.0)
    except Exception:
        pass
    return 0.0


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

    def filter_rows(self, query: str):
        """Скрывает строки, которые не матчат подстроку по имени файла."""
        q = (query or "").strip().lower()
        for r in range(self._table.rowCount()):
            it = self._table.item(r, self.COL_NAME)
            if not it:
                continue
            name = (it.text() or "").lower()
            self._table.setRowHidden(r, bool(q) and q not in name)

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

            # 1 — Длина видео. Ячейка заполнится в _on_duration_ready
            # (фоновый VideoDurationWorker через ffprobe). Для корректной
            # сортировки используется _NumItem c числовым UserRole.
            dur_item = _NumItem('')
            dur_item.setData(Qt.ItemDataRole.UserRole, 0)
            dur_item.setForeground(QColor('#5a5957'))
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if ext in VIDEO_EXTS:
                # Сначала пробуем достать duration из БД (быстрее ffprobe);
                # если нет — отдадим воркеру.
                db_dur = _lookup_duration_in_db(entry.path)
                if db_dur and db_dur > 0:
                    dur_item.setText(_format_duration(db_dur))
                    dur_item.setData(Qt.ItemDataRole.UserRole, float(db_dur))
                else:
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




class FolderNavigatorTable(QFrame):
    """Таблица-навигатор: показывает и папки, и файлы, поддерживает drill-in
    по двойному клику и рекурсивное сканирование.

    Колонки: Тип | Имя | Размер | Длительность | Дата | Формат [| Путь].
    Папки всегда сверху (через сортировочный ключ в колонке «Тип»).
    """

    file_selected  = pyqtSignal(str)
    folder_entered = pyqtSignal(str)   # путь новой папки (двойной клик)

    COL_TYPE = 0
    COL_NAME = 1
    COL_SIZE = 2
    COL_DUR  = 3
    COL_DATE = 4
    COL_FMT  = 5
    COL_PATH = 6  # только в рекурсивном режиме

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path = ''
        self._recursive = False
        self._dur_worker: VideoDurationWorker = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._empty = QLabel('\n📭\n\nПапка пуста')
        self._empty.setObjectName('empty_lbl')
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._empty)

        self._table = QTableWidget()
        self._table.setObjectName('file_table')
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ['ТИП', 'ИМЯ', 'РАЗМЕР', 'ДЛИНА', 'ДАТА', 'ФОРМАТ'])

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_TYPE, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(self.COL_SIZE, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(self.COL_DUR,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(self.COL_DATE, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(self.COL_FMT,  QHeaderView.ResizeMode.Fixed)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(self.COL_TYPE, Qt.SortOrder.AscendingOrder)

        self._table.setColumnWidth(self.COL_TYPE, 52)
        self._table.setColumnWidth(self.COL_SIZE, 92)
        self._table.setColumnWidth(self.COL_DUR,  80)
        self._table.setColumnWidth(self.COL_DATE, 140)
        self._table.setColumnWidth(self.COL_FMT,  70)

        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(False)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setDefaultSectionSize(32)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.hide()
        lay.addWidget(self._table, 1)

    # ── Загрузка ─────────────────────────────────────────────────────

    def set_recursive(self, on: bool):
        self._recursive = bool(on)
        if self._recursive and self._table.columnCount() == 6:
            self._table.setColumnCount(7)
            self._table.setHorizontalHeaderLabels(
                ['ТИП', 'ИМЯ', 'РАЗМЕР', 'ДЛИНА', 'ДАТА', 'ФОРМАТ', 'ПУТЬ'])
            self._table.horizontalHeader().setSectionResizeMode(
                self.COL_PATH, QHeaderView.ResizeMode.Stretch)
        elif not self._recursive and self._table.columnCount() == 7:
            self._table.setColumnCount(6)
            self._table.setHorizontalHeaderLabels(
                ['ТИП', 'ИМЯ', 'РАЗМЕР', 'ДЛИНА', 'ДАТА', 'ФОРМАТ'])
        if self._current_path:
            self.load_folder(self._current_path)

    def load_folder(self, path: str):
        self._current_path = path
        if self._dur_worker and self._dur_worker.isRunning():
            self._dur_worker.stop()

        if not os.path.isdir(path):
            self._show_empty(f'⚠\n\nПапка не найдена:\n{path}')
            return

        entries: list[dict] = []
        try:
            if self._recursive:
                for dirpath, _dnames, fnames in os.walk(path):
                    for fn in fnames:
                        full = os.path.join(dirpath, fn)
                        try:
                            st = os.stat(full)
                        except OSError:
                            continue
                        entries.append({
                            'is_dir': False, 'name': fn, 'path': full,
                            'size': st.st_size, 'mtime': st.st_mtime,
                        })
            else:
                for e in os.scandir(path):
                    try:
                        st = e.stat()
                    except OSError:
                        continue
                    if e.is_dir():
                        entries.append({
                            'is_dir': True, 'name': e.name, 'path': e.path,
                            'size': _folder_size(e.path), 'mtime': st.st_mtime,
                        })
                    elif e.is_file():
                        entries.append({
                            'is_dir': False, 'name': e.name, 'path': e.path,
                            'size': st.st_size, 'mtime': st.st_mtime,
                        })
        except PermissionError:
            pass

        if not entries:
            self._show_empty('📭\n\nПапка пуста')
            return

        self._empty.hide()
        self._table.show()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        video_paths: list[tuple[str, int]] = []  # (path, row)

        for ent in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            is_dir = ent['is_dir']
            name   = ent['name']
            ext    = '' if is_dir else os.path.splitext(name)[1].lower()
            icon   = '📁' if is_dir else EXT_ICONS.get(ext, '📄')

            # Тип (сортировочный ключ: 0=папка, 1=файл — папки сверху).
            type_item = _NumItem(icon)
            type_item.setData(Qt.ItemDataRole.UserRole, 0 if is_dir else 1)
            type_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, self.COL_TYPE, type_item)

            # Имя
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, ent['path'])
            name_item.setData(Qt.ItemDataRole.UserRole + 1,
                              'dir' if is_dir else 'file')
            self._table.setItem(row, self.COL_NAME, name_item)

            # Размер
            size_item = _NumItem(human_size(ent['size']))
            size_item.setData(Qt.ItemDataRole.UserRole, ent['size'])
            size_item.setForeground(QColor('#797876'))
            size_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, self.COL_SIZE, size_item)

            # Длительность (только для видео)
            dur_item = _NumItem('')
            dur_item.setData(Qt.ItemDataRole.UserRole, 0)
            dur_item.setForeground(QColor('#5a5957'))
            dur_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if not is_dir and ext in VIDEO_EXTS:
                db_dur = _lookup_duration_in_db(ent['path'])
                if db_dur and db_dur > 0:
                    dur_item.setText(_format_duration(db_dur))
                    dur_item.setData(Qt.ItemDataRole.UserRole, float(db_dur))
                else:
                    dur_item.setText('...')
                    video_paths.append((ent['path'], row))
            self._table.setItem(row, self.COL_DUR, dur_item)

            # Дата
            try:
                date_str = datetime.fromtimestamp(ent['mtime']).strftime(
                    '%Y-%m-%d  %H:%M')
            except (OSError, ValueError):
                date_str = '—'
            date_item = QTableWidgetItem(date_str)
            date_item.setData(Qt.ItemDataRole.UserRole, ent['mtime'])
            date_item.setForeground(QColor('#5a5957'))
            date_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, self.COL_DATE, date_item)

            # Формат
            if is_dir:
                fmt_text = '—'
            else:
                fmt_text = ext.lstrip('.') if ext else '—'
            fmt_item = QTableWidgetItem(fmt_text)
            fmt_item.setForeground(QColor('#3a3937'))
            fmt_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, self.COL_FMT, fmt_item)

            # Относительный путь (рекурсивный режим)
            if self._recursive and self._table.columnCount() > self.COL_PATH:
                try:
                    rel = os.path.relpath(os.path.dirname(ent['path']), path)
                except ValueError:
                    rel = ''
                rel_item = QTableWidgetItem(rel or '.')
                rel_item.setForeground(QColor('#5a5957'))
                self._table.setItem(row, self.COL_PATH, rel_item)

        self._table.setSortingEnabled(True)
        hdr = self._table.horizontalHeader()
        self._table.sortByColumn(hdr.sortIndicatorSection(),
                                 hdr.sortIndicatorOrder())

        if video_paths:
            paths_only = [p for p, _ in video_paths]
            self._dur_worker = VideoDurationWorker(paths_only)
            self._dur_worker.duration_ready.connect(self._on_duration_ready)
            self._dur_worker.start()

    def _show_empty(self, msg: str):
        self._empty.setText(f'\n{msg}')
        self._empty.show()
        self._table.hide()

    def _on_duration_ready(self, path: str, seconds: float):
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

    # ── Взаимодействие ───────────────────────────────────────────────

    def filter_rows(self, query: str):
        q = (query or '').strip().lower()
        for r in range(self._table.rowCount()):
            it = self._table.item(r, self.COL_NAME)
            if not it:
                continue
            name = (it.text() or '').lower()
            self._table.setRowHidden(r, bool(q) and q not in name)

    def _selected(self) -> tuple[str, str]:
        """Возвращает (path, kind) выбранной строки. kind = 'dir' | 'file'."""
        row = self._table.currentRow()
        if row < 0:
            return '', ''
        item = self._table.item(row, self.COL_NAME)
        if not item:
            return '', ''
        return (item.data(Qt.ItemDataRole.UserRole) or '',
                item.data(Qt.ItemDataRole.UserRole + 1) or '')

    def _on_selection_changed(self):
        path, kind = self._selected()
        if kind == 'file':
            self.file_selected.emit(path)
        else:
            self.file_selected.emit('')

    def _on_double_click(self):
        path, kind = self._selected()
        if not path:
            return
        if kind == 'dir':
            self.folder_entered.emit(path)
        elif kind == 'file' and os.path.isfile(path):
            open_with_player(path)

    def _show_context_menu(self, pos):
        path, kind = self._selected()
        if not path:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            'QMenu{background:#201f1d;color:#cdccca;border:1px solid #393836;}'
            'QMenu::item{padding:6px 20px;}'
            'QMenu::item:selected{background:#313b3b;color:#4f98a3;}'
            'QMenu::separator{background:#2d2c2a;height:1px;margin:4px 0;}'
        )
        if kind == 'dir':
            a = menu.addAction('📂  Открыть в проводнике')
            a.triggered.connect(lambda: open_in_explorer(path))
            a2 = menu.addAction('➡  Войти')
            a2.triggered.connect(lambda: self.folder_entered.emit(path))
        else:
            ext = os.path.splitext(path)[1].lower()
            if ext in VIDEO_EXTS:
                a = menu.addAction('▶  Открыть в плеере')
                a.triggered.connect(lambda: open_with_player(path))
            a2 = menu.addAction('📂  Показать в проводнике')
            a2.triggered.connect(lambda: open_in_explorer(path))
            menu.addSeparator()
            a3 = menu.addAction('📋  Копировать путь')
            a3.triggered.connect(
                lambda: QApplication.clipboard().setText(path))
        menu.exec(QCursor.pos())

    # ── Статистика (для статус-бара) ─────────────────────────────────

    def file_count(self) -> int:
        cnt = 0
        for r in range(self._table.rowCount()):
            kind_item = self._table.item(r, self.COL_NAME)
            if kind_item and kind_item.data(Qt.ItemDataRole.UserRole + 1) == 'file':
                cnt += 1
        return cnt

    def total_size(self) -> int:
        total = 0
        for r in range(self._table.rowCount()):
            kind_item = self._table.item(r, self.COL_NAME)
            if kind_item and kind_item.data(Qt.ItemDataRole.UserRole + 1) == 'file':
                s = self._table.item(r, self.COL_SIZE)
                if s:
                    total += s.data(Qt.ItemDataRole.UserRole) or 0
        return total


def _folder_size(path: str, limit_entries: int = 5000) -> int:
    """Быстрая (неглубокая) оценка размера папки. Ограничиваем общее число
    сканируемых файлов, чтобы при большом дереве не подвешивать UI."""
    total = 0
    count = 0
    try:
        for _dp, _dn, fns in os.walk(path):
            for fn in fns:
                count += 1
                if count > limit_entries:
                    return total
                try:
                    total += os.path.getsize(os.path.join(_dp, fn))
                except OSError:
                    pass
    except OSError:
        pass
    return total


class BreadcrumbBar(QFrame):
    """Хлебные крошки: сегменты-кнопки + «↑ вверх». Клик → переход."""

    crumb_clicked = pyqtSignal(str)  # путь сегмента
    up_clicked    = pyqtSignal()

    def __init__(self, root_path: str, root_label: str, parent=None):
        super().__init__(parent)
        self._root = os.path.normpath(root_path)
        self._root_label = root_label
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._current = self._root
        self._render()

    def _render(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        up = QPushButton('↑')
        up.setFixedSize(28, 24)
        up.setFlat(True)
        up.setToolTip('На уровень выше')
        up.clicked.connect(self.up_clicked.emit)
        self._layout.addWidget(up)

        # Сегменты от корня
        segments: list[tuple[str, str]] = [(self._root, self._root_label)]
        rel = os.path.relpath(self._current, self._root)
        if rel and rel != '.':
            acc = self._root
            for part in rel.replace('\\', '/').split('/'):
                if not part or part == '..':
                    continue
                acc = os.path.join(acc, part)
                segments.append((acc, part))

        for i, (path, label) in enumerate(segments):
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                'QPushButton{color:#cdccca;background:transparent;'
                'border:none;padding:2px 6px;font-size:12px;}'
                'QPushButton:hover{color:#4f98a3;}'
            )
            btn.clicked.connect(
                lambda _c=False, p=path: self.crumb_clicked.emit(p))
            self._layout.addWidget(btn)
            if i < len(segments) - 1:
                sep = QLabel('/')
                sep.setStyleSheet('color:#3a3937;')
                self._layout.addWidget(sep)
        self._layout.addStretch()

    def set_current(self, path: str):
        self._current = os.path.normpath(path)
        self._render()

    def current(self) -> str:
        return self._current

    def root(self) -> str:
        return self._root


class FolderTabPage(QWidget):
    """Одна вкладка страницы «Папки» — проводник с хлебными крошками,
    drill-in в подпапки и опциональным рекурсивным поиском."""

    def __init__(self, title: str, folder_path: str, parent=None):
        super().__init__(parent)
        self._root = os.path.normpath(folder_path)
        self._title = title
        try:
            os.makedirs(self._root, exist_ok=True)
        except Exception:
            pass

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        # Верхняя панель: крошки + кнопки
        head = QHBoxLayout()
        head.setSpacing(6)
        self._crumbs = BreadcrumbBar(self._root, title)
        self._crumbs.crumb_clicked.connect(self._navigate)
        self._crumbs.up_clicked.connect(self._go_up)
        head.addWidget(self._crumbs, 1)

        self._open_btn = QPushButton('📂 В системе')
        self._open_btn.setObjectName('tool_btn')
        self._open_btn.setToolTip('Открыть текущую папку в проводнике')
        self._open_btn.clicked.connect(self._open_current)
        head.addWidget(self._open_btn)

        self._refresh_btn = QPushButton('🔄')
        self._refresh_btn.setObjectName('tool_btn')
        self._refresh_btn.setFixedWidth(36)
        self._refresh_btn.clicked.connect(self.refresh)
        head.addWidget(self._refresh_btn)
        lay.addLayout(head)

        # Панель поиска + рекурсивный чекбокс
        from PyQt6.QtWidgets import QCheckBox
        tools = QHBoxLayout()
        tools.setSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText('Поиск по имени в текущем уровне…')
        self._search.setClearButtonEnabled(True)
        tools.addWidget(self._search, 1)
        self._rec_chk = QCheckBox('Искать во всех подпапках')
        self._rec_chk.setToolTip(
            'Показать файлы из всех вложенных папок в виде плоского списка')
        tools.addWidget(self._rec_chk)
        lay.addLayout(tools)

        # Содержимое: таблица + превью
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        self.table = FolderNavigatorTable()
        split.addWidget(self.table)
        self.preview = VideoPreviewPanel()
        split.addWidget(self.preview)
        split.setSizes([720, 280])
        lay.addWidget(split, 1)

        self.table.file_selected.connect(self.preview.show_file)
        self.table.folder_entered.connect(self._navigate)
        self._search.textChanged.connect(self.table.filter_rows)
        self._rec_chk.toggled.connect(self._on_recursive_toggled)

    def _navigate(self, path: str):
        if not path:
            return
        norm = os.path.normpath(path)
        # Защита от выхода выше корня
        root = os.path.normpath(self._root)
        try:
            common = os.path.commonpath([norm, root])
        except ValueError:
            common = ''
        if common != root:
            norm = root
        self._crumbs.set_current(norm)
        self._rec_chk.setChecked(False)  # при навигации сбрасываем рекурсию
        self.table.load_folder(norm)
        q = self._search.text()
        if q:
            self.table.filter_rows(q)

    def _go_up(self):
        cur = self._crumbs.current()
        if os.path.normpath(cur) == os.path.normpath(self._root):
            return
        self._navigate(os.path.dirname(cur))

    def _open_current(self):
        cur = self._crumbs.current()
        if cur:
            open_in_explorer(cur)

    def _on_recursive_toggled(self, on: bool):
        self.table.set_recursive(on)

    def refresh(self):
        cur = self._crumbs.current() or self._root
        if not os.path.isdir(cur):
            try:
                os.makedirs(cur, exist_ok=True)
            except Exception:
                pass
        self.table.load_folder(cur)
        q = self._search.text()
        if q:
            self.table.filter_rows(q)


class FoldersPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._config_paths = load_config_paths()
        self._size_worker: FolderSizeWorker = None
        self._watcher = QFileSystemWatcher(self)
        self._tab_pages: dict[str, FolderTabPage] = {}
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

    def _build_body(self) -> QWidget:
        """6 вкладок — по одной на каждую папку проекта.
        Каждая вкладка: поиск + сортируемая таблица + превью."""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            from utils import (
                DIR_DOWNLOADS, DIR_PROCESSED, DIR_CLIPS,
                DIR_BACKGROUNDS, DIR_BANNERS, DIR_RETENTION,
            )
        except Exception:
            # Фоллбэк, если утилиты ещё не обновлены
            DIR_DOWNLOADS = "загрузки"
            DIR_PROCESSED = "обработанное"
            DIR_CLIPS = "нарезки"
            DIR_BACKGROUNDS = "фон"
            DIR_BANNERS = "баннер"
            DIR_RETENTION = "удержание"

        specs = [
            ("Загрузки",      DIR_DOWNLOADS),
            ("Обработанное",  DIR_PROCESSED),
            ("Нарезки",       DIR_CLIPS),
            ("Фоны",          DIR_BACKGROUNDS),
            ("Баннеры",       DIR_BANNERS),
            ("Удержание",     DIR_RETENTION),
        ]

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        for title, dir_const in specs:
            abs_path = os.path.join(base, dir_const)
            page = FolderTabPage(title, abs_path, self)
            self._tabs.addTab(page, title)
            self._tab_pages[dir_const] = page
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Левая панель с использованием диска убрана — теперь её место
        # занимает статус-бар снизу. Но оставим DiskUsageWidget под
        # таблицей загрузок для наглядности.
        wrapper = QWidget()
        wlay = QVBoxLayout(wrapper)
        wlay.setContentsMargins(0, 0, 0, 0)
        wlay.addWidget(self._tabs, 1)

        dl_abs = os.path.join(base, DIR_DOWNLOADS)
        self._disk_widget = DiskUsageWidget(dl_abs)
        wlay.addWidget(self._disk_widget)
        return wrapper

    def _on_tab_changed(self, idx: int):
        page = self._tabs.widget(idx)
        if isinstance(page, FolderTabPage):
            page.refresh()

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
        self._full_refresh()
        self._setup_watcher()

    def _full_refresh(self):
        self._config_paths = load_config_paths()
        for p in self._tab_pages.values():
            p.refresh()
        self._disk_widget.refresh()
        self._start_size_worker()
        self._update_status()

    def _start_size_worker(self):
        if self._size_worker and self._size_worker.isRunning():
            return
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        paths = []
        for dir_const in self._tab_pages.keys():
            abs_p = os.path.join(base, dir_const)
            if os.path.isdir(abs_p):
                paths.append(abs_p)
        if not paths:
            return
        self._size_worker = FolderSizeWorker(paths)
        self._size_worker.start()

    def _setup_watcher(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for dir_const in self._tab_pages.keys():
            abs_p = os.path.join(base, dir_const)
            if os.path.isdir(abs_p) and abs_p not in self._watcher.directories():
                self._watcher.addPath(abs_p)
        self._watcher.directoryChanged.connect(self._on_dir_changed)

    def _on_dir_changed(self, path: str):
        for page in self._tab_pages.values():
            if getattr(page.table, '_current_path', '') == path:
                page.table.load_folder(path)

    def _update_status(self):
        total_files = 0
        total_size = 0
        for page in self._tab_pages.values():
            total_files += page.table.file_count()
            total_size += page.table.total_size()
        noun = 'файл' if total_files == 1 else (
            'файла' if 2 <= total_files <= 4 else 'файлов')
        self._status_files.setText(f'{total_files} {noun}')
        self._status_size.setText(human_size(total_size) if total_size > 0 else '')