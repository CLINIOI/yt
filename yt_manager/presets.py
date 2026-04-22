# presets.py — Система пресетов (v2)
#
# Экспорт/импорт пресетов в JSON с ПОЛНЫМ переносом состояния:
#     settings          — config.paths, диск, тема, bridge
#     channels          — YouTube-каналы + связи с TikTok
#     tiktok_channels   — TikTok-каналы + хэштеги + расписание
#     automation        — automation_settings на каждый TikTok-канал
#     processing_settings — per-channel настройки обработки
#
# Обратная совместимость: старый формат v1 с единственной секцией
# {cut, merge, stack, paths} продолжает читаться.

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Iterable

from db import db


PRESET_VERSION = 2

DEFAULT_PRESET: dict = {
    "cut": {
        "clip_duration": 60,
        "prefix": "clip",
        "reencode": False,
    },
    "merge": {
        "reencode": False,
    },
    "stack": {
        "ratio_top":    1,
        "ratio_center": 3,
        "ratio_bottom": 1,
        "output_width":  1080,
        "output_height": 1920,
        "audio_source": "center",
    },
    "paths": {
        "downloads":   "./downloads",
        "processed":   "./processed",
        "backgrounds": "./assets/backgrounds",
        "banners":     "./assets/banners",
    },
}


# ──────────────────────────────────────────────────────────────────────
# Экспорт
# ──────────────────────────────────────────────────────────────────────

def build_full_preset(name: str = "snapshot",
                      description: str = "",
                      config: dict | None = None) -> dict:
    """Собирает полный snapshot приложения для экспорта в пресет v2."""
    config = config or {}

    settings = {
        "paths": dict(config.get("paths", {}) or {}),
        "disk":  dict(config.get("disk", {}) or {}),
        "theme": db.get_setting("theme", "dark"),
        "bridge": {
            "auto_start": bool(db.get_setting("bridge_auto_start", False)),
            "host":       db.get_setting("bridge_host", "127.0.0.1"),
            "port":       db.get_setting("bridge_port", 8765),
            "token":      db.get_setting("bridge_token", "1224444"),
        },
    }

    # YouTube-каналы (без каскадного видео — это слишком много)
    channels_export = []
    for ch in db.get_all_channels():
        linked = db.list_tiktok_for_youtube(ch["id"])
        ps = db.get_processing_settings(ch["id"])
        channels_export.append({
            "url":           ch.get("url"),
            "title":         ch.get("title"),
            "yt_channel_id": ch.get("yt_channel_id"),
            "thumbnail_url": ch.get("thumbnail_url"),
            "enabled":       ch.get("enabled", 1),
            "auto_download": ch.get("auto_download", 0),
            "tiktok_links":  [t.get("handle") for t in linked if t.get("handle")],
            "processing":    {
                k: ps.get(k) for k in (
                    "clip_duration", "clip_enabled",
                    "merge_enabled", "merge_count",
                    "stack_enabled", "top_folder",
                    "center_folder", "bottom_folder",
                    "output_folder", "output_format",
                )
            },
        })

    # TikTok-каналы
    tiktok_export = []
    for tt in db.list_tiktok_channels():
        auto = db.get_automation_settings(tt["id"])
        tiktok_export.append({
            "handle":          tt.get("handle"),
            "display_name":    tt.get("display_name"),
            "avatar_url":      tt.get("avatar_url"),
            "hashtags":        tt.get("hashtags") or [],
            "schedule":        tt.get("schedule") or [],
            "clip_min_buffer": tt.get("clip_min_buffer", 10),
            "enabled":         tt.get("enabled", 1),
            "automation":      {
                k: auto.get(k) for k in (
                    "download_enabled", "min_duration_sec",
                    "max_duration_sec", "max_age_days",
                    "fallback_popular", "processing_enabled",
                    "banner_dir", "retention_dir",
                    "background_dir", "clip_duration_sec",
                    "publish_enabled",
                )
            },
        })

    return {
        "yt_manager_preset": True,
        "version":           PRESET_VERSION,
        "name":              name,
        "description":       description or "",
        "exported_at":       datetime.now().isoformat(timespec="seconds"),
        "settings":          settings,
        "channels":          channels_export,
        "tiktok_channels":   tiktok_export,
    }


def export_preset_file(preset: dict, filepath: str) -> bool:
    """
    Сохраняет пресет в JSON-файл.

    Если preset уже содержит полный v2-снимок (ключ 'settings') —
    пишет как есть. Иначе оборачивает data (v1-совместимость) в
    старый формат-обёртку.
    """
    try:
        if preset.get("version") == PRESET_VERSION or "settings" in preset:
            export_data = preset
        else:
            export_data = {
                "yt_manager_preset": True,
                "version":    1,
                "name":        preset.get("name", "preset"),
                "description": preset.get("description", ""),
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "data":        preset.get("data", {}),
            }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def export_all_presets_file(presets: list, filepath: str) -> bool:
    """Сохраняет набор v1-пресетов как коллекцию."""
    try:
        export_data = {
            "yt_manager_presets": True,
            "version":     1,
            "count":       len(presets),
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "presets": [
                {"name": p.get("name"), "description": p.get("description"),
                 "data": p.get("data", {})}
                for p in presets
            ],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────
# Импорт
# ──────────────────────────────────────────────────────────────────────

def import_preset_file(filepath: str) -> list:
    """
    Читает JSON-файл.

    Возвращает список [{name, description, data, raw}, …], где raw —
    исходный объект (нужен для apply_preset в v2). Пустой список
    означает ошибку чтения.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []

    # v2: полный snapshot
    if raw.get("version") == 2 or (raw.get("yt_manager_preset") and "settings" in raw):
        return [{
            "name": raw.get("name", "Import"),
            "description": raw.get("description", ""),
            "data": {
                "settings": raw.get("settings", {}),
                "channels": raw.get("channels", []),
                "tiktok_channels": raw.get("tiktok_channels", []),
            },
            "raw": raw,
        }]

    # v1 single
    if raw.get("yt_manager_preset"):
        return [{
            "name": raw.get("name", "preset"),
            "description": raw.get("description", ""),
            "data": raw.get("data", {}),
            "raw": raw,
        }]

    # v1 collection
    if raw.get("yt_manager_presets"):
        return [{
            "name": p.get("name"),
            "description": p.get("description", ""),
            "data": p.get("data", {}),
            "raw": p,
        } for p in raw.get("presets", [])]

    # Чужой формат
    return [{
        "name": "Импортированный",
        "description": f"Из файла {os.path.basename(filepath)}",
        "data": raw,
        "raw": raw,
    }]


# ──────────────────────────────────────────────────────────────────────
# Применение
# ──────────────────────────────────────────────────────────────────────

def apply_preset_to_config(data: dict, config_path: str) -> bool:
    """
    Применяет пресет к config.json и к базе данных.

    data — либо v1-формат (плоский dict c paths), либо v2-снимок
    с ключами settings/channels/tiktok_channels.
    """
    try:
        cfg = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}

        # v2: settings блок
        settings = data.get("settings") or {}
        paths = settings.get("paths") or data.get("paths") or {}
        if paths:
            cfg.setdefault("paths", {}).update(paths)

        if settings.get("disk"):
            cfg.setdefault("disk", {}).update(settings["disk"])

        # Тема и bridge — в app_settings
        if settings.get("theme"):
            db.set_setting("theme", settings["theme"])
        bridge = settings.get("bridge") or {}
        if bridge:
            if "auto_start" in bridge:
                db.set_setting("bridge_auto_start", bool(bridge["auto_start"]))
            if "host" in bridge:
                db.set_setting("bridge_host", bridge["host"])
            if "port" in bridge:
                db.set_setting("bridge_port", int(bridge["port"]))
            if "token" in bridge:
                db.set_setting("bridge_token", bridge["token"])

        # Каналы (v2)
        for ch in data.get("channels") or []:
            _apply_channel(ch)

        for tt in data.get("tiktok_channels") or []:
            _apply_tiktok_channel(tt)

        # Запись config.json
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return True
    except Exception:
        return False


def _apply_channel(ch: dict):
    """Импортирует один YouTube-канал: обновляет существующий или создаёт."""
    url = ch.get("url")
    if not url:
        return
    existing = [c for c in db.get_all_channels() if c.get("url") == url]
    if existing:
        ch_id = existing[0]["id"]
        db.update_channel(
            ch_id,
            title=ch.get("title"),
            yt_channel_id=ch.get("yt_channel_id"),
            thumbnail_url=ch.get("thumbnail_url"),
            enabled=int(ch.get("enabled", 1)),
            auto_download=int(ch.get("auto_download", 0)),
        )
    else:
        ch_id = db.add_channel(
            url=url, title=ch.get("title"),
            yt_channel_id=ch.get("yt_channel_id"),
            thumbnail_url=ch.get("thumbnail_url"),
        )
    if not ch_id:
        return

    # processing
    proc = ch.get("processing") or {}
    if proc:
        db.update_processing_settings(
            ch_id,
            **{k: v for k, v in proc.items() if v is not None}
        )

    # TikTok-связки
    for handle in ch.get("tiktok_links") or []:
        tt = db.get_tiktok_channel_by_handle(handle)
        if not tt:
            tt_id = db.add_tiktok_channel(handle=handle)
        else:
            tt_id = tt["id"]
        if tt_id:
            db.link_tiktok_to_youtube(tt_id, ch_id)


def _apply_tiktok_channel(tt: dict):
    handle = tt.get("handle")
    if not handle:
        return
    existing = db.get_tiktok_channel_by_handle(handle)
    if existing:
        tt_id = existing["id"]
        db.update_tiktok_channel(
            tt_id,
            display_name=tt.get("display_name"),
            avatar_url=tt.get("avatar_url"),
            clip_min_buffer=int(tt.get("clip_min_buffer", 10)),
            enabled=int(tt.get("enabled", 1)),
        )
    else:
        tt_id = db.add_tiktok_channel(
            handle=handle,
            display_name=tt.get("display_name"),
            avatar_url=tt.get("avatar_url"),
            clip_min_buffer=int(tt.get("clip_min_buffer", 10)),
        )
    if not tt_id:
        return
    db.set_tiktok_hashtags(tt_id, tt.get("hashtags") or [])
    db.set_tiktok_schedule(tt_id, tt.get("schedule") or [])

    auto = tt.get("automation") or {}
    clean = {k: v for k, v in auto.items() if v is not None}
    if clean:
        db.set_automation_settings(tt_id, **clean)
