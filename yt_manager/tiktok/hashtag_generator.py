# yt_manager/tiktok/hashtag_generator.py — генератор хэштегов
#
# Простая эвристика: берёт длинные слова (>3 символов) из заголовка видео,
# нормализует как теги и дополняет базовыми тегами канала.
# Без внешних API — работает оффлайн.

from __future__ import annotations

import re
from typing import Iterable, List


# Стоп-слова (русский + английский) — не превращаем в хэштеги
_STOPWORDS = {
    # ru
    "это", "как", "так", "что", "для", "при", "или", "ещё", "уже",
    "меня", "него", "них", "все", "всё", "нет", "там", "тут",
    "один", "один", "день", "раз", "тоже", "чего", "потом",
    "очень", "самый", "сама", "самые", "была", "были", "есть",
    "будет", "мной", "тебе", "твой", "моё", "своё", "когда",
    # en
    "the", "and", "for", "with", "from", "this", "that", "what",
    "your", "you", "are", "was", "were", "have", "has", "but",
    "not", "all", "any", "one", "two", "our", "out", "his", "her",
    "will", "just", "now", "how", "why", "who",
}

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _to_tag(word: str) -> str:
    word = word.strip().lstrip("#")
    if not word:
        return ""
    return "#" + word


def generate_hashtags(title: str,
                      channel_tags: Iterable[str] = (),
                      limit: int = 5) -> List[str]:
    """
    Генерирует список хэштегов по заголовку и тегам канала.

    Логика:
      1. Токенизируем название, отфильтровываем стоп-слова и короткие (<=3).
      2. Добавляем в начало до 3 тегов канала (если есть) — как приоритет.
      3. Обрезаем результат до limit.
      4. Дубликаты убираются без учёта регистра.
    """
    if limit <= 0:
        return []

    result: List[str] = []
    seen: set[str] = set()

    # 1. Базовые теги канала сначала
    for raw in channel_tags or []:
        tag = _to_tag(str(raw).strip())
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(tag)
        if len(result) >= min(3, limit):
            break

    if len(result) >= limit:
        return result[:limit]

    # 2. Слова из заголовка
    for word in _tokenize(title or ""):
        if len(word) <= 3:
            continue
        if word in _STOPWORDS:
            continue
        tag = _to_tag(word)
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(tag)
        if len(result) >= limit:
            break

    return result[:limit]
