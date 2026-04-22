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
        os.path.join(base_path, "каналы"),
        os.path.join(base_path, "обработанное"),
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
