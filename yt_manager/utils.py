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
