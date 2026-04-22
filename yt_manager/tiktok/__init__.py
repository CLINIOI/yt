# yt_manager/tiktok — интеграция с TikTok Studio
#
# Подмодули:
#   bridge              — локальный HTTP-сервер для отдачи видео в TikTok Studio
#   script_builder      — сборка строки публикации (path | tags | date | caption)
#   hashtag_generator   — генерация хэштегов по названию и тегам канала
#   userscript/         — Tampermonkey-скрипт для TikTok Studio

from .bridge import BridgeServer, BridgeConfig
from .script_builder import build_string, normalize_tags
from .hashtag_generator import generate_hashtags

__all__ = [
    "BridgeServer",
    "BridgeConfig",
    "build_string",
    "normalize_tags",
    "generate_hashtags",
]
