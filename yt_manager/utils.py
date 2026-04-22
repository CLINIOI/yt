# utils.py — Общие утилиты проекта
#
# Функции для работы с именами файлов, путями, хэштегами и нормализацией данных.

from __future__ import annotations

import os
import re
from typing import Iterable, List


# ──────────────────────────────────────────────────────────────────────
# Имена файлов и папок
# ──────────────────────────────────────────────────────────────────────

# [abc_123] | [XxXxXx-123] | [YT-abcDEF1]
_BRACKET_CODE_RE = re.compile(r"\s*\[[A-Za-z0-9_\-]+\]\s*")
_INVALID_FS_CHARS = re.compile(r'[\/:*?"<>|]')


# ──────────────────────────────────────────────────────────────────────
# Имена папок-констант файловой структуры проекта
# ──────────────────────────────────────────────────────────────────────
#
# ВАЖНО: раунд 7 — переименовали папки для единообразия с UI «Папки»:
#   каналы/   → загрузки/     (сырые скачанные видео)
#   клипы/    → нарезки/      (готовые для публикации куски)
# Миграция выполняется в utils.migrate_dirs_v1 при старте — идемпотентно
# по флагу app_settings.dirs_renamed_v1.

DIR_DOWNLOADS   = "загрузки"     # ранее: каналы
DIR_PROCESSED   = "обработанное"
DIR_CLIPS       = "нарезки"      # ранее: клипы
DIR_BANNERS     = "баннер"
DIR_RETENTION   = "удержание"
DIR_BACKGROUNDS = "фон"

# Алиас для обратной совместимости с существующим кодом. В старых коммитах
# использовалась константа DIR_CHANNELS — новые модули должны использовать
# DIR_DOWNLOADS, но импорты старого имени продолжат работать.
DIR_CHANNELS = DIR_DOWNLOADS

# Старые имена папок — используются только миграцией.
_LEGACY_DIR_DOWNLOADS = "каналы"
_LEGACY_DIR_CLIPS     = "клипы"

#: Полный список папок, которые ensure_dirs создаёт при старте.
PROJECT_DIRS = (
    DIR_DOWNLOADS, DIR_PROCESSED, DIR_CLIPS,
    DIR_BANNERS, DIR_RETENTION, DIR_BACKGROUNDS,
)


def strip_bracket_codes(name: str) -> str:
    """
    Убирает коды в квадратных скобках из имени файла/видео.

    Примеры:
        "My Video [abc123XY].mp4"  -> "My Video.mp4"
        "Title [XX-01] [YY-02]"     -> "Title"
        "Обычное имя"                -> "Обычное имя"

    ВАЖНО: обрабатывает только короткие коды из букв/цифр/-/_,
    не трогает обычный текст в скобках: "[Важно]", "[Часть 1]".
    """
    if not name:
        return ""
    base, ext = os.path.splitext(name)
    base = _BRACKET_CODE_RE.sub(" ", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base + ext


def sanitize_dirname(name: str) -> str:
    """Делает строку безопасной как имя папки."""
    if not name:
        return "unknown"
    cleaned = _INVALID_FS_CHARS.sub("_", name).strip()
    # Убираем точки и пробелы в конце — проблема на Windows
    cleaned = cleaned.rstrip(" .")
    return cleaned or "unknown"


def sanitize_filename(name: str, max_len: int = 180) -> str:
    """Безопасное имя файла: удаляет запрещённые символы, укорачивает."""
    if not name:
        return "file"
    base, ext = os.path.splitext(name)
    base = _INVALID_FS_CHARS.sub("_", base).strip().rstrip(" .")
    if len(base) > max_len:
        base = base[:max_len].rstrip()
    return (base or "file") + ext


def clean_video_name(raw: str) -> str:
    """
    Полная очистка имени видео: убираем коды [...] и нормализуем пробелы.
    Применяется перед сохранением файлов и в UI.
    """
    return strip_bracket_codes(raw or "").strip()


# ──────────────────────────────────────────────────────────────────────
# Хэштеги
# ──────────────────────────────────────────────────────────────────────

def normalize_hashtags(raw) -> List[str]:
    """
    Нормализует хэштеги из строки или списка.

    Примеры:
        "cats funny"         -> ["#cats", "#funny"]
        "#cats, #cats"        -> ["#cats"]
        ["cats", "#funny"]    -> ["#cats", "#funny"]
        None                  -> []
    """
    if not raw:
        return []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
    elif isinstance(raw, (list, tuple)):
        parts = []
        for p in raw:
            if p:
                parts.extend(str(p).replace(",", " ").split())
    else:
        return []

    seen: set[str] = set()
    result: List[str] = []
    for p in parts:
        tag = p.lstrip("#").strip()
        if not tag:
            continue
        tag = "#" + tag
        low = tag.lower()
        if low in seen:
            continue
        seen.add(low)
        result.append(tag)
    return result


def format_hashtags(tags: Iterable[str]) -> str:
    """Превращает список хэштегов в строку через пробел."""
    if not tags:
        return ""
    return " ".join(normalize_hashtags(list(tags)))


# ──────────────────────────────────────────────────────────────────────
# Пути проекта
# ──────────────────────────────────────────────────────────────────────

def get_project_base() -> str:
    """Корень проекта (папка yt_manager/)."""
    return os.path.dirname(os.path.abspath(__file__))


def resolve_path(path: str, base: str | None = None) -> str:
    """
    Превращает относительный путь в абсолютный относительно базовой папки.
    Абсолютные пути возвращает без изменений.
    """
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base or get_project_base(), path))


def project_path(*parts: str) -> str:
    """Склеивает части пути от корня проекта и возвращает абсолютный путь."""
    cleaned = [sanitize_dirname(str(p)) if p else "" for p in parts if p]
    return os.path.join(get_project_base(), *cleaned) if cleaned else get_project_base()


def project_dir(dir_const: str, *parts: str) -> str:
    """Путь к одной из папок проекта (DIR_DOWNLOADS/DIR_PROCESSED/DIR_CLIPS/…).

    Первый аргумент — имя папки-константы (например, DIR_CLIPS). Последующие
    сегменты очищаются через sanitize_dirname и склеиваются.
    """
    sub = [sanitize_dirname(str(p)) for p in parts if p]
    return os.path.join(get_project_base(), dir_const, *sub) if dir_const else get_project_base()


# Handle-заглушка для каналов без привязки к TikTok. Выбрано так, чтобы
# в UI «Папки» такие каналы собирались под одним понятным узлом рядом
# с настоящими TikTok-хэндлами, а миграция старой папки downloads/ имела
# единую целевую подпапку.
TIKTOK_UNLINKED_HANDLE = "_без_tiktok"


def resolve_download_dir(channel_title: str,
                         channel_id: int | None = None) -> str:
    """Единая точка резолвинга папки для скачивания видео канала.

    Структура: ``<проект>/загрузки/<tiktok_handle>/<yt_channel>/``. Если
    у канала нет привязок к TikTok, вместо хэндла используется заглушка
    ``_без_tiktok`` — так вручную скачанные видео всегда попадают под
    предсказуемый путь, видимый в UI «Папки».
    """
    yt_name = sanitize_dirname(
        clean_video_name(channel_title or "unknown") or "unknown")

    tt_dir = TIKTOK_UNLINKED_HANDLE
    if channel_id:
        try:
            from db import db as _db
            linked = _db.list_tiktok_for_youtube(int(channel_id))
            if linked:
                handle = (linked[0].get("handle") or "").strip()
                if handle:
                    tt_dir = sanitize_dirname(handle)
        except Exception:
            pass

    return os.path.join(
        get_project_base(), DIR_DOWNLOADS, tt_dir, yt_name)


def resolve_processed_dir(channel_title: str,
                          channel_id: int | None = None) -> str:
    """Зеркальный резолвер для обработанных видео. Используется, когда
    результат обработки кладётся рядом с иерархией «загрузки/»."""
    yt_name = sanitize_dirname(
        clean_video_name(channel_title or "unknown") or "unknown")

    tt_dir = TIKTOK_UNLINKED_HANDLE
    if channel_id:
        try:
            from db import db as _db
            linked = _db.list_tiktok_for_youtube(int(channel_id))
            if linked:
                handle = (linked[0].get("handle") or "").strip()
                if handle:
                    tt_dir = sanitize_dirname(handle)
        except Exception:
            pass

    return os.path.join(
        get_project_base(), DIR_PROCESSED, tt_dir, yt_name)


def ensure_dir(path: str) -> str:
    """Гарантирует существование папки, возвращает её путь."""
    if path:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
    return path


# ──────────────────────────────────────────────────────────────────────
# Миграция имён файлов: убираем [XXXX] из уже скачанных
# ──────────────────────────────────────────────────────────────────────

_MIGRATION_FLAG = "filenames_migrated_v1"


def _iter_files(root: str):
    """Генератор всех файлов в дереве root (без поднятия исключений)."""
    if not root or not os.path.isdir(root):
        return
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            yield dirpath, fname


def migrate_existing_filenames(base_path: str, log=None) -> dict:
    """
    Одноразовая миграция: сканирует `downloads/`, `каналы/`, `обработанное/`
    относительно `base_path`, и у всех файлов с кодами в квадратных скобках
    убирает их через `strip_bracket_codes`. Попутно обновляет videos.file_path
    в БД, если совпадает старый путь.

    Повторный прогон защищён флагом `filenames_migrated_v1` в app_settings.
    Возвращает статистику: {'renamed': N, 'db_updated': M, 'skipped': K, 'errors': E}.

    Импорт БД — ленивый, чтобы утилиты оставались без обязательной
    зависимости от db.py.
    """
    stats = {"renamed": 0, "db_updated": 0, "skipped": 0, "errors": 0}

    try:
        from db import db as _db
    except Exception:
        _db = None

    # Проверяем флаг, если БД доступна
    if _db is not None:
        try:
            if _db.get_setting(_MIGRATION_FLAG):
                if log:
                    log.info("migrate_existing_filenames: уже выполнялась — пропуск")
                return stats
        except Exception:
            pass

    roots = [
        os.path.join(base_path, "downloads"),
        os.path.join(base_path, _LEGACY_DIR_DOWNLOADS),  # каналы
        os.path.join(base_path, DIR_DOWNLOADS),          # загрузки
        os.path.join(base_path, DIR_PROCESSED),
    ]

    path_map: dict[str, str] = {}
    for root in roots:
        for dirpath, fname in _iter_files(root):
            cleaned = strip_bracket_codes(fname)
            cleaned = sanitize_filename(cleaned)
            if not cleaned or cleaned == fname:
                stats["skipped"] += 1
                continue
            old = os.path.join(dirpath, fname)
            new = os.path.join(dirpath, cleaned)
            if os.path.exists(new):
                # Не затираем существующий файл — оставляем как есть.
                stats["skipped"] += 1
                continue
            try:
                os.rename(old, new)
                path_map[old] = new
                stats["renamed"] += 1
            except OSError as e:
                if log:
                    log.warning("rename fail %s → %s: %s", old, new, e)
                stats["errors"] += 1

    # БД: обновляем videos.file_path для переименованных
    if _db is not None and path_map:
        try:
            conn = _db.conn
            for old, new in path_map.items():
                try:
                    cur = conn.execute(
                        "UPDATE videos SET file_path = ? WHERE file_path = ?",
                        (new, old),
                    )
                    if cur.rowcount:
                        stats["db_updated"] += cur.rowcount
                except Exception as e:
                    if log:
                        log.warning("db update fail %s: %s", old, e)
                    stats["errors"] += 1
            try:
                conn.commit()
            except Exception:
                pass
        except Exception as e:
            if log:
                log.warning("db migration pass failed: %s", e)
            stats["errors"] += 1

    # Выставляем флаг ТОЛЬКО если прошли без критических ошибок обхода.
    # Мелкие ошибки отдельных файлов — не блокируют флаг.
    if _db is not None:
        try:
            _db.set_setting(_MIGRATION_FLAG, "1")
        except Exception:
            pass
    return stats


# ──────────────────────────────────────────────────────────────────────
# Миграция v1: каналы/ → загрузки/, клипы/ → нарезки/
# ──────────────────────────────────────────────────────────────────────

_DIRS_MIGRATION_FLAG = "dirs_renamed_v1"


def _merge_tree(src: str, dst: str, log=None) -> tuple[int, int]:
    """Рекурсивно перемещает содержимое src в dst. Если файл в dst уже
    есть — не затираем (оставляем старый в src). Возвращает (moved, skipped).
    """
    moved, skipped = 0, 0
    if not os.path.isdir(src):
        return 0, 0
    try:
        os.makedirs(dst, exist_ok=True)
    except OSError:
        return 0, 0
    for name in list(os.listdir(src)):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        try:
            if os.path.isdir(s):
                sub_m, sub_s = _merge_tree(s, d, log=log)
                moved += sub_m
                skipped += sub_s
                # Попытка удалить src-подпапку если пуста
                try:
                    if not os.listdir(s):
                        os.rmdir(s)
                except OSError:
                    pass
            else:
                if os.path.exists(d):
                    skipped += 1
                    continue
                import shutil
                shutil.move(s, d)
                moved += 1
        except Exception as e:
            if log:
                log.warning("merge %s → %s: %s", s, d, e)
            skipped += 1
    return moved, skipped


def migrate_dirs_v1(base_path: str, log=None) -> dict:
    """Одноразовая миграция структуры папок:
      каналы/  → загрузки/
      клипы/   → нарезки/

    Для каждой пары:
      • если назначения ещё нет и источник есть — просто переименовываем;
      • если и источник, и назначение существуют — мержим дерево
        (не затирая совпадающие файлы в назначении);
      • после мержа обновляем videos.file_path и clips.file_path в БД
        (префиксная замена).

    Идемпотентна через флаг app_settings.dirs_renamed_v1.
    """
    stats = {"renamed": [], "merged": 0, "db_videos": 0, "db_clips": 0,
             "errors": 0}
    try:
        from db import db as _db
    except Exception:
        _db = None

    if _db is not None:
        try:
            if _db.get_setting(_DIRS_MIGRATION_FLAG):
                if log:
                    log.info("migrate_dirs_v1: уже выполнена — пропуск")
                return stats
        except Exception:
            pass

    pairs = [
        (_LEGACY_DIR_DOWNLOADS, DIR_DOWNLOADS),  # каналы → загрузки
        (_LEGACY_DIR_CLIPS,     DIR_CLIPS),      # клипы  → нарезки
    ]

    import shutil as _sh
    path_prefix_map: list[tuple[str, str]] = []
    for old_name, new_name in pairs:
        old_abs = os.path.join(base_path, old_name)
        new_abs = os.path.join(base_path, new_name)
        if not os.path.isdir(old_abs):
            continue
        try:
            if not os.path.exists(new_abs):
                _sh.move(old_abs, new_abs)
                stats["renamed"].append((old_name, new_name))
                if log:
                    log.info("migrate_dirs_v1: переименовано %s → %s",
                             old_name, new_name)
            else:
                moved, _skipped = _merge_tree(old_abs, new_abs, log=log)
                stats["merged"] += moved
                if log:
                    log.info("migrate_dirs_v1: слито %d файлов %s → %s",
                             moved, old_name, new_name)
                try:
                    _sh.rmtree(old_abs, ignore_errors=True)
                except Exception:
                    pass
        except Exception as e:
            if log:
                log.warning("migrate_dirs_v1: %s → %s: %s",
                            old_name, new_name, e)
            stats["errors"] += 1
            continue
        path_prefix_map.append((old_abs, new_abs))
        # Нормализованные с разделителем в конце — чтобы не поймать
        # случайное совпадение "каналы" внутри другого пути
        path_prefix_map.append((old_abs + os.sep, new_abs + os.sep))

    # Обновляем пути в БД
    if _db is not None and path_prefix_map:
        try:
            cur = _db.conn.cursor()
            for table, col, key in (("videos", "file_path", "db_videos"),
                                    ("clips",  "file_path", "db_clips")):
                for old_p, new_p in path_prefix_map:
                    try:
                        cur.execute(
                            f"UPDATE {table} SET {col} = REPLACE({col}, ?, ?) "
                            f"WHERE {col} LIKE ?",
                            (old_p, new_p, old_p + "%"),
                        )
                        stats[key] += cur.rowcount
                    except Exception as e:
                        if log:
                            log.warning("db update %s: %s", table, e)
                        stats["errors"] += 1
            _db.conn.commit()
        except Exception as e:
            if log:
                log.warning("migrate_dirs_v1 db update failed: %s", e)
            stats["errors"] += 1

    if _db is not None:
        try:
            _db.set_setting(_DIRS_MIGRATION_FLAG, "1")
        except Exception:
            pass
    return stats


# ──────────────────────────────────────────────────────────────────────
# Миграция старых ручных загрузок: downloads/ → загрузки/_без_tiktok/
#                                    processed/ → обработанное/_без_tiktok/
# ──────────────────────────────────────────────────────────────────────

_LEGACY_DOWNLOADS_FLAG = "legacy_downloads_migrated_v1"


def migrate_legacy_downloads_v1(base_path: str, log=None) -> dict:
    """Одноразовая миграция старых папок ручного скачивания.

    Если в корне проекта есть унаследованные ``downloads/`` или
    ``processed/`` (лежат параллельно новой структуре), их содержимое
    переносится под ``<цель>/_без_tiktok/`` — туда же, куда теперь
    резолвится путь для каналов без TikTok-привязки. Так вручную
    скачанные видео продолжают быть видны в UI «Папки».

    Идемпотентна через флаг ``legacy_downloads_migrated_v1`` в
    ``app_settings``. При мерже конфликтующий файл в назначении не
    перезаписывается — исходный остаётся на месте и попадёт в лог.
    """
    stats = {"moved": 0, "skipped": 0, "db_videos": 0, "errors": 0,
             "sources": []}
    try:
        from db import db as _db
    except Exception:
        _db = None

    if _db is not None:
        try:
            if _db.get_setting(_LEGACY_DOWNLOADS_FLAG):
                if log:
                    log.info("migrate_legacy_downloads_v1: уже выполнена")
                return stats
        except Exception:
            pass

    pairs = [
        ("downloads", DIR_DOWNLOADS),
        ("processed", DIR_PROCESSED),
    ]

    path_prefix_map: list[tuple[str, str]] = []
    for old_name, new_name in pairs:
        old_abs = os.path.join(base_path, old_name)
        if not os.path.isdir(old_abs):
            continue
        # Если папка пустая — просто удалим её, чтобы не мозолила глаза.
        try:
            if not os.listdir(old_abs):
                try:
                    os.rmdir(old_abs)
                except OSError:
                    pass
                continue
        except OSError:
            pass

        dst = os.path.join(base_path, new_name, TIKTOK_UNLINKED_HANDLE)
        try:
            os.makedirs(dst, exist_ok=True)
        except OSError as e:
            if log:
                log.warning("cannot create %s: %s", dst, e)
            stats["errors"] += 1
            continue

        moved, skipped = _merge_tree(old_abs, dst, log=log)
        stats["moved"] += moved
        stats["skipped"] += skipped
        stats["sources"].append(old_name)
        if log:
            log.info("migrate_legacy_downloads_v1: %s → %s: moved=%d, "
                     "skipped=%d", old_name, os.path.join(
                         new_name, TIKTOK_UNLINKED_HANDLE), moved, skipped)

        # Удаляем пустую исходную папку
        try:
            if os.path.isdir(old_abs) and not os.listdir(old_abs):
                os.rmdir(old_abs)
        except OSError:
            pass

        # Для обновления БД собираем префиксы (со и без завершающего sep).
        path_prefix_map.append((old_abs, dst))
        path_prefix_map.append((old_abs + os.sep, dst + os.sep))

    # Обновляем пути в таблице videos (clips в старой downloads/ не лежали).
    if _db is not None and path_prefix_map:
        try:
            cur = _db.conn.cursor()
            for old_p, new_p in path_prefix_map:
                try:
                    cur.execute(
                        "UPDATE videos SET file_path = REPLACE(file_path, ?, ?) "
                        "WHERE file_path LIKE ?",
                        (old_p, new_p, old_p + "%"),
                    )
                    stats["db_videos"] += cur.rowcount
                except Exception as e:
                    if log:
                        log.warning("db update videos: %s", e)
                    stats["errors"] += 1
            _db.conn.commit()
        except Exception as e:
            if log:
                log.warning("migrate_legacy_downloads_v1 db commit: %s", e)
            stats["errors"] += 1

    if _db is not None:
        try:
            _db.set_setting(_LEGACY_DOWNLOADS_FLAG, "1")
        except Exception:
            pass
    return stats
