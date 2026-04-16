# stats_page.py — Страница статистики
#
# KPICard           — карточка ключевой метрики
# BarChartWidget    — горизонтальная гистограмма (QPainter)
# DonutWidget       — кольцевая диаграмма (QPainter)
# ActivityLineChart — спарклайн-диаграмма по дням (QPainter)
# ActivityTable     — таблица последних загрузок
# StatsWorker       — фоновый сбор данных из БД
# StatsPage         — главная страница

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPoint
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QPainterPath, QLinearGradient,
)

from pages.base_page import BasePage
from db import db


# ──────────────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────────────

PAGE_STYLE = '''
QFrame#stats_toolbar { background:#1c1b19; border-bottom:1px solid #2d2c2a; }
QLabel#stats_title   { color:#cdccca; font-size:16px; font-weight:700; }

/* KPI card */
QFrame#kpi_card {
    background:#1c1b19; border:1px solid #2d2c2a;
    border-radius:10px;
}
QLabel#kpi_icon  { font-size:20px; }
QLabel#kpi_value {
    color:#cdccca; font-size:28px; font-weight:700;
    line-height:1;
}
QLabel#kpi_label { color:#5a5957; font-size:11px; }
QLabel#kpi_trend_up   { color:#6daa45; font-size:11px; }
QLabel#kpi_trend_down { color:#dd6974; font-size:11px; }
QLabel#kpi_trend_flat { color:#5a5957; font-size:11px; }

/* Chart containers */
QFrame#chart_frame {
    background:#1c1b19; border:1px solid #2d2c2a;
    border-radius:10px;
}
QLabel#chart_title {
    color:#797876; font-size:11px; font-weight:700;
    letter-spacing:0.5px;
}

/* Период */
QPushButton#period_btn {
    background:#201f1d; color:#5a5957;
    border:1px solid #2d2c2a; border-radius:5px;
    font-size:11px; font-weight:600;
    padding:4px 12px;
}
QPushButton#period_btn:checked {
    background:#313b3b; color:#4f98a3;
    border-color:#4f98a3;
}
QPushButton#period_btn:hover:!checked { color:#cdccca; }

/* Activity table */
QTableWidget#act_table {
    background:#1c1b19; border:none;
    gridline-color:#201f1d; outline:none;
    font-size:12px; color:#cdccca;
}
QTableWidget#act_table::item { padding:5px 8px; }
QTableWidget#act_table::item:selected {
    background:#313b3b; color:#4f98a3;
}
QHeaderView::section {
    background:#201f1d; color:#5a5957;
    font-size:11px; font-weight:600;
    border:none; padding:6px 8px;
    border-bottom:1px solid #2d2c2a;
}

/* Refresh button */
QPushButton#refresh_btn {
    background:#2d2c2a; color:#797876;
    border:none; border-radius:6px;
    font-size:12px; padding:5px 12px;
}
QPushButton#refresh_btn:hover { background:#393836; color:#cdccca; }

/* Scroll */
QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { background:transparent; width:5px; }
QScrollBar::handle:vertical {
    background:#393836; border-radius:2px; min-height:20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }

QLabel#no_data_lbl { color:#3a3937; font-size:13px; }
'''


# Палитра для нескольких каналов
CHANNEL_COLORS = [
    '#4f98a3', '#6daa45', '#e8af34', '#fdab43',
    '#5591c7', '#a86fdf', '#dd6974', '#bb653b',
]

STATUS_META = {
    'new':        ('Новые',       '#5a5957'),
    'downloaded': ('Загружены',   '#4f98a3'),
    'processed':  ('Обработаны',  '#6daa45'),
    'error':      ('Ошибка',      '#dd6974'),
}


# ──────────────────────────────────────────────────────────────────────
# МОДЕЛЬ ДАННЫХ
# ──────────────────────────────────────────────────────────────────────

@dataclass
class StatsSnapshot:
    channels_count:     int  = 0
    videos_total:       int  = 0
    videos_downloaded:  int  = 0
    videos_processed:   int  = 0
    per_channel: list        = field(default_factory=list)   # [(name, count)]
    by_status:   dict        = field(default_factory=dict)   # {status: count}
    by_date:     list        = field(default_factory=list)   # [(date_str, count)]
    recent:      list        = field(default_factory=list)   # [dict video+channel]


# ──────────────────────────────────────────────────────────────────────
# ФОНОВЫЙ ВОРКЕР
# ──────────────────────────────────────────────────────────────────────

class StatsWorker(QThread):
    ready = pyqtSignal(object)   # StatsSnapshot

    def __init__(self, days: int, parent=None):
        super().__init__(parent)
        self._days = days

    def run(self):
        snap = StatsSnapshot()
        try:
            channels  = db.get_channels() or []
            all_videos= db.get_videos()   or []
        except Exception:
            self.ready.emit(snap)
            return

        snap.channels_count = len(channels)
        snap.videos_total   = len(all_videos)

        ch_map = {ch['id']: ch.get('title', 'Без названия') for ch in channels}

        # Подсчёт по каналам
        per_ch: dict = defaultdict(int)
        by_status: dict = defaultdict(int)
        by_date: dict   = defaultdict(int)

        cutoff = datetime.now() - timedelta(days=self._days) if self._days > 0 else None

        for v in all_videos:
            status = v.get('status', 'new')
            by_status[status] += 1
            if status in ('downloaded', 'processed'):
                snap.videos_downloaded += 1
            if status == 'processed':
                snap.videos_processed += 1

            ch_title = ch_map.get(v.get('channel_id'), 'Неизвестно')
            per_ch[ch_title] += 1

            dl_at = v.get('downloaded_at') or v.get('created_at') or ''
            if dl_at:
                try:
                    dt = datetime.fromisoformat(str(dl_at)[:19])
                    if cutoff is None or dt >= cutoff:
                        by_date[dt.strftime('%Y-%m-%d')] += 1
                except ValueError:
                    pass

        snap.per_channel = sorted(per_ch.items(), key=lambda x: x[1], reverse=True)[:12]
        snap.by_status   = dict(by_status)

        # Временной ряд: заполняем нули для пропущенных дней
        days = self._days if self._days > 0 else 30
        date_range = []
        for i in range(days - 1, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            date_range.append((d, by_date.get(d, 0)))
        snap.by_date = date_range

        # Последние загрузки (50)
        try:
            recent_raw = sorted(
                [v for v in all_videos if v.get('downloaded_at')],
                key=lambda v: str(v.get('downloaded_at', '')),
                reverse=True,
            )[:50]
            snap.recent = [
                {**v, '_channel': ch_map.get(v.get('channel_id'), '—')}
                for v in recent_raw
            ]
        except Exception:
            pass

        self.ready.emit(snap)


# ──────────────────────────────────────────────────────────────────────
# KPI КАРТОЧКА
# ──────────────────────────────────────────────────────────────────────

class KPICard(QFrame):
    def __init__(self, icon: str, label: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName('kpi_card')
        self._accent = QColor(accent)
        self._build(icon, label)

    def _build(self, icon: str, label: str):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setObjectName('kpi_icon')
        self._icon_lbl.setStyleSheet(f'color:{self._accent.name()};')
        lay.addWidget(self._icon_lbl)

        lay.addSpacing(4)

        self._value_lbl = QLabel('—')
        self._value_lbl.setObjectName('kpi_value')
        lay.addWidget(self._value_lbl)

        self._label_lbl = QLabel(label)
        self._label_lbl.setObjectName('kpi_label')
        lay.addWidget(self._label_lbl)

        self._trend_lbl = QLabel('')
        self._trend_lbl.setObjectName('kpi_trend_flat')
        lay.addWidget(self._trend_lbl)

    def update(self, value: str, trend: str = '', trend_dir: str = 'flat'):
        self._value_lbl.setText(value)
        self._trend_lbl.setText(trend)
        self._trend_lbl.setObjectName(f'kpi_trend_{trend_dir}')
        self._trend_lbl.setStyleSheet(
            'color:#6daa45;' if trend_dir == 'up' else
            'color:#dd6974;' if trend_dir == 'down' else
            'color:#5a5957;'
        )


# ──────────────────────────────────────────────────────────────────────
# ГИСТОГРАММА (ГОРИЗОНТАЛЬНАЯ)
# ──────────────────────────────────────────────────────────────────────

class BarChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list = []   # [(label, value)]
        self.setMinimumHeight(60)

    def set_data(self, data: list):
        self._data = data[:12]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        PAD_L, PAD_R, PAD_T, PAD_B = 150, 50, 10, 10

        # Фон
        painter.fillRect(0, 0, W, H, QColor('#1c1b19'))

        if not self._data:
            painter.setPen(QColor('#3a3937'))
            painter.drawText(QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, 'Нет данных')
            painter.end()
            return

        chart_w = W - PAD_L - PAD_R
        chart_h = H - PAD_T - PAD_B
        n       = len(self._data)
        max_val = max(v for _, v in self._data) or 1

        bar_h = max(6, min(24, chart_h // n - 10))
        total_bars_h = bar_h * n
        gap  = (chart_h - total_bars_h) // (n + 1)

        font = QFont('Segoe UI', 10)
        font.setPixelSize(11)
        painter.setFont(font)
        fm = QFontMetrics(font)

        for i, (label, value) in enumerate(self._data):
            bar_y = PAD_T + gap + i * (bar_h + gap)
            bar_w = max(4, int(chart_w * value / max_val))
            cx    = bar_y + bar_h // 2

            # Фоновая дорожка
            painter.setBrush(QColor('#262523'))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(PAD_L, bar_y, chart_w, bar_h, 3, 3)

            # Заполненная часть
            color = QColor(CHANNEL_COLORS[i % len(CHANNEL_COLORS)])
            painter.setBrush(color)
            painter.drawRoundedRect(PAD_L, bar_y, bar_w, bar_h, 3, 3)

            # Метка слева
            short_label = label if len(label) <= 20 else label[:18] + '..'
            lbl_w = fm.horizontalAdvance(short_label)
            painter.setPen(QColor('#797876'))
            painter.drawText(
                PAD_L - lbl_w - 10,
                cx + fm.ascent() // 2 - 1,
                short_label,
            )

            # Значение справа
            painter.setPen(QColor('#5a5957'))
            painter.drawText(
                PAD_L + bar_w + 8,
                cx + fm.ascent() // 2 - 1,
                str(value),
            )

        painter.end()


# ──────────────────────────────────────────────────────────────────────
# КОЛЬЦЕВАЯ ДИАГРАММА
# ──────────────────────────────────────────────────────────────────────

class DonutWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list = []   # [(label, value, hex_color)]
        self._total_label = ''
        self.setMinimumSize(160, 160)

    def set_data(self, segments: list, total_label: str = ''):
        self._segments    = [s for s in segments if s[1] > 0]
        self._total_label = total_label
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        painter.fillRect(0, 0, W, H, QColor('#1c1b19'))

        if not self._segments:
            painter.setPen(QColor('#3a3937'))
            painter.drawText(QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, 'Нет данных')
            painter.end()
            return

        # Размещение: круг слева, легенда справа
        legend_w = 130
        donut_w  = W - legend_w
        size     = min(donut_w, H) - 24
        cx       = donut_w // 2
        cy       = H // 2
        outer_r  = size // 2
        inner_r  = int(outer_r * 0.62)

        total = sum(v for _, v, _ in self._segments) or 1
        start = -90 * 16

        # Секторы
        for label, value, color in self._segments:
            span = int(360 * 16 * value / total)
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPie(
                cx - outer_r, cy - outer_r,
                outer_r * 2, outer_r * 2,
                start, span,
            )
            start += span

        # Центральная «дыра»
        painter.setBrush(QColor('#1c1b19'))
        painter.drawEllipse(
            cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)

        # Центральный текст
        if self._total_label:
            font = QFont('Segoe UI', 10)
            font.setPixelSize(22)
            font.setWeight(QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor('#cdccca'))
            painter.drawText(
                QRect(cx - inner_r, cy - 16, inner_r * 2, 24),
                Qt.AlignmentFlag.AlignCenter,
                self._total_label,
            )
            font.setPixelSize(10)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QColor('#5a5957'))
            painter.drawText(
                QRect(cx - inner_r, cy + 8, inner_r * 2, 16),
                Qt.AlignmentFlag.AlignCenter, 'всего',
            )

        # Легенда
        font = QFont('Segoe UI', 10)
        font.setPixelSize(11)
        painter.setFont(font)
        fm   = QFontMetrics(font)
        lx   = donut_w + 10
        ly   = cy - len(self._segments) * 20 // 2

        for label, value, color in self._segments:
            pct = int(value * 100 / total)
            # Цветная точка
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(lx, ly + 3, 8, 8)
            # Метка
            painter.setPen(QColor('#797876'))
            painter.drawText(lx + 14, ly + fm.ascent(), label)
            # Значение
            val_str = f'{value} ({pct}%)'
            painter.setPen(QColor('#5a5957'))
            painter.drawText(lx + 14, ly + fm.ascent() + 13, val_str)
            ly += 36

        painter.end()


# ──────────────────────────────────────────────────────────────────────
# ЛИНЕЙНЫЙ ГРАФИК (ПО ДНЯМ)
# ──────────────────────────────────────────────────────────────────────

class ActivityLineChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list = []   # [(date_str, count)]
        self.setMinimumHeight(120)

    def set_data(self, data: list):
        self._data = data
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        PAD_L, PAD_R, PAD_T, PAD_B = 40, 20, 16, 32
        painter.fillRect(0, 0, W, H, QColor('#1c1b19'))

        if not self._data or all(v == 0 for _, v in self._data):
            painter.setPen(QColor('#3a3937'))
            painter.drawText(
                QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter,
                'Нет активности за период'
            )
            painter.end()
            return

        chart_w = W - PAD_L - PAD_R
        chart_h = H - PAD_T - PAD_B
        n       = len(self._data)
        max_val = max(v for _, v in self._data) or 1

        def px(i, v):
            x = PAD_L + int(i * chart_w / max(n - 1, 1))
            y = PAD_T + chart_h - int(v * chart_h / max_val)
            return x, y

        # Горизонтальные сетки
        painter.setPen(QPen(QColor('#262523'), 1, Qt.PenStyle.DashLine))
        for step in [0.25, 0.5, 0.75, 1.0]:
            y = PAD_T + chart_h - int(step * chart_h)
            painter.drawLine(PAD_L, y, PAD_L + chart_w, y)
            lbl = str(int(max_val * step))
            painter.setPen(QColor('#3a3937'))
            fm = QFontMetrics(painter.font())
            painter.drawText(PAD_L - fm.horizontalAdvance(lbl) - 4, y + 4, lbl)
            painter.setPen(QPen(QColor('#262523'), 1, Qt.PenStyle.DashLine))

        # Заливка под линией
        path_fill = QPainterPath()
        bx0, by_base = px(0, 0)
        path_fill.moveTo(bx0, PAD_T + chart_h)
        for i, (_, v) in enumerate(self._data):
            x, y = px(i, v)
            path_fill.lineTo(x, y)
        bx_last, _ = px(n - 1, 0)
        path_fill.lineTo(bx_last, PAD_T + chart_h)
        path_fill.closeSubpath()

        grad = QLinearGradient(0, PAD_T, 0, PAD_T + chart_h)
        grad.setColorAt(0.0, QColor('#4f98a340'))
        grad.setColorAt(1.0, QColor('#4f98a308'))
        painter.fillPath(path_fill, QBrush(grad))

        # Линия
        path_line = QPainterPath()
        for i, (_, v) in enumerate(self._data):
            x, y = px(i, v)
            if i == 0:
                path_line.moveTo(x, y)
            else:
                path_line.lineTo(x, y)
        painter.setPen(QPen(QColor('#4f98a3'), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path_line)

        # Точки только для ненулевых значений
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#4f98a3'))
        for i, (_, v) in enumerate(self._data):
            if v > 0:
                x, y = px(i, v)
                painter.drawEllipse(QPoint(x, y), 4, 4)

        # Метки дат на оси X (каждые ~7 дней)
        font = painter.font()
        painter.setFont(font)
        fm = QFontMetrics(font)
        step = max(1, n // 6)
        for i in range(0, n, step):
            date_str = self._data[i][0][5:]   # MM-DD
            x, _ = px(i, 0)
            painter.setPen(QColor('#3a3937'))
            painter.drawText(
                x - fm.horizontalAdvance(date_str) // 2,
                H - PAD_B + 14,
                date_str,
            )

        painter.end()


# ──────────────────────────────────────────────────────────────────────
# ТАБЛИЦА АКТИВНОСТИ
# ──────────────────────────────────────────────────────────────────────

_STATUS_COLORS = {
    'new':        '#5a5957',
    'downloaded': '#4f98a3',
    'processed':  '#6daa45',
    'error':      '#dd6974',
}

class ActivityTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('act_table')
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(['Канал', 'Название видео', 'Дата', 'Статус'])
        self.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)

    def load(self, rows: list):
        self.setRowCount(0)
        for row_data in rows:
            row = self.rowCount()
            self.insertRow(row)

            ch   = row_data.get('_channel', '—')
            title= row_data.get('title', '—') or '—'
            dt   = str(row_data.get('downloaded_at', '') or '')[:16].replace('T', '  ')
            status = row_data.get('status', 'new')

            ch_item    = QTableWidgetItem(ch)
            ch_item.setForeground(QColor('#797876'))
            title_item = QTableWidgetItem(title)
            dt_item    = QTableWidgetItem(dt)
            dt_item.setForeground(QColor('#5a5957'))
            dt_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

            label, _ = STATUS_META.get(status, (status, '#5a5957'))
            st_item  = QTableWidgetItem(label)
            st_item.setForeground(QColor(_STATUS_COLORS.get(status, '#5a5957')))
            st_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

            for col, item in enumerate([ch_item, title_item, dt_item, st_item]):
                self.setItem(row, col, item)


# ──────────────────────────────────────────────────────────────────────
# ГЛАВНАЯ СТРАНИЦА
# ──────────────────────────────────────────────────────────────────────

class StatsPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._period_days = 30
        self._worker: StatsWorker = None
        self._build_ui()
        self.setStyleSheet(PAGE_STYLE)
        QTimer.singleShot(100, self.refresh)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self._content_lay = QVBoxLayout(inner)
        self._content_lay.setContentsMargins(20, 16, 20, 24)
        self._content_lay.setSpacing(16)
        self._build_content()
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName('stats_toolbar')
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 16, 0)
        lay.setSpacing(10)

        lbl = QLabel('Статистика')
        lbl.setObjectName('stats_title')
        lay.addWidget(lbl)
        lay.addStretch()

        # Переключатели периода
        self._period_group = QButtonGroup(self)
        for label, days in [('7д', 7), ('30д', 30), ('Всё', 0)]:
            btn = QPushButton(label)
            btn.setObjectName('period_btn')
            btn.setCheckable(True)
            btn.setChecked(days == 30)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, d=days: self._set_period(d))
            self._period_group.addButton(btn)
            lay.addWidget(btn)

        lay.addSpacing(8)
        refresh_btn = QPushButton('🔄  Обновить')
        refresh_btn.setObjectName('refresh_btn')
        refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(refresh_btn)
        return bar

    def _build_content(self):
        lay = self._content_lay

        # ── KPI Row ──
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self._kpi_channels   = KPICard('📺', 'Каналов добавлено',    '#4f98a3')
        self._kpi_downloaded = KPICard('🎬', 'Видео загружено',      '#5591c7')
        self._kpi_processed  = KPICard('✂',  'Видео обработано',     '#6daa45')
        self._kpi_total      = KPICard('📊', 'Всего в базе',         '#e8af34')
        for card in [self._kpi_channels, self._kpi_downloaded,
                     self._kpi_processed, self._kpi_total]:
            card.setFixedHeight(110)
            card.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Fixed)
            kpi_row.addWidget(card)
        lay.addLayout(kpi_row)

        # ── Charts Row: бар + кольцо ──
        charts_row = QHBoxLayout()
        charts_row.setSpacing(12)

        self._bar_frame = self._chart_frame('ЗАГРУЗКИ ПО КАНАЛАМ')
        self._bar_chart = BarChartWidget()
        self._bar_chart.setMinimumHeight(280)
        self._bar_frame.layout().addWidget(self._bar_chart)
        charts_row.addWidget(self._bar_frame, stretch=3)

        self._donut_frame = self._chart_frame('СТАТУС ВИДЕО')
        self._donut = DonutWidget()
        self._donut.setMinimumHeight(240)
        self._donut_frame.layout().addWidget(self._donut)
        charts_row.addWidget(self._donut_frame, stretch=2)
        lay.addLayout(charts_row)

        # ── Line chart: активность по дням ──
        self._line_frame = self._chart_frame('ЗАГРУЗКИ ПО ДНЯМ')
        self._line_chart = ActivityLineChart()
        self._line_chart.setFixedHeight(160)
        self._line_frame.layout().addWidget(self._line_chart)
        lay.addWidget(self._line_frame)

        # ── Таблица активности ──
        act_frame = self._chart_frame('ПОСЛЕДНИЕ ЗАГРУЗКИ')
        self._act_table = ActivityTable()
        self._act_table.setMinimumHeight(220)
        act_frame.layout().addWidget(self._act_table)
        lay.addWidget(act_frame)

    def _chart_frame(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName('chart_frame')
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(16, 12, 16, 14)
        fl.setSpacing(10)
        lbl = QLabel(title)
        lbl.setObjectName('chart_title')
        fl.addWidget(lbl)
        return frame

    # ── Обновление данных ─────────────────────────────────────────────

    def _set_period(self, days: int):
        self._period_days = days
        self.refresh()

    def refresh(self):
        if self._worker and self._worker.isRunning():
            return
        self._worker = StatsWorker(self._period_days)
        self._worker.ready.connect(self._apply_snapshot)
        self._worker.start()

    def _apply_snapshot(self, snap: StatsSnapshot):
        # KPI
        self._kpi_channels.update(str(snap.channels_count))
        self._kpi_downloaded.update(str(snap.videos_downloaded))
        self._kpi_processed.update(str(snap.videos_processed))
        self._kpi_total.update(str(snap.videos_total))

        # Бар-чарт
        self._bar_chart.set_data(snap.per_channel)
        rows_needed = max(3, len(snap.per_channel))
        self._bar_chart.setMinimumHeight(rows_needed * 36 + 20)

        # Кольцо
        segs = []
        for status, (label, _) in STATUS_META.items():
            cnt = snap.by_status.get(status, 0)
            if cnt:
                color = _STATUS_COLORS.get(status, '#5a5957')
                segs.append((label, cnt, color))
        self._donut.set_data(segs, str(snap.videos_total))

        # Линия
        self._line_chart.set_data(snap.by_date)

        # Таблица
        self._act_table.load(snap.recent)
