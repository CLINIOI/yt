# pages/automation_page.py — Страница «Автоматизация»
#
# Управление автоматическим пайплайном для конкретного YouTube-канала.
#
# Логика автоматизации (после фидбека пользователя, раунд 4):
#   • Автоматизация запускается ТОЛЬКО по нажатию кнопки «▶ Запустить
#     автоматизацию» — никаких автостартов при сохранении настроек.
#   • Кнопка переключает поле automation_settings.auto_active (0/1).
#   • Перед запуском — валидация: должен быть привязан TikTok-канал и
#     заполнены настройки. Если включён монтаж — папки баннер/удержание/
#     фон должны быть валидны (пользователь может согласиться запустить
#     без монтажа).
#   • Авто-таймер тикает раз в 5 минут и обходит только каналы с
#     auto_active=1. Если таких нет — таймер останавливается.
#   • За один тик — максимум одно видео на канал. AutoPipelineWorker
#     реализует конечный автомат:
#       check_threshold → download_one → montage_one → split_one
#     Каждый шаг — на одно видео. Если порога достигли — выходим.

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
    QVBoxLayout, QLineEdit, QFrame,
)

from pages.base_page import BasePage
from db import db
from utils import (
    sanitize_dirname, clean_video_name, get_project_base,
    DIR_CLIPS, DIR_PROCESSED, DIR_DOWNLOADS,
)
from video_service import validate_processing_dirs, pick_first_video


log = logging.getLogger(__name__)

# Интервал авто-таймера: 5 минут (раньше было 15, но при модели
# «по одному видео за тик» 15 минут — слишком редко).
AUTO_TIMER_INTERVAL_MS = 5 * 60 * 1000


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


def _pick_next_video(channel_id: int, filters: dict) -> Optional[dict]:
    """Выбирает ОДНО следующее видео канала, ещё не скачанное и
    подходящее под фильтры. Возвращает dict видео или None.

    fallback_popular: если ничего не подходит — берём самое просматриваемое
    из новых.
    """
    new_videos = db.get_videos_by_channel(channel_id, status="new")
    if not new_videos:
        return None
    matched = [v for v in new_videos if _match_video_filters(v, filters)]
    if matched:
        # Самое свежее по upload_date
        matched.sort(key=lambda v: v.get("upload_date") or "", reverse=True)
        return matched[0]
    if filters.get("fallback_popular"):
        new_videos.sort(key=lambda v: v.get("view_count") or 0, reverse=True)
        return new_videos[0] if new_videos else None
    return None


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
            # Фолбэк: если «обработанное/» пусто (например, при невалидных
            # папках авто-монтажа) — режем из «каналы/» чтобы пайплайн
            # давал хоть какой-то результат.
            fallback = [
                v for v in db.get_videos_by_channel(self.channel_id, status="downloaded")
                if v.get("file_path") and os.path.isfile(v["file_path"])
            ]
            if fallback:
                self.progress.emit(
                    f"Нет обработанных видео — fallback: нарезаю {len(fallback)} "
                    f"скачанных напрямую."
                )
                videos = fallback
            else:
                self.progress.emit("Нет подходящих видео для нарезки.")
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
                    get_project_base(), DIR_CLIPS,
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
# WORKER: авто-монтаж (композиция) скачанных видео канала
# ──────────────────────────────────────────────────────────────────────

class AutoMontageWorker(QThread):
    """Прогоняет скачанные видео канала через video_service.stack_videos.
    При max_videos=1 обрабатывает только одно следующее видео — нужно
    для последовательного авто-пайплайна (одно за тик)."""

    progress  = pyqtSignal(str)
    finished_ = pyqtSignal(int, int)   # succeeded, failed
    failed    = pyqtSignal(str)

    def __init__(self,
                 channel_id: int,
                 banner_dir: Optional[str],
                 retention_dir: Optional[str],
                 background_dir: Optional[str],
                 max_videos: int = 0,
                 parent=None):
        super().__init__(parent)
        self.channel_id    = int(channel_id)
        self.banner_dir    = banner_dir
        self.retention_dir = retention_dir
        self.background_dir = background_dir
        self.max_videos    = int(max_videos or 0)

    def _resolve_out_dir(self) -> str:
        """Папка вывода: обработанное/<handle>/ (первый привязанный TikTok)
        или обработанное/_<channel_id>/ как фолбэк."""
        base = os.path.join(get_project_base(), DIR_PROCESSED)
        try:
            tt_list = db.list_tiktok_for_youtube(self.channel_id)
        except Exception:
            tt_list = []
        if tt_list:
            handle = tt_list[0].get("handle") or f"ch_{self.channel_id}"
            return os.path.join(base, sanitize_dirname(handle))
        return os.path.join(base, f"_ch_{self.channel_id}")

    def run(self):
        try:
            from video_service import video_service
        except Exception as e:
            self.failed.emit(f"video_service недоступен: {e}")
            return

        # Кандидаты: скачанные, но не смонтированные
        videos = [
            v for v in db.get_videos_by_channel(self.channel_id)
            if (v.get("status") in ("downloaded", "new"))
            and v.get("file_path")
            and os.path.isfile(v.get("file_path"))
        ]
        if not videos:
            self.progress.emit("Нет скачанных видео для монтажа.")
            self.finished_.emit(0, 0)
            return

        if self.max_videos > 0:
            videos = videos[: self.max_videos]

        out_dir = self._resolve_out_dir()
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            self.failed.emit(f"Не удалось создать {out_dir}: {e}")
            return

        top_path = pick_first_video(self.banner_dir)
        bot_path = pick_first_video(self.retention_dir)
        bg_path  = pick_first_video(self.background_dir)

        succeeded = 0
        failed = 0
        for v in videos:
            src = v["file_path"]
            stem = os.path.splitext(os.path.basename(src))[0]
            stem = sanitize_dirname(clean_video_name(stem)) or f"video_{v['id']}"
            out_path = os.path.join(out_dir, f"{stem}.mp4")
            # если уже смонтировано — пропускаем
            if os.path.isfile(out_path):
                self.progress.emit(f"Уже смонтировано: {stem} — пропуск.")
                try:
                    db.update_video_status(v["id"], "processed", file_path=out_path)
                except Exception:
                    pass
                succeeded += 1
                continue

            self.progress.emit(
                f"Монтаж: «{v.get('title') or stem}» → {out_path}"
            )
            try:
                video_service.stack_videos(
                    center_path=src,
                    output_path=out_path,
                    top_path=top_path,
                    bottom_path=bot_path,
                    bg_path=bg_path,
                )
                try:
                    db.update_video_status(v["id"], "processed", file_path=out_path)
                except Exception as e:
                    self.progress.emit(f"БД: не удалось обновить статус: {e}")
                succeeded += 1
            except Exception as e:
                log.exception("auto-montage failed for video %s", v.get("id"))
                self.progress.emit(f"Ошибка монтажа «{stem}»: {e}")
                failed += 1

        self.finished_.emit(succeeded, failed)


# ──────────────────────────────────────────────────────────────────────
# WORKER: AutoPipelineWorker — конечный автомат «одно видео за тик»
# ───────────────────────────────────────��──────────────────────────────

class AutoPipelineWorker(QThread):
    """Последовательный пайплайн для одного YouTube-канала:

      1. check_threshold — у привязанных TikTok считаем готовые клипы.
         Если у всех ready >= clip_min_buffer → выходим (всё в норме).
      2. download_one — выбираем ОДНО следующее видео канала и качаем.
      3. montage_one — если включён монтаж и папки валидны, собираем
         композицию для скачанного.
      4. split_one — нарезаем результат на клипы и регистрируем в БД.
      5. check_threshold снова. Если порог достигнут — выход; иначе
         просто завершаемся (следующее видео — на следующем тике).

    За один запуск worker обрабатывает максимум одно видео.
    """

    step_started   = pyqtSignal(str)
    step_finished  = pyqtSignal(str)
    log            = pyqtSignal(str)
    pipeline_done  = pyqtSignal(str)   # короткое резюме

    def __init__(self, channel_id: int, parent=None):
        super().__init__(parent)
        self.channel_id = int(channel_id)

    # ── Хелперы ────────────────────────────────────────────────────

    def _ch_label(self, ch: dict) -> str:
        return ch.get("title") or ch.get("url") or f"#{self.channel_id}"

    def _enough_clips(self, tt_list: list) -> bool:
        """Возвращает True, только если у ВСЕХ привязанных TikTok
        число ready-клипов не ниже буфера. Пишет детальный лог по каждому."""
        all_enough = True
        for tt in tt_list:
            ready = db.count_ready_clips(int(tt["id"]))
            buf = int(tt.get("clip_min_buffer") or 10)
            handle = tt.get("handle") or tt.get("username") or f"#{tt['id']}"
            if ready < buf:
                self.log.emit(
                    f"TikTok @{handle}: {ready} ready / {buf} нужно → качаем."
                )
                all_enough = False
            else:
                self.log.emit(
                    f"TikTok @{handle}: {ready} ready / {buf} нужно → достаточно."
                )
        return all_enough

    # ── Шаги ───────────────────────────────────────────────────────

    def _do_download(self, settings: dict, ch: dict) -> Optional[dict]:
        """Скачивает одно видео. Возвращает запись video из БД."""
        filters = {
            "min_duration_sec": settings.get("min_duration_sec") or 0,
            "max_duration_sec": settings.get("max_duration_sec") or 10 ** 9,
            "max_age_days":     settings.get("max_age_days") or 0,
            "fallback_popular": settings.get("fallback_popular") or 0,
        }
        v = _pick_next_video(self.channel_id, filters)
        if not v:
            self.log.emit("Нет подходящих видео для скачивания — пропуск канала.")
            return None
        self.step_started.emit(f"Скачивание: «{v.get('title') or v.get('yt_id')}»")
        try:
            from pages.channels_page import load_download_dir
        except Exception:
            load_download_dir = None
        out_dir = (load_download_dir(ch.get("title") or "unknown", ch["id"])
                   if load_download_dir else
                   os.path.join(get_project_base(), DIR_DOWNLOADS))
        try:
            from youtube_service import yt_service
            db.update_video_status(v["id"], "downloading")
            path = yt_service.download_single_video(
                yt_id_or_url=v.get("yt_id"),
                output_dir=out_dir,
                quality="1080p",
            )
        except Exception as e:
            log.exception("auto download failed for %s", v.get("yt_id"))
            db.update_video_status(v["id"], "error", error_msg=str(e))
            self.log.emit(f"Ошибка скачивания: {e}")
            return None
        if not path:
            err_msg = getattr(yt_service, "last_error_message", "") or "download returned None"
            db.update_video_status(v["id"], "error", error_msg=err_msg)
            self.log.emit(f"Скачивание завершилось без результата. {err_msg}")
            return None
        db.update_video_status(v["id"], "downloaded", file_path=path)
        self.step_finished.emit(f"Скачано: {path}")
        return db.get_video(v["id"])

    def _do_montage(self, settings: dict, video: dict) -> Optional[str]:
        """Монтирует одно видео. Возвращает путь к смонтированному
        файлу либо None если монтаж пропущен/упал.

        Если папки невалидны — пропускаем монтаж и оставляем видео в
        статусе 'downloaded' (нарезка возьмёт исходник как fallback).
        """
        banner = settings.get("banner_dir") or None
        retention = settings.get("retention_dir") or None
        background = settings.get("background_dir") or None
        ok, reason = validate_processing_dirs(banner, retention, background)
        if not ok:
            self.log.emit(
                f"Монтаж пропущен: {reason}. Нарезаю исходник напрямую."
            )
            return None

        try:
            from video_service import video_service
        except Exception as e:
            self.log.emit(f"Монтаж недоступен: {e}")
            return None

        src = video.get("file_path")
        if not src or not os.path.isfile(src):
            self.log.emit("Файл скачанного видео не найден — пропуск монтажа.")
            return None

        base = os.path.join(get_project_base(), DIR_PROCESSED)
        try:
            tt_list = db.list_tiktok_for_youtube(self.channel_id)
        except Exception:
            tt_list = []
        sub = (sanitize_dirname(tt_list[0].get("handle") or "")
               if tt_list else f"_ch_{self.channel_id}")
        out_dir = os.path.join(base, sub or f"_ch_{self.channel_id}")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            self.log.emit(f"Не удалось создать {out_dir}: {e}")
            return None
        stem = os.path.splitext(os.path.basename(src))[0]
        stem = sanitize_dirname(clean_video_name(stem)) or f"video_{video['id']}"
        out_path = os.path.join(out_dir, f"{stem}.mp4")

        self.step_started.emit(f"Монтаж: «{video.get('title') or stem}»")
        try:
            video_service.stack_videos(
                center_path=src,
                output_path=out_path,
                top_path=pick_first_video(banner),
                bottom_path=pick_first_video(retention),
                bg_path=pick_first_video(background),
            )
            db.update_video_status(video["id"], "processed", file_path=out_path)
            self.step_finished.emit(f"Смонтировано: {out_path}")
            return out_path
        except Exception as e:
            log.exception("auto montage failed video=%s", video.get("id"))
            self.log.emit(f"Ошибка монтажа: {e}")
            return None

    def _do_split(self, settings: dict, video: dict) -> int:
        """Нарезает одно видео на клипы. Возвращает кол-во клипов."""
        try:
            from video_service import video_service
        except Exception as e:
            self.log.emit(f"Нарезка недоступна: {e}")
            return 0

        src = video.get("file_path")
        if not src or not os.path.isfile(src):
            self.log.emit("Нет файла для нарезки.")
            return 0

        tt_list = db.list_tiktok_for_youtube(self.channel_id)
        if not tt_list:
            self.log.emit("Нет привязанных TikTok-каналов — нарезка пропущена.")
            return 0

        clip_dur = int(settings.get("clip_duration_sec") or 30)
        stem = os.path.splitext(os.path.basename(src))[0]
        stem = sanitize_dirname(clean_video_name(stem)) or f"video_{video['id']}"

        total = 0
        for tt in tt_list:
            tt_id = int(tt["id"])
            handle = tt.get("handle") or f"tt_{tt_id}"
            out_dir = os.path.join(
                get_project_base(), DIR_CLIPS,
                sanitize_dirname(handle), stem
            )
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                self.log.emit(f"Не удалось создать {out_dir}: {e}")
                continue

            existing = db.list_clips(tt_id)
            if any(c.get("source_video_id") == video["id"] for c in existing):
                self.log.emit(f"Уже нарезано: @{handle} ← {stem}")
                continue

            self.step_started.emit(f"Нарезка: «{video.get('title') or stem}» → @{handle}")
            try:
                result = video_service.cut_video(
                    input_path=src,
                    output_dir=out_dir,
                    clip_duration=clip_dur,
                    prefix="clip",
                    reencode=False,
                )
            except Exception as e:
                self.log.emit(f"Ошибка нарезки: {e}")
                continue
            for clip_path in result.clips:
                try:
                    db.add_clip(
                        tiktok_id=tt_id,
                        file_path=clip_path,
                        source_video_id=video["id"],
                        duration=float(clip_dur),
                        status="ready",
                    )
                    total += 1
                except Exception as e:
                    self.log.emit(f"БД: не удалось добавить клип: {e}")
            self.step_finished.emit(f"@{handle}: добавлено клипов {result.succeeded}")
        return total

    # ── Главный run ────────────────────────────────────────────────

    def run(self):
        ch = db.get_channel(self.channel_id)
        if not ch:
            self.pipeline_done.emit("Канал не найден.")
            return
        label = self._ch_label(ch)

        tt_list = db.list_tiktok_for_youtube(self.channel_id)
        if not tt_list:
            self.pipeline_done.emit(
                f"«{label}»: нет привязанного TikTok — пропуск."
            )
            return

        # Шаг 1 — порог
        if self._enough_clips(tt_list):
            self.pipeline_done.emit(
                f"«{label}»: клипов достаточно — пайплайн не нужен."
            )
            return

        settings = db.get_automation_settings(self.channel_id)

        # Шаг 2 — одно скачивание
        if not settings.get("download_enabled"):
            self.pipeline_done.emit(
                f"«{label}»: скачивание выключено — нечего делать."
            )
            return
        video = self._do_download(settings, ch)
        if not video:
            self.pipeline_done.emit(f"«{label}»: новое видео не найдено.")
            return

        # Шаг 3 — один монтаж (если включён)
        if settings.get("processing_enabled"):
            self._do_montage(settings, video)
            video = db.get_video(video["id"]) or video  # обновляем file_path

        # Шаг 4 — одна нарезка
        if settings.get("publish_enabled"):
            added = self._do_split(settings, video)
        else:
            added = 0

        # Шаг 5 — повторная проверка порога (для лога)
        tt_list = db.list_tiktok_for_youtube(self.channel_id)
        if self._enough_clips(tt_list):
            self.pipeline_done.emit(
                f"«{label}»: добавлено клипов — порог достигнут."
            )
        else:
            self.pipeline_done.emit(
                f"«{label}»: добавлено клипов {added}; "
                f"следующее видео — на следующем тике."
            )


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
        self._clip_worker: Optional[ClipPrepWorker] = None
        self._montage_worker: Optional[AutoMontageWorker] = None
        # channel_id → AutoPipelineWorker (защита от двойного запуска)
        self._active_pipelines: dict[int, AutoPipelineWorker] = {}

        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(AUTO_TIMER_INTERVAL_MS)
        self._auto_timer.timeout.connect(self._run_auto_check)

        self._build_ui()
        self.refresh()
        self._sync_timer_state()

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

        # ── Большая панель управления автоматизацией ─────────────
        root.addWidget(self._build_master_panel())

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

    def _build_master_panel(self) -> QFrame:
        """Панель: индикатор + большая кнопка Запустить/Остановить."""
        frm = QFrame()
        frm.setObjectName("auto_master")
        lay = QHBoxLayout(frm)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)

        self.lbl_auto_state = QLabel("● Остановлено")
        self.lbl_auto_state.setObjectName("auto_state")
        self.lbl_auto_state.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #964219;"
        )
        lay.addWidget(self.lbl_auto_state)
        lay.addStretch()

        self.btn_auto_toggle = QPushButton("▶ Запустить автоматизацию")
        self.btn_auto_toggle.setObjectName("auto_toggle")
        self.btn_auto_toggle.setMinimumHeight(40)
        self.btn_auto_toggle.setMinimumWidth(260)
        self.btn_auto_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_toggle.clicked.connect(self._on_auto_toggle)
        self._style_run_button(active=False)
        lay.addWidget(self.btn_auto_toggle)
        return frm

    def _style_run_button(self, active: bool):
        """Окрашивает большую кнопку: зелёная — запуск, красная — стоп."""
        if active:
            self.btn_auto_toggle.setText("⏸ Остановить автоматизацию")
            self.btn_auto_toggle.setStyleSheet(
                "QPushButton#auto_toggle{"
                " background:#a83232;color:white;font-weight:700;"
                " font-size:13px;border-radius:8px;padding:8px 14px;}"
                "QPushButton#auto_toggle:hover{background:#bf3a3a;}"
            )
        else:
            self.btn_auto_toggle.setText("▶ Запустить автоматизацию")
            self.btn_auto_toggle.setStyleSheet(
                "QPushButton#auto_toggle{"
                " background:#2f7a3a;color:white;font-weight:700;"
                " font-size:13px;border-radius:8px;padding:8px 14px;}"
                "QPushButton#auto_toggle:hover{background:#388f47;}"
            )

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

        defaults = self._media_defaults()

        row = QHBoxLayout()
        self.ed_banner = QLineEdit()
        self.ed_banner.setPlaceholderText(
            f"по умолчанию: {defaults['banner_dir']}"
        )
        btn_b = QPushButton("…")
        btn_b.clicked.connect(lambda: self._pick_dir(self.ed_banner))
        row.addWidget(QLabel("Баннеры:"))
        row.addWidget(self.ed_banner, 1)
        row.addWidget(btn_b)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.ed_retention = QLineEdit()
        self.ed_retention.setPlaceholderText(
            f"по умолчанию: {defaults['retention_dir']}"
        )
        btn_r = QPushButton("…")
        btn_r.clicked.connect(lambda: self._pick_dir(self.ed_retention))
        row.addWidget(QLabel("Удержание:"))
        row.addWidget(self.ed_retention, 1)
        row.addWidget(btn_r)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.ed_background = QLineEdit()
        self.ed_background.setPlaceholderText(
            f"по умолчанию: {defaults['background_dir']}"
        )
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

    # ── Helpers ────────────────────────────────────────────────────
    def _media_defaults(self) -> dict:
        """Дефолтные пути для banner/retention/background — через db."""
        try:
            return db._default_media_dirs()  # type: ignore[attr-defined]
        except Exception:
            base = get_project_base()
            return {
                "banner_dir":     os.path.join(base, "баннер"),
                "retention_dir":  os.path.join(base, "удержание"),
                "background_dir": os.path.join(base, "фон"),
            }

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
            self.btn_auto_toggle.setEnabled(False)
            self._style_run_button(active=False)
            self.lbl_auto_state.setText("● Нет канала")
            return
        self.btn_link_tt.setEnabled(True)
        self.btn_auto_toggle.setEnabled(True)
        s = db.get_automation_settings(self._current_channel)
        self.sp_min_dur.setValue(int(s.get("min_duration_sec") or 300))
        self.sp_max_dur.setValue(int(s.get("max_duration_sec") or 1800))
        self.sp_max_age.setValue(int(s.get("max_age_days") or 7))
        self.chk_popular.setChecked(bool(s.get("fallback_popular")))
        self.g_download.setChecked(bool(s.get("download_enabled")))
        self.g_processing.setChecked(bool(s.get("processing_enabled")))
        self.g_clips.setChecked(bool(s.get("publish_enabled")))
        # Поля папок: показываем то, что в БД (может быть NULL — тогда
        # пользователь видит плейсхолдер).
        raw = self.conn_get_raw_dirs(self._current_channel)
        self.ed_banner.setText(raw.get("banner_dir") or "")
        self.ed_retention.setText(raw.get("retention_dir") or "")
        self.ed_background.setText(raw.get("background_dir") or "")
        self.sp_clip_dur.setValue(int(s.get("clip_duration_sec") or 30))

        self._update_master_panel(s)

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

    def conn_get_raw_dirs(self, channel_id: int) -> dict:
        """Возвращает значения banner/retention/background из БД БЕЗ
        подстановки дефолтов — чтобы UI отличал «пусто» от «дефолт»."""
        row = db.conn.execute(
            "SELECT banner_dir, retention_dir, background_dir "
            "FROM automation_settings WHERE channel_id = ?",
            (int(channel_id),)
        ).fetchone()
        return dict(row) if row else {}

    def _update_master_panel(self, settings: dict):
        active = bool(settings.get("auto_active"))
        self._style_run_button(active=active)
        if active:
            running = self._current_channel in self._active_pipelines and \
                      self._active_pipelines[self._current_channel].isRunning()
            if running:
                self.lbl_auto_state.setText("● Работает — пайплайн активен")
                self.lbl_auto_state.setStyleSheet(
                    "font-size: 14px; font-weight: 600; color: #4f98a3;"
                )
            else:
                self.lbl_auto_state.setText("● Работает — ждёт триггера")
                self.lbl_auto_state.setStyleSheet(
                    "font-size: 14px; font-weight: 600; color: #437a22;"
                )
        else:
            self.lbl_auto_state.setText("● Остановлено")
            self.lbl_auto_state.setStyleSheet(
                "font-size: 14px; font-weight: 600; color: #964219;"
            )

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
        QMessageBox.information(
            self, "Сохранено",
            "Настройки автоматизации сохранены.\n\n"
            "Чтобы запустить автоматизацию, нажмите «▶ Запустить автоматизацию»."
        )
        # ВАЖНО: НЕ запускаем таймер здесь. Только после явного нажатия
        # большой кнопки запуска.
        self._on_channel_changed()

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
            # Сообщения с префиксом [!] подсвечиваем красным
            if "[!]" in msg:
                from PyQt6.QtGui import QTextCharFormat, QColor
                cursor = self.journal.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                fmt = QTextCharFormat()
                fmt.setForeground(QColor("#d64545"))
                fmt.setFontWeight(700)
                if self.journal.toPlainText():
                    cursor.insertText("\n")
                cursor.insertText(f"[{ts}] {msg}", fmt)
                self.journal.setTextCursor(cursor)
            else:
                self.journal.appendPlainText(f"[{ts}] {msg}")
        except Exception:
            pass
        log.info("auto: %s", msg)

    # ── Большая кнопка: запуск/остановка автоматизации ────────────

    def _on_auto_toggle(self):
        if not self._current_channel:
            return
        s = db.get_automation_settings(self._current_channel)
        if s.get("auto_active"):
            # Остановка: безусловная.
            db.set_auto_active(self._current_channel, False)
            self._log(f"Автоматизация остановлена для канала #{self._current_channel}.")
            self._on_channel_changed()
            self._sync_timer_state()
            return

        # Запуск: валидация
        ok, reason = self._validate_for_start()
        if not ok:
            QMessageBox.warning(
                self, "Не могу запустить автоматизацию", reason
            )
            return

        # Если включён монтаж и папки невалидны — спрашиваем подтверждение
        if self.g_processing.isChecked():
            banner = self.ed_banner.text().strip() or s.get("banner_dir")
            retention = self.ed_retention.text().strip() or s.get("retention_dir")
            background = self.ed_background.text().strip() or s.get("background_dir")
            mok, mreason = validate_processing_dirs(banner, retention, background)
            if not mok:
                reply = QMessageBox.question(
                    self, "Папки монтажа не настроены",
                    f"{mreason}\n\nЗапустить автоматизацию БЕЗ монтажа? "
                    f"(нарезка пойдёт из исходников)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        # Сначала сохраним текущие настройки UI в БД, чтобы воркер
        # увидел актуальные значения.
        self._save_settings_silent()
        db.set_auto_active(self._current_channel, True)
        self._log(
            f"Автоматизация запущена для канала #{self._current_channel}. "
            f"Авто-таймер: 5 минут, по одному видео за тик."
        )
        self._on_channel_changed()
        self._sync_timer_state()
        # Сразу запускаем первый тик — чтобы пользователь не ждал
        # 5 минут перед первым видео.
        self._run_auto_check()

    def _save_settings_silent(self):
        """Сохраняет настройки без показа QMessageBox (для запуска)."""
        if not self._current_channel:
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

    def _validate_for_start(self) -> tuple[bool, str]:
        """Проверяет, можно ли запустить автоматизацию для канала."""
        if not self._current_channel:
            return False, "Канал не выбран."
        tt_list = db.list_tiktok_for_youtube(self._current_channel)
        if not tt_list:
            return False, ("К каналу не привязан ни один TikTok-канал. "
                           "Нажмите «Привязать TikTok…».")
        if not (self.g_download.isChecked() or self.g_processing.isChecked()
                or self.g_clips.isChecked()):
            return False, ("Не включён ни один блок (скачивание/монтаж/клипы). "
                           "Включите хотя бы один.")
        # Если монтаж включён, но папки невалидны — спросим в _on_auto_toggle.
        return True, ""

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
                   if load_download_dir else
                   os.path.join(get_project_base(), DIR_DOWNLOADS))
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
        """Ручной запуск монтажа на выбранном YouTube-канале.
        Перед стартом проверяет, что указанные папки существуют и содержат видео."""
        if not self._current_channel:
            QMessageBox.information(self, "Нет канала",
                                    "Сначала выберите YouTube-канал.")
            return
        if self._montage_worker and self._montage_worker.isRunning():
            QMessageBox.information(
                self, "Идёт монтаж",
                "Монтаж уже выполняется. Дождитесь завершения."
            )
            return

        banner = self.ed_banner.text().strip() or None
        retention = self.ed_retention.text().strip() or None
        background = self.ed_background.text().strip() or None

        ok, reason = validate_processing_dirs(banner, retention, background)
        if not ok:
            QMessageBox.warning(
                self, "Некорректные папки монтажа",
                f"Не удаётся запустить монтаж:\n{reason}\n\n"
                "Проверьте пути к баннерам / удержанию / фону в блоке «Монтаж»."
            )
            return

        self._log(f"Монтаж: канал={self._current_channel}")
        self._montage_worker = AutoMontageWorker(
            self._current_channel, banner, retention, background, parent=self
        )
        self._montage_worker.progress.connect(self._log)
        self._montage_worker.failed.connect(
            lambda msg: (
                self._log(f"Монтаж провалился: {msg}"),
                QMessageBox.warning(self, "Ошибка монтажа", msg),
            )
        )
        self._montage_worker.finished_.connect(self._on_montage_done)
        self._montage_worker.start()

    def _on_montage_done(self, succeeded: int, failed: int):
        self._log(f"Монтаж завершён: успех={succeeded}, ошибок={failed}")
        self._on_channel_changed()

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
    def _sync_timer_state(self):
        """Запускает/останавливает авто-таймер в зависимости от того,
        есть ли каналы с auto_active=1."""
        try:
            active_ids = db.list_active_automation_channels()
        except Exception:
            active_ids = []
        if active_ids and not self._auto_timer.isActive():
            self._auto_timer.start()
            self._log(
                f"Авто-таймер запущен (каждые "
                f"{AUTO_TIMER_INTERVAL_MS // 60000} мин). "
                f"Активных каналов: {len(active_ids)}."
            )
        elif not active_ids and self._auto_timer.isActive():
            self._auto_timer.stop()
            self._log("Авто-таймер остановлен (нет активных каналов).")

    def _run_auto_check(self):
        """Тик авто-таймера: для каждого канала с auto_active=1 запускаем
        AutoPipelineWorker (если он ещё не работает). Каждый воркер
        обработает максимум одно видео."""
        try:
            active_ids = db.list_active_automation_channels()
        except Exception as e:
            log.exception("auto check failed: %s", e)
            return
        if not active_ids:
            self._sync_timer_state()
            return

        for cid in active_ids:
            existing = self._active_pipelines.get(cid)
            if existing and existing.isRunning():
                self._log(f"Канал #{cid}: пайплайн уже выполняется — пропуск.")
                continue
            worker = AutoPipelineWorker(cid, parent=self)
            worker.log.connect(self._log)
            worker.step_started.connect(lambda m: self._log(f"→ {m}"))
            worker.step_finished.connect(lambda m: self._log(f"✓ {m}"))
            worker.pipeline_done.connect(self._on_pipeline_done)
            self._active_pipelines[cid] = worker
            worker.start()

        self._on_channel_changed()

    def _on_pipeline_done(self, summary: str):
        self._log(summary)
        # Чистим завершённые воркеры
        for cid in list(self._active_pipelines.keys()):
            w = self._active_pipelines[cid]
            if not w.isRunning():
                self._active_pipelines.pop(cid, None)
        self._on_channel_changed()
