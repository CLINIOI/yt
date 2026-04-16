# startup_check.py — Диалог проверки окружения при старте
#
# Проверяет: Python, SQLite, yt-dlp, ffmpeg, папки проекта.
# Статусы: "ok" / "warning" / "error".
# "error" блокирует запуск; "warning" — предупреждение, но app стартует.

import sys
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt


# ──────────────────────────────────────────────────────────────────────
# Результат одной проверки
# ──────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name:   str
    status: str    # "ok" | "warning" | "error"
    detail: str = ""
    hint:   str = ""   # совет при warning/error


DIALOG_STYLE = """
QDialog#startup_dialog {
    background: #171614;
}
QFrame#chk_header {
    background: #1c1b19;
    border-bottom: 1px solid #2d2c2a;
}
QLabel#chk_title { color: #cdccca; font-size: 17px; font-weight: 700; }
QLabel#chk_sub   { color: #5a5957; font-size: 12px; }

QFrame#chk_row {
    background: #1c1b19;
    border: 1px solid #2d2c2a;
    border-radius: 8px;
}
QLabel#chk_icon   { font-size: 18px; }
QLabel#chk_name   { color: #cdccca; font-size: 13px; font-weight: 600; }
QLabel#chk_detail { color: #797876; font-size: 11px; }
QLabel#chk_hint   { color: #bb653b; font-size: 11px; }

QFrame#warn_box {
    background: #2c2218;
    border: 1px solid #bb653b;
    border-radius: 8px;
}
QLabel#warn_text { color: #e8af34; font-size: 12px; }

QPushButton#btn_continue {
    background: #01696f; color: #f9f8f5;
    border: none; border-radius: 7px;
    font-size: 13px; font-weight: 700;
    padding: 9px 28px;
}
QPushButton#btn_continue:hover { background: #0c4e54; }

QPushButton#btn_quit {
    background: transparent; color: #5a5957;
    border: 1px solid #393836; border-radius: 7px;
    font-size: 13px; padding: 9px 20px;
}
QPushButton#btn_quit:hover { color: #dd6974; border-color: #dd6974; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 4px; }
QScrollBar::handle:vertical { background: #393836; border-radius: 2px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

STATUS_ICON = {"ok": "✅", "warning": "⚠️", "error": "❌"}


# ──────────────────────────────────────────────────────────────────────
# Проверки
# ──────────────────────────────────────────────────────────────────────

def _check_python() -> CheckResult:
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if v < (3, 10):
        return CheckResult("Python", "error", ver,
                           "Требуется Python 3.10+")
    return CheckResult("Python", "ok", ver)


def _check_sqlite() -> CheckResult:
    ver = sqlite3.sqlite_version
    return CheckResult("SQLite", "ok", ver)


def _check_ytdlp() -> CheckResult:
    path = shutil.which("yt-dlp")
    if path:
        try:
            r = subprocess.run(["yt-dlp", "--version"],
                               capture_output=True, text=True, timeout=5)
            ver = r.stdout.strip() or "установлен"
            return CheckResult("yt-dlp", "ok", ver)
        except Exception:
            return CheckResult("yt-dlp", "ok", "установлен")
    # Проверяем как python-модуль
    try:
        import yt_dlp
        return CheckResult("yt-dlp", "ok", "модуль загружен")
    except ImportError:
        pass
    return CheckResult("yt-dlp", "warning", "не найден",
                       "pip install yt-dlp  или добавь в PATH")


def _check_ffmpeg() -> CheckResult:
    path = shutil.which("ffmpeg")
    if path:
        try:
            r = subprocess.run(["ffmpeg", "-version"],
                               capture_output=True, text=True, timeout=5)
            line = r.stdout.splitlines()[0] if r.stdout else "установлен"
            ver = line.split("version")[1].split()[0] if "version" in line else "установлен"
            return CheckResult("ffmpeg", "ok", ver)
        except Exception:
            return CheckResult("ffmpeg", "ok", "установлен")
    return CheckResult("ffmpeg", "warning", "не найден",
                       "Нарезка / склейка / стекинг недоступны. "
                       "Установи ffmpeg и добавь в PATH.")


def _check_dirs(base_dir: str) -> CheckResult:
    data_dir = os.path.join(base_dir, "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
        test = os.path.join(data_dir, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.unlink(test)
        return CheckResult("Папки проекта", "ok", data_dir)
    except Exception as e:
        return CheckResult("Папки проекта", "error", str(e),
                           "Нет доступа на запись в папку проекта.")


def run_checks(base_dir: str) -> list[CheckResult]:
    return [
        _check_python(),
        _check_sqlite(),
        _check_ytdlp(),
        _check_ffmpeg(),
        _check_dirs(base_dir),
    ]


# ──────────────────────────────────────────────────────────────────────
# Диалог
# ──────────────────────────────────────────────────────────────────────

class StartupCheckDialog(QDialog):
    def __init__(self, results: list[CheckResult], parent=None):
        super().__init__(parent)
        self.setObjectName("startup_dialog")
        self.setWindowTitle("YT Manager — Проверка окружения")
        self.setFixedSize(480, 400)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.CustomizeWindowHint
        )
        self._results = results
        self._has_errors   = any(r.status == "error"   for r in results)
        self._has_warnings = any(r.status == "warning"  for r in results)
        self._build(results)
        self.setStyleSheet(DIALOG_STYLE)

    def _build(self, results: list[CheckResult]):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Шапка
        hdr = QFrame()
        hdr.setObjectName("chk_header")
        hdr.setFixedHeight(68)
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(24, 12, 24, 12)
        hdr_lay.setSpacing(2)
        hdr_lay.addWidget(self._lbl("🔧  Проверка окружения", "chk_title"))
        hdr_lay.addWidget(self._lbl("YT Manager проверяет необходимые компоненты", "chk_sub"))
        lay.addWidget(hdr)

        # Список проверок
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(16, 12, 16, 12)
        c_lay.setSpacing(6)
        for r in results:
            c_lay.addWidget(self._make_row(r))
        c_lay.addStretch()
        sa.setWidget(content)
        lay.addWidget(sa, stretch=1)

        # Предупреждение
        if self._has_errors or self._has_warnings:
            warn = QFrame()
            warn.setObjectName("warn_box")
            w_lay = QVBoxLayout(warn)
            w_lay.setContentsMargins(14, 10, 14, 10)
            texts = []
            for r in results:
                if r.status in ("warning", "error") and r.hint:
                    texts.append(f"{'⛔' if r.status == 'error' else '⚠'} {r.hint}")
            warn_lbl = QLabel("\n".join(texts))
            warn_lbl.setObjectName("warn_text")
            warn_lbl.setWordWrap(True)
            w_lay.addWidget(warn_lbl)
            pad = QHBoxLayout()
            pad.setContentsMargins(16, 0, 16, 12)
            pad.addWidget(warn)
            lay.addLayout(pad)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 10, 20, 16)
        btn_row.setSpacing(8)

        quit_btn = QPushButton("Выйти")
        quit_btn.setObjectName("btn_quit")
        quit_btn.clicked.connect(self.reject)
        btn_row.addWidget(quit_btn)
        btn_row.addStretch()

        ok_lbl = "Запустить" if not self._has_errors else "Всё равно запустить"
        cont_btn = QPushButton(ok_lbl)
        cont_btn.setObjectName("btn_continue")
        cont_btn.clicked.connect(self.accept)
        btn_row.addWidget(cont_btn)
        lay.addLayout(btn_row)

    def _make_row(self, r: CheckResult) -> QFrame:
        row = QFrame()
        row.setObjectName("chk_row")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        icon = QLabel(STATUS_ICON.get(r.status, "❓"))
        icon.setObjectName("chk_icon")
        icon.setFixedWidth(24)
        lay.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.addWidget(self._lbl(r.name, "chk_name"))
        if r.detail:
            text_col.addWidget(self._lbl(r.detail, "chk_detail"))
        lay.addLayout(text_col, stretch=1)
        return row

    @staticmethod
    def _lbl(text: str, obj: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName(obj)
        return l


def show_startup_check(base_dir: str, parent=None) -> bool:
    """
    Запускает проверки и показывает диалог если есть проблемы.
    Возвращает True если нужно продолжать запуск, False — выйти.
    """
    results = run_checks(base_dir)
    has_issues = any(r.status != "ok" for r in results)

    if not has_issues:
        return True  # всё OK — диалог не показываем

    dlg = StartupCheckDialog(results, parent)
    return dlg.exec() == QDialog.DialogCode.Accepted
