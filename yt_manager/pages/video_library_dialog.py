# video_library_dialog.py — Диалог "Библиотека скачанных видео"
import webbrowser
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QWidget, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSortFilterProxyModel, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon

from db import db

DIALOG_STYLE = """
QDialog {
    background: #141312;
}
QFrame#dlg_header {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #181715, stop:1 #1a1917);
    border-bottom: 1px solid #2a2927;
}
QLabel#dlg_title { color: #f0ede8; font-size: 18px; font-weight: 800; }
QLabel#dlg_subtitle { color: #7a7875; font-size: 12px; }
QLabel#filter_label { color: #9f9d99; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
QLabel#stat_badge { color: #8fc3ca; font-size: 12px; font-weight: 700; }

QLineEdit#search_input {
    background: #1e1d1b; color: #e8e4df;
    border: 1px solid #343230; border-radius: 10px;
    padding: 8px 14px; font-size: 13px;
}
QLineEdit#search_input:focus { border-color: #4f98a3; }
QLineEdit#search_input::placeholder { color: #5a5856; }

QComboBox#filter_combo {
    background: #1e1d1b; color: #c8c4bf;
    border: 1px solid #343230; border-radius: 10px;
    padding: 7px 12px; font-size: 12px; font-weight: 600;
    min-width: 130px;
}
QComboBox#filter_combo:focus { border-color: #4f98a3; }
QComboBox#filter_combo::drop-down { border: none; width: 20px; }
QComboBox#filter_combo QAbstractItemView {
    background: #252320; border: 1px solid #343230;
    color: #c8c4bf; selection-background-color: #243337;
    border-radius: 8px; padding: 4px;
}

QPushButton#close_btn {
    background: #252320; color: #9a9793;
    border: 1px solid #343230; border-radius: 10px;
    padding: 8px 20px; font-size: 13px; font-weight: 700;
}
QPushButton#close_btn:hover { background: #2c2b28; color: #f0ede8; }
QPushButton#reset_btn {
    background: transparent; color: #7a7875;
    border: 1px solid #2e2c2a; border-radius: 9px;
    padding: 7px 14px; font-size: 11px; font-weight: 600;
}
QPushButton#reset_btn:hover { color: #c8c4bf; border-color: #4a4845; }

QTableWidget#lib_table {
    background: #161513; border: none;
    gridline-color: #1e1d1b; color: #e0dcd7;
    font-size: 12px; outline: none;
    alternate-background-color: #181614;
}
QTableWidget#lib_table::item { padding: 0px 10px; border: none; }
QTableWidget#lib_table::item:selected {
    background: #1e3336; color: #9ed4db;
}
QTableWidget#lib_table::item:hover { background: #1d2422; }
QHeaderView::section {
    background: #1a1917; color: #6e6b67;
    border: none; border-bottom: 2px solid #2a2927;
    padding: 10px; font-size: 11px; font-weight: 800;
    letter-spacing: 0.6px; text-transform: uppercase;
}
QHeaderView::section:hover { color: #a0a09a; }
QHeaderView::section::first { padding-left: 16px; }

QPushButton#yt_btn {
    background: #1e2e2f; color: #4f98a3;
    border: 1px solid #2e4446; border-radius: 8px;
    font-size: 11px; font-weight: 700; padding: 4px 10px;
    min-width: 56px;
}
QPushButton#yt_btn:hover { background: #4f98a3; color: #0a1e20; border-color: #4f98a3; }
QPushButton#yt_btn:pressed { background: #3a7d87; }

QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #2e2d2b; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal { background: transparent; height: 8px; }
QScrollBar::handle:horizontal { background: #2e2d2b; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

QFrame#filters_bar { background: #161513; border-bottom: 1px solid #222120; }
QFrame#footer_bar { background: #161513; border-top: 1px solid #222120; }
"""

STATUS_LABELS = {
    'new': 'Новое', 'queued': 'В очереди', 'downloading': 'Скачивается',
    'downloaded': 'Скачано', 'processing': 'Обработка',
    'processed': 'Обработано', 'error': 'Ошибка',
}
STATUS_COLORS = {
    'new': '#6e6b67', 'queued': '#e8af34', 'downloading': '#5591c7',
    'downloaded': '#4f98a3', 'processing': '#fdab43',
    'processed': '#6daa45', 'error': '#dd6974',
}


def _fmt_dur(secs):
    if not secs:
        return '—'
    s = int(secs)
    h, r = divmod(s, 3600)
    m, sc = divmod(r, 60)
    return f'{h}:{m:02d}:{sc:02d}' if h else f'{m}:{sc:02d}'


def _fmt_views(n):
    if n is None or n == 0:
        return '—'
    n = int(n)
    if n >= 1_000_000:
        return f'{n/1_000_000:.1f}M'
    if n >= 1_000:
        return f'{n/1_000:.1f}K'
    return str(n)


def _fmt_date(raw):
    if not raw:
        return '—'
    text = str(raw)[:19].replace('T', ' ')
    return text[:16]


class LoadWorker(QThread):
    ready = pyqtSignal(list, list)

    def run(self):
        try:
            channels = db.get_all_channels() or []
            videos = db.conn.cursor().execute(
                "SELECT * FROM videos WHERE status IN ('downloaded', 'processed') ORDER BY downloaded_at DESC, created_at DESC"
            ).fetchall()
            videos = [dict(v) for v in videos]
            ch_map = {c['id']: (c.get('title') or 'Без названия') for c in channels}
            for v in videos:
                v['_channel'] = ch_map.get(v.get('channel_id'), '—')
        except Exception:
            videos, channels = [], []
        self.ready.emit(videos, channels)


class VideoLibraryDialog(QDialog):
    def __init__(self, parent=None, filter_channel_id: int | None = None):
        super().__init__(parent)
        self.setObjectName('VideoLibraryDialog')
        self.setWindowTitle('Библиотека видео')
        self.resize(1320, 820)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(DIALOG_STYLE)
        self._all_rows = []
        self._filter_channel_id = filter_channel_id
        self._build_ui()
        QTimer.singleShot(80, self._load_data)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_filters())
        root.addWidget(self._build_table(), 1)
        root.addWidget(self._build_footer())

    def _build_header(self):
        hdr = QFrame()
        hdr.setObjectName('dlg_header')
        hdr.setFixedHeight(72)
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(24, 12, 24, 12)
        left = QVBoxLayout()
        left.setSpacing(2)
        t = QLabel('Библиотека скачанных видео')
        t.setObjectName('dlg_title')
        s = QLabel('Скачанные и обработанные видео · фильтр по каналу, дате, просмотрам')
        s.setObjectName('dlg_subtitle')
        left.addWidget(t)
        left.addWidget(s)
        lay.addLayout(left, 1)
        self._stat_lbl = QLabel('')
        self._stat_lbl.setObjectName('stat_badge')
        lay.addWidget(self._stat_lbl)
        lay.addSpacing(16)
        close = QPushButton('Закрыть')
        close.setObjectName('close_btn')
        close.clicked.connect(self.close)
        lay.addWidget(close)
        return hdr

    def _build_filters(self):
        bar = QFrame()
        bar.setObjectName('filters_bar')
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(10)

        lbl = QLabel('🔍')
        lbl.setStyleSheet('font-size:14px; color:#6e6b67;')
        lay.addWidget(lbl)

        self._search = QLineEdit()
        self._search.setObjectName('search_input')
        self._search.setPlaceholderText('Поиск по названию видео...')
        self._search.setFixedWidth(320)
        self._search.textChanged.connect(self._apply_filters)
        lay.addWidget(self._search)

        lay.addSpacing(4)

        self._ch_combo = QComboBox()
        self._ch_combo.setObjectName('filter_combo')
        self._ch_combo.addItem('Все каналы', None)
        self._ch_combo.currentIndexChanged.connect(self._apply_filters)
        lay.addWidget(self._ch_combo)

        self._date_combo = QComboBox()
        self._date_combo.setObjectName('filter_combo')
        for label, val in [('Любая дата', 0), ('Сегодня', 1), ('7 дней', 7), ('30 дней', 30), ('90 дней', 90)]:
            self._date_combo.addItem(label, val)
        self._date_combo.currentIndexChanged.connect(self._apply_filters)
        lay.addWidget(self._date_combo)

        self._views_combo = QComboBox()
        self._views_combo.setObjectName('filter_combo')
        for label, val in [('Любые просмотры', 0), ('> 1K', 1000), ('> 10K', 10000), ('> 100K', 100000), ('> 1M', 1000000)]:
            self._views_combo.addItem(label, val)
        self._views_combo.currentIndexChanged.connect(self._apply_filters)
        lay.addWidget(self._views_combo)

        self._status_combo = QComboBox()
        self._status_combo.setObjectName('filter_combo')
        self._status_combo.addItem('Любой статус', None)
        for k, v in STATUS_LABELS.items():
            self._status_combo.addItem(v, k)
        self._status_combo.currentIndexChanged.connect(self._apply_filters)
        lay.addWidget(self._status_combo)

        lay.addStretch(1)

        reset = QPushButton('Сбросить')
        reset.setObjectName('reset_btn')
        reset.clicked.connect(self._reset_filters)
        lay.addWidget(reset)

        return bar

    def _build_table(self):
        self._table = QTableWidget()
        self._table.setObjectName('lib_table')
        cols = ['Название видео', 'Канал', 'Дата скачивания', 'Длительность', 'Просмотры', 'Статус', '']
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(6, 76)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setRowHeight(0, 44)
        return self._table

    def _build_footer(self):
        bar = QFrame()
        bar.setObjectName('footer_bar')
        bar.setFixedHeight(42)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 0, 24, 0)
        self._footer_lbl = QLabel('Загрузка...')
        self._footer_lbl.setStyleSheet('color:#6e6b67; font-size:11px;')
        lay.addWidget(self._footer_lbl)
        lay.addStretch(1)
        tip = QLabel('Кликни по заголовку столбца чтобы отсортировать')
        tip.setStyleSheet('color:#4a4846; font-size:11px;')
        lay.addWidget(tip)
        return bar

    def _load_data(self):
        self._worker = LoadWorker()
        self._worker.ready.connect(self._on_data)
        self._worker.start()

    def _on_data(self, videos, channels):
        self._all_rows = videos
        # заполняем комбо каналов
        seen = {}
        for v in videos:
            ch = v.get('_channel', '—')
            cid = v.get('channel_id')
            if cid not in seen:
                seen[cid] = ch
        self._ch_combo.blockSignals(True)
        self._ch_combo.clear()
        self._ch_combo.addItem('Все каналы', None)
        for cid, name in sorted(seen.items(), key=lambda x: x[1]):
            self._ch_combo.addItem(name, cid)
        # если передан channel_id — выбираем его
        if self._filter_channel_id is not None:
            for i in range(self._ch_combo.count()):
                if self._ch_combo.itemData(i) == self._filter_channel_id:
                    self._ch_combo.setCurrentIndex(i)
                    break
        self._ch_combo.blockSignals(False)
        self._apply_filters()

    def _reset_filters(self):
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._ch_combo.setCurrentIndex(0)
        self._date_combo.setCurrentIndex(0)
        self._views_combo.setCurrentIndex(0)
        self._status_combo.setCurrentIndex(0)
        self._apply_filters()

    def _apply_filters(self):
        query = self._search.text().strip().lower()
        ch_id = self._ch_combo.currentData()
        days = self._date_combo.currentData() or 0
        min_views = self._views_combo.currentData() or 0
        status_key = self._status_combo.currentData()
        cutoff = (datetime.now() - timedelta(days=days)) if days > 0 else None

        filtered = []
        for v in self._all_rows:
            if query and query not in (v.get('title') or '').lower():
                continue
            if ch_id is not None and v.get('channel_id') != ch_id:
                continue
            if min_views > 0 and (v.get('view_count') or 0) < min_views:
                continue
            if status_key and v.get('status') != status_key:
                continue
            if cutoff:
                raw = v.get('downloaded_at') or v.get('created_at')
                if not raw:
                    continue
                try:
                    dt = datetime.fromisoformat(str(raw)[:19])
                    if dt < cutoff:
                        continue
                except Exception:
                    continue
            filtered.append(v)

        self._render_table(filtered)
        total = len(self._all_rows)
        shown = len(filtered)
        self._stat_lbl.setText(f'{shown:,} из {total:,} видео')
        self._footer_lbl.setText(f'Показано: {shown:,} · Всего в базе: {total:,}')

    def _render_table(self, rows):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))
        for i, v in enumerate(rows):
            self._table.setRowHeight(i, 44)
            title = QTableWidgetItem(v.get('title') or '—')
            title.setForeground(QColor('#e8e4df'))
            channel = QTableWidgetItem(v.get('_channel', '—'))
            channel.setForeground(QColor('#8f8c87'))
            date_item = QTableWidgetItem(_fmt_date(v.get('downloaded_at') or v.get('created_at')))
            date_item.setForeground(QColor('#75736f'))
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            dur_secs = v.get('duration') or 0
            dur_item = QTableWidgetItem(_fmt_dur(dur_secs))
            dur_item.setData(Qt.ItemDataRole.UserRole, dur_secs)
            dur_item.setForeground(QColor('#9a9793'))
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            views_n = v.get('view_count') or 0
            views_item = QTableWidgetItem(_fmt_views(views_n))
            views_item.setData(Qt.ItemDataRole.UserRole, views_n)
            views_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if views_n >= 1_000_000:
                views_item.setForeground(QColor('#e8af34'))
            elif views_n >= 100_000:
                views_item.setForeground(QColor('#fdab43'))
            elif views_n >= 10_000:
                views_item.setForeground(QColor('#4f98a3'))
            else:
                views_item.setForeground(QColor('#75736f'))
            sk = v.get('status', 'new')
            status_item = QTableWidgetItem(STATUS_LABELS.get(sk, sk))
            status_item.setForeground(QColor(STATUS_COLORS.get(sk, '#6e6b67')))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            for col, item in enumerate([title, channel, date_item, dur_item, views_item, status_item]):
                self._table.setItem(i, col, item)
            yt_id = v.get('yt_id', '')
            if yt_id:
                btn = QPushButton('▶ YouTube')
                btn.setObjectName('yt_btn')
                url = f'https://www.youtube.com/watch?v={yt_id}'
                btn.clicked.connect(lambda _, u=url: webbrowser.open(u))
                cell = QWidget()
                cl = QHBoxLayout(cell)
                cl.setContentsMargins(8, 6, 8, 6)
                cl.addWidget(btn)
                self._table.setCellWidget(i, 6, cell)
        self._table.setSortingEnabled(True)
