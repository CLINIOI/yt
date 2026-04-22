# yt_manager/tiktok/script_builder.py — сборка строки публикации
#
# Формат строки, понятный user-script'у TikTok Studio:
#
#     path | tags | date(yyyy-MM-dd HH:mm) | caption
#
# Разделитель — " | " (с пробелами). Вертикальная черта внутри любого поля
# заменяется на безопасный символ (слеш / пробел), чтобы не сломать парсер.

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def normalize_tags(raw) -> str:
    """Превращает строку или список тегов в "#a #b #c" без дубликатов."""
    if not raw:
        return ""
    if isinstance(raw, (list, tuple)):
        items: List[str] = []
        for p in raw:
            if not p:
                continue
            items.extend(str(p).replace(",", " ").split())
    else:
        items = [p for p in str(raw).replace(",", " ").split() if p]

    fixed: List[str] = []
    seen = set()
    for p in items:
        if not p.startswith("#"):
            p = "#" + p.lstrip("#")
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        fixed.append(p)
    return " ".join(fixed)


def _clean_for_pipe(value: str, replacement: str = "/") -> str:
    return (value or "").replace("|", replacement).strip()


def format_date(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def build_string(path: str,
                 tags: Iterable[str] | str = "",
                 date: Optional[datetime] = None,
                 caption: str = "") -> str:
    """
    Собирает строку для копирования в TikTok Studio.
    Пустые хвостовые поля обрезаются.
    """
    path_s = _clean_for_pipe(path or "")
    tags_s = normalize_tags(tags).replace("|", " ")
    date_s = format_date(date)
    caption_s = _clean_for_pipe((caption or "").replace("\n", " "))

    parts = [path_s, tags_s, date_s, caption_s]
    while parts and parts[-1] == "":
        parts.pop()
    return " | ".join(parts)


def parse_string(raw: str) -> dict:
    """Обратная операция: строка -> {path, tags, date, caption}. Используется
    для истории и импорта скриптов. date может быть None."""
    parts = [p.strip() for p in (raw or "").split("|")]
    while len(parts) < 4:
        parts.append("")
    path, tags, date_str, caption = parts[0], parts[1], parts[2], " | ".join(parts[3:]).strip() if len(parts) > 4 else parts[3]
    dt = None
    if date_str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            dt = None
    return {"path": path, "tags": tags, "date": dt, "caption": caption}
