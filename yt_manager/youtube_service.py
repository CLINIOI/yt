# youtube_service.py — Интеграция с YouTube через yt-dlp
#
# Содержит:
#   YouTubeService  — чистый Python-сервис (без Qt): получение инфо, скачивание
#   DownloadWorker  — QThread-обёртка для фонового скачивания с прогрессом

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# КЛАССИФИКАЦИЯ ОШИБОК yt-dlp
# ─────────────────────────────────────────────────────────────────────

COOKIES_HINT = (
    "Откройте Настройки → «YouTube — куки для скачивания» "
    "и выберите браузер или файл cookies.txt."
)


def classify_download_error(err_text: str) -> str:
    """Возвращает понятное русскоязычное сообщение по тексту ошибки yt-dlp.

    Используется для логов пайплайна и UI-баннеров. Префикс `[!]` помогает
    AutomationPage подсветить строку.
    """
    low = (err_text or "").lower()
    if ("sign in to confirm" in low) or ("not a bot" in low) \
            or ("confirm you" in low) or ("use --cookies" in low):
        return (f"[!] Требуются куки YouTube. {COOKIES_HINT}")
    if "429" in low or "too many requests" in low or "rate" in low and "limit" in low:
        return "[!] YouTube ограничил частоту запросов (429). Попробуйте позже."
    if "age" in low and ("restrict" in low or "confirm" in low or "gate" in low):
        return ("[!] Видео с возрастным ограничением — нужны куки "
                f"авторизованного аккаунта. {COOKIES_HINT}")
    if "private video" in low:
        return "[!] Видео приватное — доступ невозможен."
    if "video unavailable" in low or "removed" in low:
        return "[!] Видео недоступно (удалено или скрыто)."
    # Иначе — отдаём исходный текст
    return err_text or "Неизвестная ошибка yt-dlp"


# ─────────────────────────────────────────────────────────────────────
# ОПЦИИ КУКИ (глобальные, управляются настройками)
# ─────────────────────────────────────────────────────────────────────

_SUPPORTED_BROWSERS = (
    "chrome", "firefox", "edge", "opera", "brave",
    "vivaldi", "chromium", "safari",
)

# Файл cookies.txt рядом с проектом (используется в режиме "auto")
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTO_COOKIES_FILE = os.path.join(_PROJECT_ROOT, "cookies.txt")


def _auto_resolve_cookies() -> dict:
    """Старая автологика: cookies.txt рядом с проектом → первый доступный браузер."""
    if os.path.isfile(AUTO_COOKIES_FILE):
        return {"cookiefile": AUTO_COOKIES_FILE}
    try:
        import yt_dlp.cookies as _ck
        for _br in ("chrome", "firefox", "edge", "brave", "opera"):
            try:
                _ck.load_cookies_from_browser(_br)
                return {"cookiesfrombrowser": (_br,)}
            except Exception:
                continue
    except Exception:
        pass
    return {}


def _resolve_cookie_opts(db=None) -> dict:
    """Возвращает словарь опций для yt-dlp на основе настроек пользователя.

    Режимы (ключ app_settings `yt_cookies_mode`):
        "auto"    — текущая автологика (cookies.txt → браузер).
        "browser" — явный браузер из `yt_cookies_browser`.
        "file"    — cookies.txt по пути `yt_cookies_file`.

    Если db не передан — используем глобальный инстанс `db` из модуля db.
    При любой ошибке откатываемся на автологику (обратная совместимость).

    Логирует применяемый режим и итоговый словарь опций, чтобы в логе
    было видно, какие куки реально используются при каждом вызове.
    """
    try:
        if db is None:
            from db import db as _db
            db = _db
    except Exception:
        db = None

    mode = "auto"
    try:
        if db is not None:
            mode = (db.get_setting("yt_cookies_mode", "auto") or "auto").strip().lower()
    except Exception:
        mode = "auto"

    result: dict = {}
    if mode == "browser":
        try:
            browser = (db.get_setting("yt_cookies_browser", "chrome") or "chrome").strip().lower()
        except Exception:
            browser = "chrome"
        if browser not in _SUPPORTED_BROWSERS:
            browser = "chrome"
        result = {"cookiesfrombrowser": (browser,)}
    elif mode == "file":
        try:
            path = (db.get_setting("yt_cookies_file", "") or "").strip()
        except Exception:
            path = ""
        if path and Path(path).exists():
            result = {"cookiefile": path}
        else:
            log.warning("yt_cookies_file не существует (%s), откат на auto", path)
            result = _auto_resolve_cookies()
            mode = "auto(fallback)"
    else:
        result = _auto_resolve_cookies()

    log.info("cookies: mode=%s, result=%r", mode, result)
    return result


def describe_cookie_opts(db=None) -> str:
    """Короткое человекочитаемое описание применяемых куки — для UI.

    Примеры: "Из файла /home/user/cookies.txt",
    "Из браузера chrome", "Авто (cookies.txt рядом с проектом)",
    "Авто (ничего не найдено)".
    """
    opts = _resolve_cookie_opts(db)
    if "cookiefile" in opts:
        return f"Из файла {opts['cookiefile']}"
    if "cookiesfrombrowser" in opts:
        br = opts["cookiesfrombrowser"]
        name = br[0] if isinstance(br, (tuple, list)) and br else str(br)
        return f"Из браузера {name}"
    return "Авто (куки не применяются — yt-dlp работает без авторизации)"


# ─────────────────────────────────────────────────────────────────────
# EXTRACTOR ARGS — обход проверки бота через мобильные клиенты
# ─────────────────────────────────────────────────────────────────────

def _resolve_extractor_args(db=None) -> dict:
    """Возвращает extractor_args для yt-dlp, если включён режим
    «Мобильные клиенты» (ключ `yt_use_mobile_clients`, по умолчанию True).

    Использование клиентов ios/android часто обходит проверку
    «Sign in to confirm you're not a bot» даже без куки.
    """
    try:
        if db is None:
            from db import db as _db
            db = _db
    except Exception:
        db = None

    use_mobile = True
    try:
        if db is not None:
            raw = db.get_setting("yt_use_mobile_clients", True)
            if isinstance(raw, str):
                use_mobile = raw.strip().lower() not in ("0", "false", "no", "")
            else:
                use_mobile = bool(raw) if raw is not None else True
    except Exception:
        use_mobile = True

    if not use_mobile:
        return {}
    return {
        "youtube": {
            "player_client": ["ios", "android", "web"],
        }
    }


# ─────────────────────────────────────────────────────────────────────
# ДАТАКЛАССЫ — структуры данных
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ChannelInfo:
    """Метаинформация о YouTube-канале."""
    url:            str
    yt_channel_id:  str  = ""
    title:          str  = ""
    description:    str  = ""
    thumbnail_url:  str  = ""
    video_count:    int  = 0


@dataclass
class VideoInfo:
    """Метаинформация об отдельном видео."""
    yt_id:         str  = ""
    title:         str  = ""
    duration:      int  = 0    # секунды
    thumbnail_url: str  = ""
    upload_date:   str  = ""   # YYYYMMDD
    view_count:    int  = 0
    url:           str  = ""   # полная ссылка


@dataclass
class DownloadProgress:
    """Прогресс скачивания, передаётся через сигнал."""
    percent:        float = 0.0
    speed:          str   = ""   # "1.2 MiB/s"
    eta:            str   = ""   # "00:42"
    downloaded_mb:  float = 0.0
    total_mb:       float = 0.0
    status:         str   = "downloading"  # downloading | merging | finished | error


# ─────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────────────

def _best_thumbnail(thumbnails: list) -> str:
    """
    Выбирает URL превью подходящего размера из списка yt-dlp thumbnails.
    Предпочитает ширину в диапазоне 320–640px.
    """
    if not thumbnails:
        return ""
    # Сортируем по ширине, берём ближайшую к 480
    sized = [t for t in thumbnails if t.get("width")]
    if sized:
        sized.sort(key=lambda t: abs(t["width"] - 480))
        return sized[0].get("url", "")
    return thumbnails[-1].get("url", "")


def _format_speed(bytes_per_sec: Optional[float]) -> str:
    if not bytes_per_sec:
        return ""
    if bytes_per_sec > 1_048_576:
        return f"{bytes_per_sec / 1_048_576:.1f} MiB/s"
    if bytes_per_sec > 1024:
        return f"{bytes_per_sec / 1024:.1f} KiB/s"
    return f"{bytes_per_sec:.0f} B/s"


def _format_eta(seconds: Optional[float]) -> str:
    if not seconds:
        return ""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _bytes_to_mb(b: Optional[float]) -> float:
    return round((b or 0) / 1_048_576, 1)


# ─────────────────────────────────────────────────────────────────────
# YOUTUBE SERVICE
# ─────────────────────────────────────────────────────────────────────

class YouTubeService:
    """
    Чистый Python-сервис для работы с YouTube.
    Не зависит от Qt — можно использовать в тестах и CLI.

    Качество скачивания:
        "1080p" | "720p" | "480p" | "360p" | "best" | "audio"
    """

    QUALITY_FORMATS: dict[str, str] = {
        "best":  "bestvideo*+bestaudio*/best",
        "1080p": "bestvideo*[height<=1080]+bestaudio*/best[height<=1080]/best",
        "720p":  "bestvideo*[height<=720]+bestaudio*/best[height<=720]/best",
        "480p":  "bestvideo*[height<=480]+bestaudio*/best[height<=480]/best",
        "360p":  "bestvideo*[height<=360]+bestaudio*/best[height<=360]/best",
        "audio": "bestaudio*/best",
    }

    def __init__(self, db=None):
        # Последнее понятное сообщение об ошибке (для UI)
        self._last_error_message: str = ""
        # Инстанс БД — используется для чтения настроек куки.
        # Если не передан, в _resolve_cookie_opts произойдёт fallback
        # на глобальный `from db import db` (обратная совместимость).
        self.db = db

    def set_db(self, db) -> None:
        """Позволяет пробросить инстанс БД уже после создания сервиса."""
        self.db = db

    @property
    def last_error_message(self) -> str:
        return self._last_error_message

    # Обратная совместимость — сохраняем путь к файлу cookies.txt
    COOKIES_FILE: str = AUTO_COOKIES_FILE

    def _cookie_opts(self) -> dict:
        """Опции куки для yt-dlp — используют настройки пользователя."""
        return _resolve_cookie_opts(self.db)

    def _extractor_args(self) -> dict:
        """extractor_args (мобильные клиенты YouTube — обход проверки бота)."""
        args = _resolve_extractor_args(self.db)
        return {"extractor_args": args} if args else {}

    def _common_opts(self) -> dict:
        """Общие опции yt-dlp: куки + extractor_args. Используется во всех методах."""
        opts = dict(self._cookie_opts())
        opts.update(self._extractor_args())
        return opts



    # ── Получение инфо о канале ───────────────────────────────────────

    def get_channel_info(self, url: str) -> Optional[ChannelInfo]:
        """
        Получает метаданные канала без скачивания видео.
        Поддерживает каналы с табами (Videos / Shorts / Live).
        """
        opts = {
            "quiet":        True,
            "no_warnings":  True,
            "extract_flat": "in_playlist",
            "playlistend":  5,      # достаточно для получения мета
            **self._common_opts(),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return None

            # Каналы с табами: верхний уровень = список под-плейлистов (tabs)
            # Настоящее кол-во видео берём из первого таба "Videos"
            video_count = info.get("playlist_count") or 0
            entries = info.get("entries") or []
            # Если entries — это табы, а не видео
            if entries and entries[0] and not entries[0].get("duration"):
                for tab in entries:
                    if not tab:
                        continue
                    tab_title = (tab.get("title") or "").lower()
                    if "video" in tab_title or tab_title == "":
                        video_count = tab.get("playlist_count") or video_count
                        break

            return ChannelInfo(
                url=url,
                yt_channel_id=info.get("channel_id") or info.get("uploader_id", ""),
                title=(
                    info.get("channel")
                    or info.get("uploader")
                    or info.get("title", "")
                ),
                description=info.get("description", ""),
                thumbnail_url=_best_thumbnail(info.get("thumbnails") or []),
                video_count=video_count,
            )
        except yt_dlp.utils.DownloadError as e:
            human = classify_download_error(str(e))
            self._last_error_message = human
            log.error("get_channel_info DownloadError [%s]: %s | %s", url, e, human)
        except Exception as e:
            log.exception("get_channel_info unexpected error [%s]: %s", url, e)
        return None

    # ── Список видео канала ───────────────────────────────────────────

    def get_channel_videos(self, url: str, limit: int = 0) -> list[VideoInfo]:
        """
        Возвращает список видео канала.
        Корректно обрабатывает каналы с табами (Videos / Shorts / Live):
        yt-dlp может вернуть верхний уровень как список под-плейлистов,
        тогда нужно раскрыть нужный таб и взять видео из него.

        Args:
            url:   URL канала.
            limit: Максимальное кол-во видео (0 = все без ограничения).
        """
        opts = {
            "quiet":        True,
            "no_warnings":  True,
            "extract_flat": "in_playlist",
            **({"playlistend": limit} if limit > 0 else {}),
            **self._common_opts(),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return []

            entries = info.get("entries") or []

            # ── Обработка каналов с табами ──────────────────────────
            # Признак табов: entries — под-плейлисты без duration у элементов
            # Нужно раскрыть таб "Videos" (или первый доступный)
            if entries and self._is_tab_list(entries):
                entries = self._fetch_tab_videos(entries, limit)

            # ── Парсинг видео ───────────────────────────────────────
            result: list[VideoInfo] = []
            for entry in entries:
                if not entry or not entry.get("id"):
                    continue
                # Пропускаем Short-вертикальные (необязательно — убери if хочешь Shorts тоже)
                yt_id = entry.get("id", "")
                result.append(VideoInfo(
                    yt_id=yt_id,
                    title=entry.get("title") or "",
                    duration=int(entry.get("duration") or 0),
                    thumbnail_url=(
                        _best_thumbnail(entry.get("thumbnails") or [])
                        or f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg"
                    ),
                    upload_date=entry.get("upload_date") or "",
                    view_count=int(entry.get("view_count") or 0),
                    url=entry.get("url") or f"https://youtube.com/watch?v={yt_id}",
                ))
                if limit > 0 and len(result) >= limit:
                    break

            return result

        except yt_dlp.utils.DownloadError as e:
            human = classify_download_error(str(e))
            self._last_error_message = human
            log.error("get_channel_videos DownloadError [%s]: %s | %s", url, e, human)
        except Exception as e:
            log.exception("get_channel_videos unexpected error [%s]: %s", url, e)
        return []

    @staticmethod
    def _is_tab_list(entries: list) -> bool:
        """
        Проверяет, является ли список entries набором табов (под-плейлистов),
        а не реальными видео. Признаки таба: нет поля duration, есть url с /videos.
        """
        if not entries:
            return False
        first = entries[0]
        if not first:
            return False
        # Видео всегда имеют duration (может быть 0, но ключ есть)
        # Табы — это плейлисты: имеют _type == "playlist" или нет duration
        entry_type = first.get("_type", "")
        if entry_type == "playlist":
            return True
        # Дополнительная проверка: нет duration, но есть title типа "Videos"
        if "duration" not in first:
            tab_titles = {"videos", "shorts", "live", "streams", "releases", "podcasts"}
            title = (first.get("title") or "").lower().strip()
            if title in tab_titles or not first.get("id", "").startswith("-"):
                return True
        return False

    def _fetch_tab_videos(self, tab_entries: list, limit: int) -> list:
        """
        Раскрывает нужный таб канала и возвращает список видео.
        Приоритет: таб "Videos" → первый доступный таб.
        """
        # Выбираем нужный таб: предпочитаем "Videos", избегаем "Shorts"
        preferred = None
        fallback  = None
        for tab in tab_entries:
            if not tab:
                continue
            title = (tab.get("title") or "").lower().strip()
            tab_url = tab.get("url") or tab.get("webpage_url") or ""
            if not tab_url:
                continue
            if title in ("videos", ""):
                preferred = tab_url
                break
            if title not in ("shorts", "live", "streams", "podcasts", "releases") and not fallback:
                fallback = tab_url

        target_url = preferred or fallback
        if not target_url:
            return []

        log.info("_fetch_tab_videos: раскрываем таб %s", target_url)
        opts = {
            "quiet":        True,
            "no_warnings":  True,
            "extract_flat": "in_playlist",
            **({"playlistend": limit} if limit > 0 else {}),
            **self._common_opts(),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                tab_info = ydl.extract_info(target_url, download=False)
            if not tab_info:
                return []
            return tab_info.get("entries") or []
        except Exception as e:
            log.error("_fetch_tab_videos error [%s]: %s", target_url, e)
            return []

    # ── Инфо об одном видео ───────────────────────────────────────────

    def get_video_info(self, yt_id_or_url: str) -> Optional[VideoInfo]:
        """
        Получает полные метаданные одного видео.

        Args:
            yt_id_or_url: YouTube ID (dQw4w9WgXcQ) или полная ссылка.
        """
        url = (yt_id_or_url if yt_id_or_url.startswith("http")
               else f"https://youtube.com/watch?v={yt_id_or_url}")
        opts = {
            "quiet":       True,
            "no_warnings": True,
            **self._common_opts(),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                return None
            return VideoInfo(
                yt_id=info.get("id", ""),
                title=info.get("title", ""),
                duration=int(info.get("duration") or 0),
                thumbnail_url=_best_thumbnail(info.get("thumbnails") or []),
                upload_date=info.get("upload_date", ""),
                view_count=int(info.get("view_count") or 0),
                url=url,
            )
        except Exception as e:
            log.error("get_video_info error [%s]: %s", yt_id_or_url, e)
        return None

    # ── Скачивание видео ──────────────────────────────────────────────

    def download_video(
        self,
        yt_id_or_url: str,
        output_dir: str,
        quality: str = "1080p",
        filename_template: str = "%(title)s [%(id)s].%(ext)s",
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        cancel_flag: Optional[list] = None,
    ) -> Optional[str]:
        """
        Скачивает видео и возвращает путь к файлу.

        Args:
            yt_id_or_url:       YouTube ID или URL.
            output_dir:         Папка для сохранения.
            quality:            Ключ из QUALITY_FORMATS.
            filename_template:  Шаблон имени файла (формат yt-dlp).
            progress_callback:  Функция, принимающая DownloadProgress.
            cancel_flag:        Список-флаг [False]; установи [True] для отмены.

        Returns:
            Путь к скачанному файлу или None при ошибке/отмене.
        """
        os.makedirs(output_dir, exist_ok=True)
        url = (yt_id_or_url if yt_id_or_url.startswith("http")
               else f"https://youtube.com/watch?v={yt_id_or_url}")

        fmt = self.QUALITY_FORMATS.get(quality, self.QUALITY_FORMATS["1080p"])
        downloaded_path: list[str] = []  # список для записи из хука

        def _progress_hook(d: dict):
            # Проверяем флаг отмены
            if cancel_flag and cancel_flag[0]:
                raise yt_dlp.utils.DownloadCancelled("Cancelled by user")

            if not progress_callback:
                return

            status = d.get("status", "")

            if status == "downloading":
                total   = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                current = d.get("downloaded_bytes") or 0
                percent = (current / total * 100) if total else 0

                progress_callback(DownloadProgress(
                    percent=round(percent, 1),
                    speed=_format_speed(d.get("speed")),
                    eta=_format_eta(d.get("eta")),
                    downloaded_mb=_bytes_to_mb(current),
                    total_mb=_bytes_to_mb(total),
                    status="downloading",
                ))

            elif status == "finished":
                downloaded_path.append(d.get("filename", ""))
                progress_callback(DownloadProgress(
                    percent=100.0,
                    status="merging",
                ))

        def _postprocessor_hook(d: dict):
            if d.get("status") == "finished":
                # Финальный файл после склейки видео+аудио
                filepath = d.get("info_dict", {}).get("filepath") or d.get("filepath", "")
                if filepath:
                    downloaded_path.clear()
                    downloaded_path.append(filepath)

        opts: dict = {
            "format":             fmt,
            "format_sort":        ["res", "ext:mp4:m4a", "codec:avc:m4a"],
            "outtmpl":            os.path.join(output_dir, filename_template),
            "merge_output_format": "mp4",
            "quiet":              True,
            "no_warnings":        True,
            "noprogress":         True,
            "progress_hooks":     [_progress_hook],
            "postprocessor_hooks": [_postprocessor_hook],
            "writethumbnail":     False,
            "nooverwrites":       True,
            **self._common_opts(),
        }

        def _run_download(run_opts: dict) -> None:
            with yt_dlp.YoutubeDL(run_opts) as ydl:
                ydl.download([url])

        try:
            try:
                _run_download(opts)
            except yt_dlp.utils.DownloadError as e:
                # Fallback: если формат недоступен — пробуем 'best' без format_sort.
                if "format is not available" in str(e).lower():
                    log.warning(
                        "download_video: формат %r недоступен для %s, "
                        "fallback на 'best' без format_sort",
                        fmt, yt_id_or_url,
                    )
                    fb_opts = dict(opts)
                    fb_opts["format"] = "best"
                    fb_opts.pop("format_sort", None)
                    downloaded_path.clear()
                    _run_download(fb_opts)
                else:
                    raise

            result = downloaded_path[-1] if downloaded_path else None
            # Переименование: убираем коды [XXXX] из имени файла
            if result and os.path.isfile(result):
                try:
                    from utils import strip_bracket_codes, sanitize_filename
                    folder = os.path.dirname(result)
                    base = os.path.basename(result)
                    cleaned = sanitize_filename(strip_bracket_codes(base))
                    if cleaned and cleaned != base:
                        new_path = os.path.join(folder, cleaned)
                        if not os.path.exists(new_path):
                            os.rename(result, new_path)
                            result = new_path
                except Exception as _e:
                    log.warning("rename on strip_bracket_codes failed: %s", _e)
            if progress_callback and result:
                progress_callback(DownloadProgress(percent=100.0, status="finished"))
            return result

        except yt_dlp.utils.DownloadCancelled:
            log.info("Download cancelled: %s", yt_id_or_url)
            if progress_callback:
                progress_callback(DownloadProgress(status="error"))
            return None

        except yt_dlp.utils.DownloadError as e:
            human = classify_download_error(str(e))
            log.error("download_video DownloadError [%s]: %s | %s",
                      yt_id_or_url, e, human)
            self._last_error_message = human
            if progress_callback:
                progress_callback(DownloadProgress(status="error"))
            return None

        except Exception as e:
            log.exception("download_video unexpected [%s]: %s", yt_id_or_url, e)
            if progress_callback:
                progress_callback(DownloadProgress(status="error"))
            return None

    # ── Скачивание одного видео (синхронно, без QThread) ──────────────

    def download_single_video(
        self,
        yt_id_or_url: str,
        output_dir: str,
        quality: str = "1080p",
    ) -> Optional[str]:
        """Синхронное скачивание одного видео — обёртка над download_video.

        Используется AutoPipelineWorker для строго последовательного
        пайплайна (одно видео за один тик авто-таймера). Возвращает
        путь к файлу или None при ошибке.
        """
        return self.download_video(
            yt_id_or_url=yt_id_or_url,
            output_dir=output_dir,
            quality=quality,
        )

    # ── Утилиты ───────────────────────────────────────────────────────

    @staticmethod
    def normalize_channel_url(url: str) -> str:
        """
        Приводит разные форматы ссылок на канал к стандартному виду.
        Работает с @handle, /channel/UC..., /c/name, голым @handle.
        """
        url = url.strip()
        if not url.startswith("http"):
            # "@mkbhd" → "https://youtube.com/@mkbhd"
            url = f"https://youtube.com/{url}" if url.startswith("@") else                   f"https://youtube.com/@{url}"
        return url

    @staticmethod
    def video_url(yt_id: str) -> str:
        return f"https://youtube.com/watch?v={yt_id}"


# ─────────────────────────────────────────────────────────────────────
# DOWNLOAD WORKER — QThread для фонового скачивания
# ─────────────────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    """
    Запускает скачивание в фоновом потоке.
    Испускает сигналы для обновления UI (прогресс-бар, статус, иконки).

    Использование:
        worker = DownloadWorker(video_id=42, yt_id="dQw4w9WgXcQ",
                                output_dir="/downloads/channel1", quality="1080p")
        worker.progress_updated.connect(my_progress_bar.setValue)
        worker.download_finished.connect(on_finished)
        worker.download_error.connect(on_error)
        worker.start()
        # Для отмены:
        worker.cancel()
    """

    # Сигналы
    progress_updated  = pyqtSignal(float, str, str)  # percent, speed, eta
    status_changed    = pyqtSignal(str)               # "downloading" | "merging" | ...
    download_finished = pyqtSignal(int, str)          # video_id, file_path
    download_error    = pyqtSignal(int, str)          # video_id, error_message

    def __init__(
        self,
        video_id:   int,
        yt_id:      str,
        output_dir: str,
        quality:    str = "1080p",
        parent=None,
        db=None,
    ):
        super().__init__(parent)
        self.video_id   = video_id
        self.yt_id      = yt_id
        self.output_dir = output_dir
        self.quality    = quality
        self._cancel    = [False]   # передаётся в download_video как cancel_flag
        # Пробрасываем db в сервис → в _cookie_opts, чтобы пользовательские
        # настройки куки реально применялись при каждой загрузке.
        self._service   = YouTubeService(db=db)

    def run(self):
        """Выполняется в отдельном потоке при worker.start()."""
        self.status_changed.emit("downloading")

        def on_progress(p: DownloadProgress):
            if p.status == "downloading":
                self.progress_updated.emit(p.percent, p.speed, p.eta)
            elif p.status == "merging":
                self.status_changed.emit("merging")
                self.progress_updated.emit(100.0, "", "")

        result = self._service.download_video(
            yt_id_or_url=self.yt_id,
            output_dir=self.output_dir,
            quality=self.quality,
            progress_callback=on_progress,
            cancel_flag=self._cancel,
        )

        if result:
            self.status_changed.emit("finished")
            self.download_finished.emit(self.video_id, result)
        else:
            if not self._cancel[0]:
                msg = self._service.last_error_message or "Ошибка скачивания"
                self.download_error.emit(self.video_id, msg)

    def cancel(self):
        """Отменяет скачивание. Поток завершится при следующем хуке прогресса."""
        self._cancel[0] = True


# ─────────────────────────────────────────────────────────────────────
# Глобальный инстанс сервиса
# ─────────────────────────────────────────────────────────────────────
#
# `yt_service.db` будет None до инициализации БД. При обращении к
# настройкам куки сработает fallback на `from db import db`. Для явного
# проброса после импорта db — вызывайте `yt_service.set_db(db)`.

yt_service = YouTubeService()

try:
    from db import db as _global_db
    yt_service.set_db(_global_db)
except Exception:
    pass
