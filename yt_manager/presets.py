# presets.py — Система пресетов
# Экспорт/импорт пресетов в JSON-файлы, применение к config.json.

import json
import os
from datetime import datetime

from db import db


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


def export_preset_file(preset: dict, filepath: str) -> bool:
    """Сохраняет один пресет в JSON-файл."""
    try:
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
    """Сохраняет несколько пресетов в один JSON-файл."""
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


def import_preset_file(filepath: str) -> list:
    """
    Читает JSON-файл пресета / коллекции пресетов.
    Возвращает список dict: [{name, description, data}, ...].
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            raw = json.load(f)

        if raw.get("yt_manager_presets"):
            return raw.get("presets", [])
        if raw.get("yt_manager_preset"):
            return [{"name": raw["name"],
                     "description": raw.get("description", ""),
                     "data": raw.get("data", {})}]
        # Чужой формат: просто dict настроек
        return [{"name": "Импортированный",
                 "description": f"Из файла {os.path.basename(filepath)}",
                 "data": raw}]
    except Exception:
        return []


def apply_preset_to_config(data: dict, config_path: str) -> bool:
    """Применяет секцию 'paths' из пресета в config.json."""
    try:
        cfg = {}
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        paths = data.get("paths", {})
        if paths:
            cfg.setdefault("paths", {}).update(paths)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
