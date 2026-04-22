# pages/automation_page.py — Страница «Автоматизация»
#
# Управление автоматическим пайплайном для конкретного YouTube-канала:
#   • Фильтры видео (длительность, возраст, популярные в запас)
#   • Три блока-карточки (включаемые чекбоксами):
#       1. Скачивание — новые видео выбранного YouTube-канала
#       2. Монтаж     — обработка скачанного (cut/merge/stack)
#       3. Клипы      — физическая нарезка обработанного через ffmpeg,
#                       раскладка по привязанным TikTok-каналам через
#                       tiktok_youtube_link
#   • Авто-триггер: раз в 15 минут обходит YouTube-каналы с
#     включённой автоматизацией и добирает клипы для их TikTok-каналов
#
# Старая страница «Обработка» (ProcessingPage) остаётся отдельно —
# для ручной композиции.

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QVBoxLayout, QLineEdit,
)

from pages.base_page import BasePage
from db import db
from utils import sanitize_dirname, clean_video_name, get_project_base


log = logging.getLogger(__name__)


def _match_video_filters(v: dict, f: dict) -> bool:
    """Сопоставляет видео с фильтрами автоматизации."""
    dur = v.get("duration") or 0
    if dur < int(f.get("min_duration_sec") or 0):
        return False
    if dur > int(f.get("max_duration_sec") or 10 ** 9):
        return False
    if f.get("max_age_days"):
        upd = v.get("upload_date")
        if upd and len(upd) == 8:
            try:
                from datetime import datetime, timedelta
                d = datetime.strptime(upd, "%Y%m%d")
                if d < datetime.now() - timedelta(days=int(f["max_age_days"])):
                    return False
            except Exception:
                pass
    return True


# ──────────────────────────────────────────────────────────────────────
# ДИАЛОГИ
# ──────────────────────────────────────────────────────────────────────

class LinkTikTokDialog(QDialog):
    """Мини-диалог: выбрать существующий TikTok-канал или создать новый."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Привязать TikTok")
        self.setModal(True)
        self._selected_handle: Optional[str] = None

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Выберите существующий TikTok-канал или создайте новый:"))

        self.cmb = QComboBox()
        for tt in db.list_tiktok_channels():
            handle = tt.get("handle") or ""
            self.cmb.addItem(f"@{handle}", handle)
        if self.cmb.count() == 0:
            self.cmb.addItem("— нет TikTok-каналов —", None)
        lay.addWidget(self.cmb)

        row = QHBoxLayout()
        btn_new = QPushButton("Создать новый @handle…")
        btn_new.clicked.connect(self._on_create_new)
        row.addWidget(btn_new)
        row.addStretch()
        lay.addLayout(row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

    def _on_create_new(self):
        handle, ok = QInputDialog.getText(
            self, "Новый TikTok-канал",
            "Введите @handle (без пробелов):"
        )
        if not ok:
            return
        handle = handle.strip().lstrip("@")
        if not handle:
            QMessageBox.warning(self, "Пустой handle", "Укажите корректный handle.")
            return
        db.add_tiktok_channel(handle, display_name=handle)
        # обновить список
        self.cmb.clear()
        for tt in db.list_tiktok_channels():
            h = tt.get("handle") or ""
            self.cmb.addItem(f"@{h}", h)
        idx = self.cmb.findData(handle)
        if idx >= 0:
            self.cmb.setCurrentIndex(idx)

    def _on_accept(self):
        data = self.cmb.currentData()
        if not data:
            QMessageBox.warning(self, "Нет выбора", "Выберите или создайте TikTok-канал.")
            return
        self._selected_handle = str(data)
        self.accept()

    def selected_handle(self) -> Optional[str]:
        return self._selected_handle


class SelectTikTokDialog(QDialog):
    """Диалог выбора одного или нескольких TikTok-каналов
    из уже привязанных к данному YouTube-каналу."""

    def __init__(self, tiktoks: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выберите TikTok-канал")
        self.setModal(True)
        self._tiktoks = tiktoks
        self._selected_ids: list[int] = []

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Выберите TikTok-каналы для нарезки клипов:"))

        self.lst = QListWidget()
        for tt in tiktoks:
            item = QListWidgetItem(f"@{tt.get('handle', '')}")
            item.setData(Qt.ItemDataRole.UserRole, int(tt["id"]))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.lst.addItem(item)
        lay.addWidget(self.lst)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_ok(self):
        ids: list[int] = []
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                ids.append(int(it.data(Qt.ItemDataRole.UserRole)))
        if not ids:
            QMessageBox.warning(self, "Нет выбора", "Отметьте хотя бы один канал.")
            return
        self._selected_ids = ids
        self.accept()

    def selected_ids(self) -> list[int]:
        return list(self._selected_ids)


# ──────────────────────────────────────────────────────────────────────
# WORKER: физическая нарезка клипов
# ──────────────────────────────────────────────────────────────────────

class ClipPrepWorker(QThread):
    """Нарезает обработанные видео YouTube-канала на клипы заданной
    длительности через video_service.cut_video и регистрирует их в БД
    для каждого выбранного TikTok-канала."""

    progress   = pyqtSignal(str)          # сообщение в журнал
    finished_  = pyqtSignal(int, int)     # total_clips, total_videos
    failed     = pyqtSignal(str)

    def __init__(self,
                 channel_id: int,
                 tiktok_ids: list[int],
                 clip_duration: int,
                 parent=None):
        super().__init__(parent)
        self.channel_id     = int(channel_id)
        self.tiktok_ids     = [int(t) for t in tiktok_ids]
        self.clip_duration  = int(clip_duration)

    def run(self):
        try:
            from video_service import video_service
        except Exception as e:
            self.failed.emit(f"video_service недоступен: {e}")
            return

        videos = db.get_videos_by_channel(self.channel_id, status="processed")
        if not videos:
            self.progress.emit("Нет обработанных видео для нарезки.")
            self.finished_.emit(0, 0)
            return

        total_clips = 0
        total_videos = 0
        for v in videos:
            src = v.get("file_path")
            if not src or not os.path.isfile(src):
                self.progress.emit(f"Пропуск: файл не найден ({v.get('title') or v.get('id')}).")
                continue

            stem = os.path.splitext(os.path.basename(src))[0]
            stem = sanitize_dirname(clean_video_name(stem)) or f"video_{v['id']}"

            for tt_id in self.tiktok_ids:
                tt = db.get_tiktok_channel(tt_id)
                handle = (tt or {}).get("handle") or f"tt_{tt_id}"
                out_dir = os.path.join(
                    get_project_base(), "клипы",
                    sanitize_dirname(handle), stem
                )
                try:
                    os.makedirs(out_dir, exist_ok=True)
                except OSError as e:
                    self.progress.emit(f"Не удалось создать {out_dir}: {e}")
                    continue

                # пропускаем уже нарезанное
                existing = db.list_clips(tt_id)
                if any(c.get("source_video_id") == v["id"] for c in existing):
                    self.progress.emit(
                        f"Уже нарезано: @{handle} ← «{v.get('title') or stem}»"
                    )
                    continue

                self.progress.emit(
                    f"Нарезаю «{v.get('title') or stem}» для @{handle} "
                    f"({self.clip_duration} сек)…"
                )
                try:
                    result = video_service.cut_video(
                        input_path=src,
                        output_dir=out_dir,
                        clip_duration=self.clip_duration,
                        prefix="clip",
                        reencode=False,
                    )
                except Exception as e:
                    self.progress.emit(f"Ошибка ffmpeg: {e}")
                    continue

                for clip_path in result.clips:
                    try:
                        db.add_clip(
                            tiktok_id=tt_id,
                            file_path=clip_path,
                            source_video_id=v["id"],
                            duration=float(self.clip_duration),
                            status="ready",
                        )
                        total_clips += 1
                    except Exception as e:
                        self.progress.emit(f"БД: не удалось добавить клип: {e}")
                self.progress.emit(
                    f"Готово: {result.succeeded} клипов → @{handle}"
                )
            total_videos += 1

        self.finished_.emit(total_clips, total_videos)


# ──────────────────────────────────────────────────────────────────────
# AUTOMATION PAGE
# ──────────────────────────────────────────────────────────────────────

class AutomationPage(BasePage):
    """Автоматизация: выбор YouTube-канала, фильтры, блоки, авто-триггер."""

    PAGE_TITLE = "Автоматизация"

    request_open_tiktok = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_channel: Optional[int] = None
        self._pipeline_running = False
        self._clip_worker: Optional[ClipPrepWorker] = None
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(15 * 60 * 1000)  # каждые 15 минут
        self._auto_timer.timeout.connect(self._run_auto_check)

        self._build_ui()
        self.refresh()
        self._maybe_start_timer()

    # ── UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(QLabel("YouTube-канал:"))
        self.cmb_channel = QComboBox()
        self.cmb_channel.setMinimumWidth(260)
        self.cmb_channel.currentIndexChanged.connect(self._on_channel_changed)
        top.addWidget(self.cmb_channel)
        top.addStretch()
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #5a5957;")
        top.addWidget(self.lbl_status)
        root.addLayout(top)

        tt_row = QHBoxLayout()
        self.lbl_tiktoks = QLabel("")
        self.lbl_tiktoks.setStyleSheet("color: #5a5957;")
        self.lbl_tiktoks.setWordWrap(True)
        tt_row.addWidget(self.lbl_tiktoks, 1)
        self.btn_link_tt = QPushButton("Привязать TikTok…")
        self.btn_link_tt.clicked.connect(self._open_link_tiktok_dialog)
        tt_row.addWidget(self.btn_link_tt)
        root.addLayout(tt_row)

        root.addWidget(self._build_filters_group())
        root.addWidget(self._build_download_block())
        root.addWidget(self._build_processing_block())
        root.addWidget(self._build_clip_block())

        root.addWidget(self._build_journal_group(), 1)

        bar = QHBoxLayout()
        bar.addStretch()
        btn_save = QPushButton("Сохранить настройки")
        btn_save.clicked.connect(self._save_settings)
        bar.addWidget(btn_save)
        btn_run = QPushButton("Запустить пайплайн сейчас")
        btn_run.clicked.connect(self._run_pipeline_now)
        bar.addWidget(btn_run)
        root.addLayout(bar)

    def _build_filters_group(self) -> QGroupBox:
        g = QGroupBox("Фильтры видео")
        lay = QHBoxLayout(g)
        self.sp_min_dur = QSpinBox()
        self.sp_min_dur.setRange(0, 100000)
        self.sp_min_dur.setSuffix(" сек")
        self.sp_max_dur = QSpinBox()
        self.sp_max_dur.setRange(0, 100000)
        self.sp_max_dur.setSuffix(" сек")
        self.sp_max_age = QSpinBox()
        self.sp_max_age.setRange(0, 3650)
        self.sp_max_age.setSuffix(" дн")
        self.chk_popular = QCheckBox("Брать популярные если мало подходящих")

        lay.addWidget(QLabel("Мин. длительность:"))
        lay.addWidget(self.sp_min_dur)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Макс. длительность:"))
        lay.addWidget(self.sp_max_dur)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Макс. возраст:"))
        lay.addWidget(self.sp_max_age)
        lay.addSpacing(8)
        lay.addWidget(self.chk_popular)
        lay.addStretch()
        return g

    def _build_download_block(self) -> QGroupBox:
        g = QGroupBox()
        g.setCheckable(True)
        g.setChecked(True)
        g.setTitle("Скачивание новых видео")
        lay = QVBoxLayout(g)
        row = QHBoxLayout()
        lbl = QLabel("Добавляет новые видео выбранного YouTube-канала в очередь загрузки.")
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        btn = QPushButton("Запустить скачивание")
        btn.clicked.connect(self._run_download)
        row.addWidget(btn)
        lay.addLayout(row)
        self.g_download = g
        return g

    def _build_processing_block(self) -> QGroupBox:
        g = QGroupBox()
        g.setCheckable(True)
        g.setChecked(False)
        g.setTitle("Монтаж")
        lay = QVBoxLayout(g)

        row = QHBoxLayout()
        self.ed_banner = QLineEdit()
        btn_b = QPushButton("…")
        btn_b.clicked.connect(lambda: self._pick_dir(self.ed_banner))
        row.addWidget(QLabel("Баннеры:"))
        row.addWidget(self.ed_banner, 1)
        row.addWidget(btn_b)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.ed_retention = QLineEdit()
        btn_r = QPushButton("…")
        btn_r.clicked.connect(lambda: self._pick_dir(self.ed_retention))
        row.addWidget(QLabel("Удержание:"))
        row.addWidget(self.ed_retention, 1)
        row.addWidget(btn_r)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.ed_background = QLineEdit()
        btn_bg = QPushButton("…")
        btn_bg.clicked.connect(lambda: self._pick_dir(self.ed_background))
        row.addWidget(QLabel("Фон:"))
        row.addWidget(self.ed_background, 1)
        row.addWidget(btn_bg)
        lay.addLayout(row)

        btn_run = QPushButton("Запустить монтаж")
        btn_run.clicked.connect(self._run_processing)
        lay.addWidget(btn_run)
        self.g_processing = g
        return g

    def _build_clip_block(self) -> QGroupBox:
        g = QGroupBox()
        g.setCheckable(True)
        g.setChecked(True)
        g.setTitle("Подготовка клипов")
        lay = QVBoxLayout(g)
        row = QHBoxLayout()
        row.addWidget(QLabel("Длительность клипа:"))
        self.sp_clip_dur = QSpinBox()
        self.sp_clip_dur.setRange(5, 600)
        self.sp_clip_dur.setSuffix(" сек")
        row.addWidget(self.sp_clip_dur)
        row.addStretch()
        btn = QPushButton("Нарезать сейчас")
        btn.clicked.connect(self._run_clip_prep)
        row.addWidget(btn)
        lay.addLayout(row)
        self.g_clips = g
        return g

    def _build_journal_group(self) -> QGroupBox:
        g = QGroupBox("Журнал автоматизации")
        lay = QVBoxLayout(g)
        self.journal = QPlainTextEdit()
        self.journal.setReadOnly(True)
        self.journal.setMaximumBlockCount(1000)
        lay.addWidget(self.journal)
        return g

    # ── Data ───────────────────────────────────────────────────────
    def refresh(self):
        prev = self._current_channel
        self.cmb_channel.blockSignals(True)
        self.cmb_channel.clear()
        for ch in db.get_all_channels():
            label = ch.get("title") or ch.get("url") or f"channel #{ch['id']}"
            self.cmb_channel.addItem(label, ch["id"])
        self.cmb_channel.blockSignals(False)
        if prev:
            idx = self.cmb_channel.findData(prev)
            if idx >= 0:
                self.cmb_channel.setCurrentIndex(idx)
        self._on_channel_changed()

    def _on_channel_changed(self):
        cid = self.cmb_channel.currentData()
        self._current_channel = int(cid) if cid else None
        if not self._current_channel:
            self.lbl_status.setText("Нет выбранного канала.")
            self.lbl_tiktoks.setText("")
            self.btn_link_tt.setEnabled(False)
            return
        self.btn_link_tt.setEnabled(True)
        s = db.get_automation_settings(self._current_channel)
        self.sp_min_dur.setValue(int(s.get("min_duration_sec") or 300))
        self.sp_max_dur.setValue(int(s.get("max_duration_sec") or 1800))
        self.sp_max_age.setValue(int(s.get("max_age_days") or 7))
        self.chk_popular.setChecked(bool(s.get("fallback_popular")))
        self.g_download.setChecked(bool(s.get("download_enabled")))
        self.g_processing.setChecked(bool(s.get("processing_enabled")))
        self.g_clips.setChecked(bool(s.get("publish_enabled")))
        self.ed_banner.setText(s.get("banner_dir") or "")
        self.ed_retention.setText(s.get("retention_dir") or "")
        self.ed_background.setText(s.get("background_dir") or "")
        self.sp_clip_dur.setValue(int(s.get("clip_duration_sec") or 30))

        tt_list = db.list_tiktok_for_youtube(self._current_channel)
        ch = db.get_channel(self._current_channel)
        ch_title = (ch or {}).get("title") or f"#{self._current_channel}"
        if tt_list:
            handles = ", ".join(f"@{t.get('handle')}" for t in tt_list if t.get("handle"))
            ready_total = sum(db.count_ready_clips(t["id"]) for t in tt_list)
            self.lbl_tiktoks.setText(
                f"Привязанные TikTok: {handles or '—'}"
            )
            self.lbl_status.setText(f"Готовых клипов по привязкам: {ready_total}")
        else:
            self.lbl_tiktoks.setText(
                f"У канала «{ch_title}» не задан TikTok-хэндл. "
                f"Откройте «YouTube каналы» → укажите @handle в карточке канала, "
                f"либо нажмите «Привязать TikTok…» справа чтобы выбрать существующий "
                f"или создать новый."
            )
            self.lbl_status.setText("TikTok не привязан")

    def _save_settings(self):
        if not self._current_channel:
            QMessageBox.information(
                self, "Нет канала",
                "Сначала добавьте YouTube-канал на вкладке «YouTube каналы»."
            )
            return
        db.set_automation_settings(
            self._current_channel,
            download_enabled=int(self.g_download.isChecked()),
            processing_enabled=int(self.g_processing.isChecked()),
            publish_enabled=int(self.g_clips.isChecked()),
            min_duration_sec=self.sp_min_dur.value(),
            max_duration_sec=self.sp_max_dur.value(),
            max_age_days=self.sp_max_age.value(),
            fallback_popular=int(self.chk_popular.isChecked()),
            banner_dir=self.ed_banner.text().strip() or None,
            retention_dir=self.ed_retention.text().strip() or None,
            background_dir=self.ed_background.text().strip() or None,
            clip_duration_sec=self.sp_clip_dur.value(),
        )
        QMessageBox.information(self, "Сохранено", "Настройки автоматизации сохранены.")
        self._maybe_start_timer()

    # ── Actions ────────────────────────────────────────────────────
    def _pick_dir(self, target: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Выберите папку", target.text() or "")
        if d:
            target.setText(d)

    def _open_link_tiktok_dialog(self):
        if not self._current_channel:
            return
        dlg = LinkTikTokDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            handle = dlg.selected_handle()
            if handle:
                tt_id = db.ensure_tiktok_link(self._current_channel, handle)
                # также проставим handle в channels для отображения в карточке
                db.update_channel(self._current_channel, tiktok_handle=handle)
                self._log(f"Привязан TikTok @{handle} → {self._current_channel}")
                self._on_channel_changed()

    def _current_filter(self) -> dict:
        return {
            "min_duration_sec": self.sp_min_dur.value(),
            "max_duration_sec": self.sp_max_dur.value(),
            "max_age_days": self.sp_max_age.value(),
            "fallback_popular": int(self.chk_popular.isChecked()),
        }

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self.journal.appendPlainText(f"[{ts}] {msg}")
        except Exception:
            pass
        log.info("auto: %s", msg)

    def _run_download(self):
        if not self._current_channel:
            QMessageBox.information(self, "Нет канала",
                                    "Сначала выберите YouTube-канал.")
            return
        c = db.get_channel(self._current_channel)
        if not c:
            return
        f = self._current_filter()
        queued = 0
        try:
            from download_queue import queue_manager
        except Exception as e:
            log.exception("download_queue import failed: %s", e)
            QMessageBox.warning(self, "Ошибка", f"Не удалось получить очередь загрузок: {e}")
            return

        try:
            from pages.channels_page import load_download_dir
        except Exception:
            load_download_dir = None

        videos = db.get_videos_by_channel(c["id"], status="new")
        matched = [v for v in videos if _match_video_filters(v, f)]
        if not matched and f.get("fallback_popular"):
            matched = sorted(videos, key=lambda v: v.get("view_count") or 0, reverse=True)[:5]
        out_dir = (load_download_dir(c.get("title") or "unknown", c["id"])
                   if load_download_dir else os.path.abspath("downloads"))
        for v in matched:
            try:
                queue_manager.add(
                    v["id"], v.get("title") or v.get("yt_id"),
                    v.get("yt_id"),
                    output_dir=out_dir,
                    quality="1080p",
                )
                queued += 1
            except Exception as e:
                log.warning("queue add failed for %s: %s", v.get("yt_id"), e)

        self._log(f"Скачивание: в очередь добавлено {queued} видео ({c.get('title')})")
        QMessageBox.information(
            self, "Скачивание запущено",
            f"В очередь добавлено {queued} видео."
        )

    def _run_processing(self):
        QMessageBox.information(
            self, "Монтаж",
            "Монтаж выполняется через существующий video_service.py.\n"
            "Настройки сохранены; полная автоматизация монтажа будет подключена в "
            "отдельной итерации — пока используйте страницу «Обработка» для ручной "
            "композиции или запустите нарезку клипов."
        )

    def _resolve_target_tiktoks(self, ask_if_many: bool = True) -> list[int]:
        """Возвращает id TikTok-каналов, куда раскладывать клипы.
        При нескольких привязках и ask_if_many=True — показывает диалог выбора.
        При авто-триггере ask_if_many=False (раскладываем во все)."""
        if not self._current_channel:
            return []
        tt_list = db.list_tiktok_for_youtube(self._current_channel)
        if not tt_list:
            return []
        if len(tt_list) == 1:
            return [int(tt_list[0]["id"])]
        if not ask_if_many:
            return [int(t["id"]) for t in tt_list]
        dlg = SelectTikTokDialog(tt_list, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selected_ids()
        return []

    def _run_clip_prep(self):
        """Физическая нарезка обработанных видео на клипы через ffmpeg.
        Работает в QThread."""
        if not self._current_channel:
            return
        if self._clip_worker and self._clip_worker.isRunning():
            QMessageBox.information(
                self, "Идёт нарезка",
                "Нарезка клипов уже выполняется. Дождитесь завершения."
            )
            return
        tt_list = db.list_tiktok_for_youtube(self._current_channel)
        if not tt_list:
            QMessageBox.warning(
                self, "Нет привязанного TikTok",
                "У выбранного YouTube-канала нет привязанного TikTok-канала. "
                "Нажмите «Привязать TikTok…» или укажите @handle в карточке канала."
            )
            return
        tt_ids = self._resolve_target_tiktoks(ask_if_many=True)
        if not tt_ids:
            return

        clip_dur = int(self.sp_clip_dur.value())
        self._log(
            f"Нарезка клипов: канал={self._current_channel}, "
            f"TikTok={tt_ids}, длит.={clip_dur} сек"
        )
        self._clip_worker = ClipPrepWorker(
            self._current_channel, tt_ids, clip_dur, parent=self
        )
        self._clip_worker.progress.connect(self._log)
        self._clip_worker.failed.connect(
            lambda msg: (
                self._log(f"Нарезка провалилась: {msg}"),
                QMessageBox.warning(self, "Ошибка нарезки", msg),
            )
        )
        self._clip_worker.finished_.connect(self._on_clip_prep_done)
        self._clip_worker.start()

    def _on_clip_prep_done(self, total_clips: int, total_videos: int):
        self._log(f"Нарезка завершена: {total_clips} клипов из {total_videos} видео")
        self._on_channel_changed()

    def _run_pipeline_now(self):
        if self.g_download.isChecked():
            self._run_download()
        if self.g_clips.isChecked():
            self._run_clip_prep()

    # ── Авто-триггер ──────────────────────────────────────────────
    def _maybe_start_timer(self):
        any_on = False
        try:
            for ch in db.get_all_channels():
                s = db.get_automation_settings(ch["id"])
                if s.get("download_enabled") or s.get("publish_enabled"):
                    any_on = True
                    break
        except Exception:
            any_on = False
        if any_on and not self._auto_timer.isActive():
            self._auto_timer.start()
            self._log("Авто-таймер запущен (каждые 15 минут).")
        elif not any_on and self._auto_timer.isActive():
            self._auto_timer.stop()
            self._log("Авто-таймер остановлен (нет включённых каналов).")

    def _run_auto_check(self):
        """Раз в 15 минут: обходит все YouTube-каналы с включённой
        автоматизацией. Для каждого проверяет запас клипов у привязанных
        TikTok-каналов и запускает блоки пайплайна (скачивание, монтаж,
        нарезка) — только те, которые включены в settings."""
        if self._pipeline_running:
            self._log("Авто-проверка: пайплайн уже выполняется — пропускаю.")
            return
        self._pipeline_running = True
        try:
            for ch in db.get_all_channels():
                s = db.get_automation_settings(ch["id"])
                if not (s.get("download_enabled") or s.get("publish_enabled")
                        or s.get("processing_enabled")):
                    continue
                tt_list = db.list_tiktok_for_youtube(ch["id"])
                if not tt_list:
                    continue
                shortages = []
                for tt in tt_list:
                    ready = db.count_ready_clips(tt["id"])
                    buf = int(tt.get("clip_min_buffer") or 10)
                    if ready < buf:
                        shortages.append((tt, ready, buf))
                if not shortages:
                    continue

                for tt, ready, buf in shortages:
                    self._log(
                        f"Авто: @{tt.get('handle')} "
                        f"({ready}/{buf}) ниже буфера — триггер пайплайна "
                        f"для «{ch.get('title') or ch['id']}»"
                    )

                prev_channel = self._current_channel
                self._current_channel = ch["id"]
                try:
                    if s.get("download_enabled"):
                        try:
                            self._run_download()
                        except Exception as e:
                            self._log(f"Авто: ошибка скачивания: {e}")

                    if s.get("processing_enabled"):
                        # Автоматический монтаж пока не реализован —
                        # логируем, чтобы пользователь видел пропуск.
                        self._log(
                            "Авто: шаг монтажа пропущен (реализуется в "
                            "отдельной итерации, используйте страницу «Обработка»)."
                        )

                    if s.get("publish_enabled"):
                        # Нарезка во все привязанные TikTok без диалога.
                        tt_ids = [int(t["id"]) for t in tt_list]
                        clip_dur = int(s.get("clip_duration_sec") or 30)
                        if self._clip_worker and self._clip_worker.isRunning():
                            self._log(
                                "Авто: нарезка уже в процессе — пропускаю канал."
                            )
                        else:
                            self._log(
                                f"Авто: запуск нарезки {ch.get('title') or ch['id']}"
                            )
                            self._clip_worker = ClipPrepWorker(
                                ch["id"], tt_ids, clip_dur, parent=self
                            )
                            self._clip_worker.progress.connect(self._log)
                            self._clip_worker.finished_.connect(
                                self._on_clip_prep_done
                            )
                            self._clip_worker.start()
                finally:
                    self._current_channel = prev_channel
        except Exception as e:
            log.exception("auto check failed")
            self._log(f"Авто-проверка упала: {e}")
        finally:
            self._pipeline_running = False
