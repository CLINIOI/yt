# main.py — Точка входа в приложение
#
# Порядок старта:
#   1. Настройки HiDPI
#   2. Загрузка config.json
#   3. Создание обязательных папок
#   4. Проверка окружения (StartupCheckDialog)
#   5. Инициализация БД
#   6. Создание MainWindow

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore    import Qt
from PyQt6.QtGui     import QFont

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Всегда работаем относительно папки проекта
os.chdir(BASE_DIR)

DEFAULT_CONFIG = {
    "app":      {"window_width": 1280, "window_height": 800},
    "paths": {
        "downloads":   os.path.join(BASE_DIR, "downloads"),
        "processed":   os.path.join(BASE_DIR, "processed"),
        "backgrounds": os.path.join(BASE_DIR, "assets", "backgrounds"),
        "banners":     os.path.join(BASE_DIR, "assets", "banners"),
    },
    "download":  {"max_parallel": 2, "format": "bestvideo+bestaudio/best"},
    "processing": {},
}


# ──────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Загружает config.json; при отсутствии создаёт с дефолтами."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Создаём дефолтный
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def ensure_dirs(config: dict):
    """Создаёт папки из config.paths, если их ещё нет."""
    paths = config.get("paths", {})
    for key, path in paths.items():
        if path:
            try:
                os.makedirs(path, exist_ok=True)
            except Exception:
                pass
    # Всегда создаём data/
    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    # Новая файловая структура: каналы, обработанное, клипы
    for folder in ("каналы", "обработанное", "клипы"):
        try:
            os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)
        except Exception:
            pass


def init_db():
    """Инициализирует БД (создаёт таблицы при первом запуске)."""
    try:
        from db import db  # noqa — вызов создаёт таблицы через _create_tables()
        _ = db
    except RuntimeError:
        raise
    except Exception as e:
        import traceback
        details = traceback.format_exc()
        raise RuntimeError(
            f"Не удалось инициализировать базу данных:\n{e}\n\n"
            f"Путь к проекту: {BASE_DIR}\n"
            f"Права на запись: {os.access(BASE_DIR, os.W_OK)}\n\n"
            f"Полная ошибка:\n{details}"
        ) from e


# ──────────────────────────────────────────────────────────────────────

def main():
    # 1. HiDPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("YT Manager")
    app.setApplicationVersion("0.1.0")

    # Системный шрифт
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    app.setFont(font)

    # 2. Конфиг
    config = load_config()

    # 3. Папки
    ensure_dirs(config)

    # 4. Проверка окружения
    try:
        from startup_check import show_startup_check
        should_start = show_startup_check(BASE_DIR)
        if not should_start:
            sys.exit(0)
    except Exception:
        # startup_check недоступен или упал — продолжаем,
        # но логируем причину, чтобы не молчать о реальной ошибке.
        import logging
        logging.getLogger(__name__).exception(
            "startup_check failed — продолжаем без проверки окружения"
        )

    # 5. БД
    try:
        init_db()
    except RuntimeError as e:
        from PyQt6.QtWidgets import QTextEdit
        msg = QMessageBox(None)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("Критическая ошибка")
        msg.setText("Не удалось инициализировать базу данных")
        msg.setDetailedText(str(e))
        msg.exec()
        sys.exit(1)

    # 6. Главное окно
    from ui_main import MainWindow
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
