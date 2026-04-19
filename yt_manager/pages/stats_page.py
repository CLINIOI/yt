# stats_page.py — redesigned analytics dashboard

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, Counter

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QButtonGroup
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPointF
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QPainterPath, QLinearGradient
)

from pages.base_page import BasePage
from db import db
from pages.video_library_dialog import VideoLibraryDialog

PAGE_STYLE = """
QFrame#stats_toolbar {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #181715, stop:0.55 #1d1c1a, stop:1 #161614);
    border-bottom:1px solid #2b2a28;
}
QLabel#stats_title { color:#f3f1ee; font-size:18px; font-weight:700; }
QLabel#stats_subtitle { color:#7f7d79; font-size:12px; }
QPushButton#refresh_btn {
    background:#232220; color:#d0ceca; border:1px solid #343331;
    border-radius:10px; padding:7px 14px; font-size:12px; font-weight:600;
}
QPushButton#refresh_btn:hover { background:#2a2926; border-color:#4f98a3; }
QPushButton#period_btn {
    background:#232220; color:#7f7d79; border:1px solid #343331;
    border-radius:9px; padding:6px 12px; font-size:11px; font-weight:700;
}
QPushButton#period_btn:hover:!checked { color:#f3f1ee; border-color:#4b4a46; }
QPushButton#period_btn:checked {
    background:#243337; color:#8fc3ca; border:1px solid #4f98a3;
}
QScrollArea { border:none; background:transparent; }
QFrame#hero_panel, QFrame#section_card, QFrame#kpi_card {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #1d1c1a, stop:1 #171614);
    border:1px solid #2f2d2b;
    border-radius:16px;
}
QFrame#hero_panel { border-radius:20px; }
QLabel#hero_eyebrow {
    color:#8fc3ca; font-size:11px; font-weight:800; letter-spacing:1px;
}
QLabel#hero_title { color:#f4f1ee; font-size:28px; font-weight:800; }
QLabel#hero_text { color:#9f9d99; font-size:12px; }
QLabel#hero_value { color:#f4f1ee; font-size:26px; font-weight:800; }
QLabel#hero_label { color:#7f7d79; font-size:11px; text-transform:uppercase; }
QLabel#hero_note { color:#8fc3ca; font-size:11px; font-weight:600; }
QLabel#section_title {
    color:#e9e6e2; font-size:13px; font-weight:800; letter-spacing:0.4px;
}
QLabel#section_hint { color:#7f7d79; font-size:11px; }
QLabel#kpi_icon { font-size:20px; }
QLabel#kpi_value { color:#f4f1ee; font-size:24px; font-weight:800; }
QLabel#kpi_label { color:#b1afaa; font-size:12px; font-weight:600; }
QLabel#kpi_sub { color:#75736f; font-size:11px; }
QLabel#metric_name { color:#c7c4bf; font-size:12px; font-weight:600; }
QLabel#metric_value { color:#f4f1ee; font-size:15px; font-weight:800; }
QFrame#line_div { background:#2b2a28; max-height:1px; min-height:1px; }
QTableWidget#act_table {
    background:transparent; border:none; gridline-color:#232220;
    color:#e8e4df; font-size:12px; outline:none;
}
QTableWidget#act_table::item { padding:6px 8px; }
QTableWidget#act_table::item:selected { background:#243337; color:#9ed4db; }
QHeaderView::section {
    background:#201f1d; color:#7f7d79; border:none; border-bottom:1px solid #2f2d2b;
    padding:8px; font-size:11px; font-weight:700;
}
QScrollBar:vertical { background:transparent; width:8px; }
QScrollBar::handle:vertical { background:#3b3936; border-radius:4px; min-height:24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }

QPushButton#lib_btn {
    background:#1e2e2f; color:#4f98a3;
    border:1px solid #2e4446; border-radius:10px;
    padding:7px 16px; font-size:12px; font-weight:700;
}
QPushButton#lib_btn:hover { background:#4f98a3; color:#0a1e20; border-color:#4f98a3; }
"""

ACCENT = {
    'teal': '#4f98a3',
    'green': '#6daa45',
    'gold': '#e8af34',
    'orange': '#fdab43',
    'blue': '#5591c7',
    'purple': '#a86fdf',
    'red': '#dd6974',
    'brown': '#bb653b',
    'muted': '#7f7d79',
}

STATUS_META = {
    'new': ('Новые', '#7f7d79'),
    'queued': ('В очереди', '#e8af34'),
    'downloading': ('Загружаются', '#5591c7'),
    'downloaded': ('Загружены', '#4f98a3'),
    'processing': ('Обрабатываются', '#a86fdf'),
    'processed': ('Обработаны', '#6daa45'),
    'error': ('С ошибкой', '#dd6974'),
}

CHANNEL_COLORS = ['#4f98a3', '#6daa45', '#e8af34', '#fdab43', '#5591c7', '#a86fdf', '#dd6974', '#bb653b']


@dataclass
class StatsSnapshot:
    channels_count: int = 0
    videos_total: int = 0
    videos_downloaded: int = 0
    videos_processed: int = 0
    queued_videos: int = 0
    error_videos: int = 0
    error_percent: float = 0.0
    uploaded_today: int = 0
    uploaded_7_days: int = 0
    channels_with_videos: int = 0
    channels_without_videos: int = 0
    avg_videos_per_channel: float = 0.0
    avg_downloads_per_day: float = 0.0
    active_days: int = 0
    best_day: str = '—'
    best_day_count: int = 0
    uploaded_share: float = 0.0
    processed_share: float = 0.0
    most_active_channel: str = '—'
    most_active_channel_count: int = 0
    per_channel: list = field(default_factory=list)
    by_status: dict = field(default_factory=dict)
    by_date: list = field(default_factory=list)
    recent: list = field(default_factory=list)


class StatsWorker(QThread):
    ready = pyqtSignal(object)

    def __init__(self, days: int, parent=None):
        super().__init__(parent)
        self._days = days

    @staticmethod
    def _parse_dt(raw):
        if not raw:
            return None
        text = str(raw).replace('Z', '')
        for candidate in (text, text[:19]):
            try:
                return datetime.fromisoformat(candidate)
            except Exception:
                pass
        return None

    def run(self):
        snap = StatsSnapshot()
        try:
            channels = db.get_all_channels() or []
            videos = db.conn.cursor().execute('SELECT * FROM videos').fetchall()
            videos = [dict(v) for v in videos]
            queue_rows = db.conn.cursor().execute('SELECT * FROM download_queue').fetchall()
            queue_rows = [dict(r) for r in queue_rows]
        except Exception:
            self.ready.emit(snap)
            return

        now = datetime.now()
        ch_map = {c['id']: (c.get('title') or 'Без названия') for c in channels}
        snap.channels_count = len(channels)
        snap.videos_total = len(videos)

        per_channel = defaultdict(int)
        by_status = Counter()
        by_day = defaultdict(int)
        channels_with_videos = set()
        recent_candidates = []

        for v in videos:
            status = (v.get('status') or 'new').strip()
            by_status[status] += 1
            if status in ('downloaded', 'processed'):
                snap.videos_downloaded += 1
            if status == 'processed':
                snap.videos_processed += 1
            if status == 'error':
                snap.error_videos += 1
            if status in ('queued', 'downloading'):
                snap.queued_videos += 1

            ch_name = ch_map.get(v.get('channel_id'), 'Неизвестно')
            per_channel[ch_name] += 1
            channels_with_videos.add(v.get('channel_id'))

            dt = self._parse_dt(v.get('downloaded_at')) or self._parse_dt(v.get('created_at'))
            if dt:
                day_key = dt.strftime('%Y-%m-%d')
                by_day[day_key] += 1
                if dt.date() == now.date():
                    snap.uploaded_today += 1
                if dt >= now - timedelta(days=7):
                    snap.uploaded_7_days += 1
                recent_candidates.append((dt, v, ch_name))

        snap.by_status = dict(by_status)
        snap.channels_with_videos = len([c for c in channels if c['id'] in channels_with_videos])
        snap.channels_without_videos = max(0, snap.channels_count - snap.channels_with_videos)
        snap.avg_videos_per_channel = (snap.videos_total / snap.channels_count) if snap.channels_count else 0.0
        snap.error_percent = (snap.error_videos / snap.videos_total * 100) if snap.videos_total else 0.0
        snap.uploaded_share = (snap.videos_downloaded / snap.videos_total * 100) if snap.videos_total else 0.0
        snap.processed_share = (snap.videos_processed / snap.videos_downloaded * 100) if snap.videos_downloaded else 0.0
        snap.active_days = len([d for d, cnt in by_day.items() if cnt > 0])

        period_days = max(self._days, 1)
        days = []
        for i in range(period_days - 1, -1, -1):
            d = (now - timedelta(days=i)).strftime('%Y-%m-%d')
            days.append((d, by_day.get(d, 0)))
        snap.by_date = days
        total_period_uploads = sum(v for _, v in days)
        snap.avg_downloads_per_day = total_period_uploads / period_days if period_days else 0.0

        if by_day:
            best_day, best_count = max(by_day.items(), key=lambda x: x[1])
            snap.best_day = best_day
            snap.best_day_count = best_count

        if per_channel:
            snap.per_channel = sorted(per_channel.items(), key=lambda x: (-x[1], x[0]))[:12]
            snap.most_active_channel, snap.most_active_channel_count = snap.per_channel[0]

        q_pending = sum(1 for q in queue_rows if (q.get('status') or '') == 'pending')
        if q_pending > snap.queued_videos:
            snap.queued_videos = q_pending

        recent_candidates.sort(key=lambda x: x[0], reverse=True)
        snap.recent = []
        for dt, v, ch_name in recent_candidates[:50]:
            row = dict(v)
            row['_channel'] = ch_name
            row['_activity_dt'] = dt.strftime('%Y-%m-%d %H:%M')
            snap.recent.append(row)

        self.ready.emit(snap)


class StatCard(QFrame):
    def __init__(self, icon: str, title: str, accent: str, subtitle: str = '', parent=None):
        super().__init__(parent)
        self.setObjectName('kpi_card')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(118)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        icon_lbl = QLabel(icon)
        icon_lbl.setObjectName('kpi_icon')
        icon_lbl.setStyleSheet(f'color:{accent};')
        top.addWidget(icon_lbl)
        top.addStretch(1)
        lay.addLayout(top)
        self.value = QLabel('—')
        self.value.setObjectName('kpi_value')
        lay.addWidget(self.value)
        self.title = QLabel(title)
        self.title.setObjectName('kpi_label')
        lay.addWidget(self.title)
        self.sub = QLabel(subtitle)
        self.sub.setObjectName('kpi_sub')
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)

    def set_value(self, value: str, subtitle: str | None = None):
        self.value.setText(value)
        if subtitle is not None:
            self.sub.setText(subtitle)


class MetricRow(QFrame):
    def __init__(self, label: str, accent: str = '#4f98a3', parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        dot = QLabel('●')
        dot.setStyleSheet(f'color:{accent}; font-size:12px;')
        lay.addWidget(dot)
        self.name = QLabel(label)
        self.name.setObjectName('metric_name')
        lay.addWidget(self.name, 1)
        self.value = QLabel('—')
        self.value.setObjectName('metric_value')
        lay.addWidget(self.value)

    def set_value(self, text: str):
        self.value.setText(text)


class SectionCard(QFrame):
    def __init__(self, title: str, hint: str = '', parent=None):
        super().__init__(parent)
        self.setObjectName('section_card')
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(14)
        head = QVBoxLayout()
        head.setSpacing(2)
        ttl = QLabel(title)
        ttl.setObjectName('section_title')
        head.addWidget(ttl)
        if hint:
            h = QLabel(hint)
            h.setObjectName('section_hint')
            h.setWordWrap(True)
            head.addWidget(h)
        self.layout.addLayout(head)

    def add_divider(self):
        line = QFrame()
        line.setObjectName('line_div')
        self.layout.addWidget(line)


class BarChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self.setMinimumHeight(260)

    def set_data(self, data: list):
        self._data = data[:10]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#181715'))
        if not self._data:
            p.setPen(QColor('#5f5d59'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Нет данных по каналам')
            return
        W, H = self.width(), self.height()
        left, right, top, bottom = 138, 18, 8, 12
        rows = len(self._data)
        row_h = max(28, (H - top - bottom) // max(rows, 1))
        max_val = max(v for _, v in self._data) or 1
        font = QFont('Segoe UI', 10)
        p.setFont(font)
        fm = QFontMetrics(font)
        for i, (label, value) in enumerate(self._data):
            y = top + i * row_h
            bar_y = y + 6
            bar_h = min(16, row_h - 10)
            p.setPen(QColor('#8f8c87'))
            short = fm.elidedText(label, Qt.TextElideMode.ElideRight, left - 16)
            p.drawText(0, y + 18, short)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#242321'))
            p.drawRoundedRect(left, bar_y, W - left - right, bar_h, 8, 8)
            width = int((W - left - right) * value / max_val)
            grad = QLinearGradient(left, bar_y, left + max(width, 1), bar_y)
            grad.setColorAt(0, QColor('#4f98a3'))
            grad.setColorAt(1, QColor(CHANNEL_COLORS[i % len(CHANNEL_COLORS)]))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(left, bar_y, max(width, 6), bar_h, 8, 8)
            p.setPen(QColor('#ece8e2'))
            p.drawText(left + width + 8, y + 18, str(value))


class DonutWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments = []
        self._center_text = '0'
        self.setMinimumHeight(250)

    def set_data(self, segments: list, center_text: str):
        self._segments = segments
        self._center_text = center_text
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#181715'))
        W, H = self.width(), self.height()
        if not self._segments:
            p.setPen(QColor('#5f5d59'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Нет данных по статусам')
            return
        donut_w = min(220, W // 2)
        size = min(donut_w, H - 20)
        cx, cy = donut_w // 2 + 12, H // 2
        outer_r = size // 2
        inner_r = int(outer_r * 0.62)
        total = sum(v for _, v, _ in self._segments) or 1
        start = -90 * 16
        p.setPen(Qt.PenStyle.NoPen)
        for label, value, color in self._segments:
            span = int(360 * 16 * value / total)
            p.setBrush(QColor(color))
            p.drawPie(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2, start, span)
            start += span
        p.setBrush(QColor('#181715'))
        p.drawEllipse(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2)
        f = QFont('Segoe UI', 10)
        f.setPixelSize(24)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor('#f3f1ee'))
        p.drawText(QRect(cx - inner_r, cy - 18, inner_r * 2, 28), Qt.AlignmentFlag.AlignCenter, self._center_text)
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(QColor('#7f7d79'))
        p.drawText(QRect(cx - inner_r, cy + 8, inner_r * 2, 20), Qt.AlignmentFlag.AlignCenter, 'видео всего')
        lx = donut_w + 24
        ly = max(20, cy - len(self._segments) * 20)
        p.setFont(QFont('Segoe UI', 10))
        fm = QFontMetrics(p.font())
        for label, value, color in self._segments:
            pct = round(value * 100 / total)
            p.setBrush(QColor(color))
            p.drawEllipse(lx, ly + 4, 9, 9)
            p.setPen(QColor('#d7d3cd'))
            p.drawText(lx + 16, ly + fm.ascent() + 1, label)
            p.setPen(QColor('#7f7d79'))
            p.drawText(lx + 16, ly + fm.ascent() + 15, f'{value} · {pct}%')
            ly += 34


class ActivityLineChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []
        self.setMinimumHeight(220)

    def set_data(self, data: list):
        self._data = data
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#181715'))
        W, H = self.width(), self.height()
        if not self._data or all(v == 0 for _, v in self._data):
            p.setPen(QColor('#5f5d59'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'За выбранный период активности нет')
            return
        left, right, top, bottom = 38, 18, 16, 34
        chart_w, chart_h = W - left - right, H - top - bottom
        n = len(self._data)
        max_val = max(v for _, v in self._data) or 1
        def pos(i, v):
            x = left + (chart_w * i / max(n - 1, 1))
            y = top + chart_h - (chart_h * v / max_val)
            return QPointF(x, y)
        grid_pen = QPen(QColor('#2b2a28'), 1, Qt.PenStyle.DashLine)
        p.setFont(QFont('Segoe UI', 9))
        for step in range(1, 5):
            y = top + chart_h - (chart_h * step / 4)
            p.setPen(grid_pen)
            p.drawLine(left, int(y), W - right, int(y))
            p.setPen(QColor('#66635f'))
            p.drawText(4, int(y) + 4, str(int(max_val * step / 4)))
        fill = QPainterPath()
        first = pos(0, self._data[0][1])
        fill.moveTo(left, top + chart_h)
        fill.lineTo(first)
        line = QPainterPath(first)
        for i, (_, value) in enumerate(self._data[1:], start=1):
            pt = pos(i, value)
            line.lineTo(pt)
            fill.lineTo(pt)
        fill.lineTo(left + chart_w, top + chart_h)
        fill.closeSubpath()
        grad = QLinearGradient(0, top, 0, top + chart_h)
        grad.setColorAt(0.0, QColor('#4f98a366'))
        grad.setColorAt(1.0, QColor('#4f98a30a'))
        p.fillPath(fill, QBrush(grad))
        p.setPen(QPen(QColor('#78b5be'), 2.5))
        p.drawPath(line)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#8fc3ca'))
        for i, (_, value) in enumerate(self._data):
            if value > 0:
                pt = pos(i, value)
                p.drawEllipse(pt, 3.5, 3.5)
        step = max(1, n // 6)
        p.setPen(QColor('#706d69'))
        for i in range(0, n, step):
            label = self._data[i][0][5:]
            pt = pos(i, 0)
            p.drawText(int(pt.x()) - 14, H - 10, label)


class ActivityTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('act_table')
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(['Канал', 'Видео', 'Дата', 'Статус'])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)

    def load(self, rows: list):
        self.setRowCount(0)
        for row_data in rows:
            row = self.rowCount()
            self.insertRow(row)
            channel = QTableWidgetItem(row_data.get('_channel', '—'))
            channel.setForeground(QColor('#8f8c87'))
            title = QTableWidgetItem(row_data.get('title') or '—')
            dt = QTableWidgetItem(row_data.get('_activity_dt', '—'))
            dt.setForeground(QColor('#75736f'))
            status_key = row_data.get('status', 'new')
            status_title, status_color = STATUS_META.get(status_key, (status_key, '#7f7d79'))
            status = QTableWidgetItem(status_title)
            status.setForeground(QColor(status_color))
            for col, item in enumerate([channel, title, dt, status]):
                self.setItem(row, col, item)


class StatsPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._period_days = 30
        self._worker = None
        self.setStyleSheet(PAGE_STYLE)
        self._build_ui()
        QTimer.singleShot(120, self.refresh)

    def _make_period_button(self, text: str, days: int, checked=False):
        btn = QPushButton(text)
        btn.setObjectName('period_btn')
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.clicked.connect(lambda: self._set_period(days))
        return btn

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName('stats_toolbar')
        bar.setFixedHeight(62)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 8, 18, 8)
        lay.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(0)
        title = QLabel('Статистика')
        title.setObjectName('stats_title')
        subtitle = QLabel('Стильная панель аналитики по каналам, статусам и загрузкам')
        subtitle.setObjectName('stats_subtitle')
        left.addWidget(title)
        left.addWidget(subtitle)
        lay.addLayout(left)
        lay.addStretch(1)
        self._period_group = QButtonGroup(self)
        for txt, days, checked in [('7D', 7, False), ('30D', 30, True), ('90D', 90, False)]:
            btn = self._make_period_button(txt, days, checked)
            self._period_group.addButton(btn)
            lay.addWidget(btn)
        self._refresh_btn = QPushButton('Обновить')
        self._refresh_btn.setObjectName('refresh_btn')
        self._refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(self._refresh_btn)
        lib_btn = QPushButton('📋  Библиотека видео')
        lib_btn.setObjectName('lib_btn')
        lib_btn.clicked.connect(self._open_library)
        lay.addWidget(lib_btn)
        return bar

    def _build_hero(self):
        hero = QFrame()
        hero.setObjectName('hero_panel')
        lay = QHBoxLayout(hero)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(6)
        brow = QLabel('ANALYTICS OVERVIEW')
        brow.setObjectName('hero_eyebrow')
        left.addWidget(brow)
        title = QLabel('Живой срез по вашей базе видео')
        title.setObjectName('hero_title')
        title.setWordWrap(True)
        left.addWidget(title)
        text = QLabel('Сводка показывает объём базы, долю загруженных и обработанных видео, активность по дням и проблемные зоны.')
        text.setObjectName('hero_text')
        text.setWordWrap(True)
        left.addWidget(text)
        lay.addLayout(left, 2)
        right = QGridLayout()
        right.setHorizontalSpacing(16)
        right.setVerticalSpacing(10)
        self._hero_total = self._hero_metric('Всего видео')
        self._hero_downloaded = self._hero_metric('Загружено')
        self._hero_processed = self._hero_metric('Обработано')
        self._hero_error = self._hero_metric('Ошибки')
        right.addWidget(self._hero_total, 0, 0)
        right.addWidget(self._hero_downloaded, 0, 1)
        right.addWidget(self._hero_processed, 1, 0)
        right.addWidget(self._hero_error, 1, 1)
        lay.addLayout(right, 2)
        return hero

    def _hero_metric(self, label_text):
        box = QFrame()
        box.setStyleSheet('QFrame{background:#201f1d;border:1px solid #2e2c29;border-radius:14px;}')
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        value = QLabel('—')
        value.setObjectName('hero_value')
        label = QLabel(label_text)
        label.setObjectName('hero_label')
        note = QLabel('')
        note.setObjectName('hero_note')
        lay.addWidget(value)
        lay.addWidget(label)
        lay.addWidget(note)
        box._value = value
        box._note = note
        return box

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self._content = QVBoxLayout(inner)
        self._content.setContentsMargins(18, 18, 18, 24)
        self._content.setSpacing(18)
        self._content.addWidget(self._build_hero())

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(14)
        cards_grid.setVerticalSpacing(14)
        self.cards = {
            'channels': StatCard('📡', 'Каналов добавлено', ACCENT['teal']),
            'total': StatCard('🎞', 'Всего видео в базе', ACCENT['blue']),
            'downloaded': StatCard('⬇', 'Видео загружено', ACCENT['teal']),
            'processed': StatCard('⚙', 'Видео обработано', ACCENT['green']),
            'queue': StatCard('🕒', 'Видео в очереди', ACCENT['gold']),
            'error': StatCard('⚠', 'Видео с ошибкой', ACCENT['red']),
            'error_pct': StatCard('％', 'Процент ошибок', ACCENT['red']),
            'today': StatCard('☀', 'Загружено сегодня', ACCENT['orange']),
            'week': StatCard('📅', 'Загружено за 7 дней', ACCENT['purple']),
            'with_videos': StatCard('📁', 'Каналов с видео', ACCENT['green']),
            'without_videos': StatCard('🗂', 'Каналов без видео', ACCENT['muted']),
            'avg': StatCard('∿', 'Среднее видео на канал', ACCENT['blue']),
        }
        order = list(self.cards.values())
        idx = 0
        for r in range(3):
            for c in range(4):
                cards_grid.addWidget(order[idx], r, c)
                idx += 1
        cards_wrap = QWidget()
        cards_wrap.setLayout(cards_grid)
        self._content.addWidget(cards_wrap)

        middle = QGridLayout()
        middle.setHorizontalSpacing(18)
        middle.setVerticalSpacing(18)
        self._per_channel_card = SectionCard('Видео по каналам', 'Топ каналов по количеству записей в базе')
        self._bar_chart = BarChartWidget()
        self._per_channel_card.layout.addWidget(self._bar_chart)
        middle.addWidget(self._per_channel_card, 0, 0)

        self._status_card = SectionCard('Разбивка по статусам', 'Соотношение новых, загруженных, обработанных и проблемных видео')
        self._donut = DonutWidget()
        self._status_card.layout.addWidget(self._donut)
        middle.addWidget(self._status_card, 0, 1)
        self._content.addLayout(middle)

        trends = QGridLayout()
        trends.setHorizontalSpacing(18)
        trends.setVerticalSpacing(18)
        self._activity_card = SectionCard('Загрузки по дням', 'Динамика за выбранный период')
        self._line_chart = ActivityLineChart()
        self._activity_card.layout.addWidget(self._line_chart)
        trends.addWidget(self._activity_card, 0, 0)

        self._insights_card = SectionCard('Ключевые инсайты', 'Самый активный канал, средняя интенсивность и пиковые значения')
        self._m_active = MetricRow('Самый активный канал', ACCENT['teal'])
        self._m_avg_day = MetricRow('Среднее загрузок в день', ACCENT['blue'])
        self._m_best_day = MetricRow('День с максимумом загрузок', ACCENT['gold'])
        self._m_best_day_count = MetricRow('Количество загрузок в пиковый день', ACCENT['orange'])
        self._m_active_days = MetricRow('Дней с активностью', ACCENT['purple'])
        self._m_uploaded_share = MetricRow('% загруженных от всех', ACCENT['teal'])
        self._m_processed_share = MetricRow('% обработанных от загруженных', ACCENT['green'])
        rows = [
            self._m_active, self._m_avg_day, self._m_best_day, self._m_best_day_count,
            self._m_active_days, self._m_uploaded_share, self._m_processed_share,
        ]
        for i, row in enumerate(rows):
            self._insights_card.layout.addWidget(row)
            if i < len(rows) - 1:
                self._insights_card.add_divider()
        trends.addWidget(self._insights_card, 0, 1)
        self._content.addLayout(trends)

        self._recent_card = SectionCard('Последние 50 загрузок', 'Последние видео, попавшие в активность и загрузки')
        self._act_table = ActivityTable()
        self._recent_card.layout.addWidget(self._act_table)
        self._content.addWidget(self._recent_card)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)


    def _open_library(self):
        dlg = VideoLibraryDialog(self)
        dlg.exec()

    def _set_period(self, days: int):
        self._period_days = days
        self.refresh()

    def refresh(self):
        if self._worker and self._worker.isRunning():
            return
        self._refresh_btn.setText('Обновление...')
        self._worker = StatsWorker(self._period_days)
        self._worker.ready.connect(self._apply_snapshot)
        self._worker.finished.connect(lambda: self._refresh_btn.setText('Обновить'))
        self._worker.start()

    def _apply_snapshot(self, snap: StatsSnapshot):
        self._hero_total._value.setText(str(snap.videos_total))
        self._hero_total._note.setText(f'{snap.channels_count} каналов в базе')
        self._hero_downloaded._value.setText(str(snap.videos_downloaded))
        self._hero_downloaded._note.setText(f'{snap.uploaded_share:.1f}% от общего числа')
        self._hero_processed._value.setText(str(snap.videos_processed))
        self._hero_processed._note.setText(f'{snap.processed_share:.1f}% от загруженных')
        self._hero_error._value.setText(str(snap.error_videos))
        self._hero_error._note.setText(f'Ошибка у {snap.error_percent:.1f}% видео')

        self.cards['channels'].set_value(str(snap.channels_count), f'Каналов с видео: {snap.channels_with_videos}')
        self.cards['total'].set_value(str(snap.videos_total), f'Без видео: {snap.channels_without_videos}')
        self.cards['downloaded'].set_value(str(snap.videos_downloaded), f'Сегодня: {snap.uploaded_today}')
        self.cards['processed'].set_value(str(snap.videos_processed), f'За 7 дней: {snap.uploaded_7_days}')
        self.cards['queue'].set_value(str(snap.queued_videos), 'Очередь и активные загрузки')
        self.cards['error'].set_value(str(snap.error_videos), 'Требуют внимания')
        self.cards['error_pct'].set_value(f'{snap.error_percent:.1f}%', 'Доля ошибочных видео')
        self.cards['today'].set_value(str(snap.uploaded_today), 'За текущие сутки')
        self.cards['week'].set_value(str(snap.uploaded_7_days), 'За последние 7 дней')
        self.cards['with_videos'].set_value(str(snap.channels_with_videos), 'Каналы с активной базой')
        self.cards['without_videos'].set_value(str(snap.channels_without_videos), 'Каналы пока пустые')
        self.cards['avg'].set_value(f'{snap.avg_videos_per_channel:.1f}', 'Среднее наполнение')

        self._bar_chart.set_data(snap.per_channel)
        segments = []
        for key in ['new', 'queued', 'downloading', 'downloaded', 'processing', 'processed', 'error']:
            count = snap.by_status.get(key, 0)
            if count:
                label, color = STATUS_META[key]
                segments.append((label, count, color))
        self._donut.set_data(segments, str(snap.videos_total))
        self._line_chart.set_data(snap.by_date)
        self._act_table.load(snap.recent)

        active_line = snap.most_active_channel
        if snap.most_active_channel_count:
            active_line = f'{snap.most_active_channel} · {snap.most_active_channel_count}'
        self._m_active.set_value(active_line)
        self._m_avg_day.set_value(f'{snap.avg_downloads_per_day:.1f}')
        self._m_best_day.set_value(snap.best_day)
        self._m_best_day_count.set_value(str(snap.best_day_count))
        self._m_active_days.set_value(str(snap.active_days))
        self._m_uploaded_share.set_value(f'{snap.uploaded_share:.1f}%')
        self._m_processed_share.set_value(f'{snap.processed_share:.1f}%')
