# pages/settings_page.py — Страница «Настройки»
#
# Содержит:
#   • Диск: лимит на папки клипов/обработанного, кнопка очистки кэша.
#   • Тема: радио (тёмная / светлая) — сохраняется в app_settings.
#   • Bridge: автозапуск, host, port, token — сохраняются в app_settings.
#   • Helper userscript: кнопка «Сохранить как…» копирует встроенный
#     helper.user.js на выбранный путь (для установки в Tampermonkey).

from __future__ import annotations

import logging
import os
import shutil
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from pages.base_page import BasePage
from db import db


log = logging.getLogger(__name__)

USERSCRIPT_REL = os.path.join("tiktok", "userscript", "helper.user.js")

# Браузеры, которые yt-dlp умеет читать через --cookies-from-browser
YT_BROWSERS: list[str] = [
    "chrome", "firefox", "edge", "opera",
    "brave", "vivaldi", "chromium", "safari",
]

# Тестовое публично-доступное видео для проверки куки
COOKIES_TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class CookiesTestWorker(QThread):
    """Фоновая проверка куки: пробует yt-dlp получить info тестового видео."""

    finished_ok   = pyqtSignal(str)   # title
    finished_fail = pyqtSignal(str)   # human-readable error

    def __init__(self, mode: str, browser: str, file_path: str, parent=None):
        super().__init__(parent)
        self.mode     = mode
        self.browser  = browser
        self.file_path = file_path

    def run(self):
        try:
            import yt_dlp
            from youtube_service import classify_download_error
        except Exception as e:
            self.finished_fail.emit(f"yt-dlp недоступен: {e}")
            return

        opts: dict = {"quiet": True, "no_warnings": True, "skip_download": True}
        if self.mode == "browser":
            opts["cookiesfrombrowser"] = (self.browser,)
        elif self.mode == "file":
            if not self.file_path or not os.path.isfile(self.file_path):
                self.finished_fail.emit("Файл cookies.txt не найден.")
                return
            opts["cookiefile"] = self.file_path
        # Для режима "auto" ничего не добавляем — yt-dlp отработает без куков,
        # успех подтверждает, что YouTube разрешает доступ с текущего IP.

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(COOKIES_TEST_URL, download=False)
            title = (info or {}).get("title") or "(без названия)"
            self.finished_ok.emit(title)
        except yt_dlp.utils.DownloadError as e:
            self.finished_fail.emit(classify_download_error(str(e)))
        except Exception as e:
            self.finished_fail.emit(f"Ошибка: {e}")


# (name, title, bg, accent, text)
THEMES: list[tuple[str, str, str, str, str]] = [
    ("dark",      "Тёмная",     "#171614", "#4f98a3", "#cdccca"),
    ("light",     "Светлая",    "#f6f5f2", "#2c6d77", "#1c1b19"),
    ("midnight",  "Midnight",   "#0d1220", "#4d7fff", "#e0e6f0"),
    ("solarized", "Solarized",  "#fdf6e3", "#b58900", "#586e75"),
    ("contrast",  "Контраст",   "#000000", "#ffd400", "#ffffff"),
]


class SettingsPage(BasePage):
    """Глобальные настройки приложения."""

    PAGE_TITLE = "Настройки"

    theme_changed = pyqtSignal(str)  # испускается при смене темы

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    # ── UI ─────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        root.addWidget(self._build_disk_group())
        root.addWidget(self._build_cookies_group())
        root.addWidget(self._build_theme_group())
        root.addWidget(self._build_bridge_group())
        root.addWidget(self._build_userscript_group())
        root.addStretch()

        bar = QHBoxLayout()
        bar.addStretch()
        btn_save = QPushButton("Сохранить настройки")
        btn_save.clicked.connect(self._save_all)
        bar.addWidget(btn_save)
        root.addLayout(bar)

    def _build_disk_group(self) -> QGroupBox:
        g = QGroupBox("Диск")
        lay = QVBoxLayout(g)

        row = QHBoxLayout()
        row.addWidget(QLabel("Лимит для папок (GB):"))
        self.sp_disk_limit = QSpinBox()
        self.sp_disk_limit.setRange(0, 10000)
        self.sp_disk_limit.setSpecialValueText("без ограничений")
        self.sp_disk_limit.setSuffix(" GB")
        row.addWidget(self.sp_disk_limit)
        row.addStretch()
        lay.addLayout(row)

        row = QHBoxLayout()
        btn = QPushButton("Очистить кэш (downloads/processed)")
        btn.clicked.connect(self._clear_cache)
        row.addWidget(btn)
        row.addStretch()
        self.lbl_disk_status = QLabel("")
        self.lbl_disk_status.setStyleSheet("color:#5a5957;")
        row.addWidget(self.lbl_disk_status)
        lay.addLayout(row)
        return g

    def _build_cookies_group(self) -> QGroupBox:
        g = QGroupBox("YouTube — куки для скачивания")
        lay = QVBoxLayout(g)

        hint = QLabel(
            "Если YouTube требует «Sign in to confirm you're not a bot», "
            "выберите источник куки ниже. Для режима «Из браузера» браузер "
            "должен быть установлен на этом же компьютере."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a8985; font-size:11px;")
        lay.addWidget(hint)

        self.rb_cookies_auto    = QRadioButton("Автоматически (cookies.txt рядом с проектом → браузер)")
        self.rb_cookies_browser = QRadioButton("Из браузера:")
        self.rb_cookies_file    = QRadioButton("Из файла cookies.txt:")
        self._cookies_group = QButtonGroup(self)
        self._cookies_group.addButton(self.rb_cookies_auto)
        self._cookies_group.addButton(self.rb_cookies_browser)
        self._cookies_group.addButton(self.rb_cookies_file)

        lay.addWidget(self.rb_cookies_auto)

        row_b = QHBoxLayout()
        row_b.addWidget(self.rb_cookies_browser)
        self.cmb_cookies_browser = QComboBox()
        self.cmb_cookies_browser.addItems(YT_BROWSERS)
        self.cmb_cookies_browser.setMaximumWidth(160)
        row_b.addWidget(self.cmb_cookies_browser)
        row_b.addStretch()
        lay.addLayout(row_b)

        row_f = QHBoxLayout()
        row_f.addWidget(self.rb_cookies_file)
        self.ed_cookies_file = QLineEdit()
        self.ed_cookies_file.setPlaceholderText("полный путь к cookies.txt")
        row_f.addWidget(self.ed_cookies_file, 1)
        btn_pick = QPushButton("…")
        btn_pick.setMaximumWidth(36)
        btn_pick.clicked.connect(self._pick_cookies_file)
        row_f.addWidget(btn_pick)
        lay.addLayout(row_f)

        # Автопереключение радио при активном действии
        self.cmb_cookies_browser.activated.connect(
            lambda *_: self.rb_cookies_browser.setChecked(True)
        )
        self.ed_cookies_file.textEdited.connect(
            lambda *_: self.rb_cookies_file.setChecked(True)
        )

        row_test = QHBoxLayout()
        self.btn_cookies_test = QPushButton("Проверить куки")
        self.btn_cookies_test.clicked.connect(self._run_cookies_test)
        row_test.addWidget(self.btn_cookies_test)
        self.lbl_cookies_status = QLabel("")
        self.lbl_cookies_status.setWordWrap(True)
        row_test.addWidget(self.lbl_cookies_status, 1)
        lay.addLayout(row_test)

        self._cookies_test_worker: Optional[CookiesTestWorker] = None
        return g

    def _pick_cookies_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите cookies.txt",
            self.ed_cookies_file.text() or "",
            "Cookies (*.txt);;Все файлы (*.*)"
        )
        if path:
            self.ed_cookies_file.setText(path)
            self.rb_cookies_file.setChecked(True)

    def _current_cookies_mode(self) -> str:
        if self.rb_cookies_browser.isChecked():
            return "browser"
        if self.rb_cookies_file.isChecked():
            return "file"
        return "auto"

    def _run_cookies_test(self):
        if self._cookies_test_worker and self._cookies_test_worker.isRunning():
            return
        # Сохраняем текущие настройки, чтобы тест использовал их
        self._save_cookies_settings()
        self.btn_cookies_test.setEnabled(False)
        self.lbl_cookies_status.setStyleSheet("color:#8a8985;")
        self.lbl_cookies_status.setText("Проверка…")
        self._cookies_test_worker = CookiesTestWorker(
            mode=self._current_cookies_mode(),
            browser=self.cmb_cookies_browser.currentText().strip().lower(),
            file_path=self.ed_cookies_file.text().strip(),
            parent=self,
        )
        self._cookies_test_worker.finished_ok.connect(self._on_cookies_ok)
        self._cookies_test_worker.finished_fail.connect(self._on_cookies_fail)
        self._cookies_test_worker.finished.connect(
            lambda: self.btn_cookies_test.setEnabled(True)
        )
        self._cookies_test_worker.start()

    def _on_cookies_ok(self, title: str):
        self.lbl_cookies_status.setStyleSheet("color:#2e8b57; font-weight:700;")
        self.lbl_cookies_status.setText(f"✓ Куки работают — получено видео «{title}»")

    def _on_cookies_fail(self, err: str):
        self.lbl_cookies_status.setStyleSheet("color:#d64545; font-weight:700;")
        self.lbl_cookies_status.setText(f"✗ {err}")

    def _save_cookies_settings(self):
        db.set_setting("yt_cookies_mode", self._current_cookies_mode())
        db.set_setting("yt_cookies_browser",
                       self.cmb_cookies_browser.currentText().strip().lower())
        db.set_setting("yt_cookies_file", self.ed_cookies_file.text().strip())

    def _build_theme_group(self) -> QGroupBox:
        g = QGroupBox("Тема оформления")
        outer = QVBoxLayout(g)
        hint = QLabel("Клик по карточке — тема применится мгновенно.")
        hint.setStyleSheet("color:#8a8985; font-size:11px;")
        outer.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(12)
        self._theme_cards: dict[str, QFrame] = {}
        for idx, (name, title, bg, accent, text) in enumerate(THEMES):
            card = self._make_theme_card(name, title, bg, accent, text)
            self._theme_cards[name] = card
            grid.addWidget(card, idx // 3, idx % 3)
        outer.addLayout(grid)
        return g

    def _make_theme_card(self, name: str, title: str,
                         bg: str, accent: str, text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("theme_card")
        card.setFixedSize(200, 140)
        card.setProperty("selected", "false")
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        v = QVBoxLayout(card)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{accent}; font-weight:700; font-size:13px;"
                          f" background:transparent;")
        v.addWidget(lbl)

        preview = QFrame()
        preview.setFixedHeight(60)
        preview.setStyleSheet(f"background:{bg}; border-radius:4px;")
        pv = QVBoxLayout(preview)
        pv.setContentsMargins(8, 8, 8, 8)
        pv.setSpacing(4)
        stripe_text = QFrame()
        stripe_text.setFixedHeight(6)
        stripe_text.setStyleSheet(f"background:{text}; border-radius:2px;")
        stripe_acc = QFrame()
        stripe_acc.setFixedHeight(6)
        stripe_acc.setStyleSheet(f"background:{accent}; border-radius:2px;")
        stripe_text2 = QFrame()
        stripe_text2.setFixedHeight(6)
        stripe_text2.setStyleSheet(f"background:{text}; border-radius:2px;")
        pv.addWidget(stripe_text)
        pv.addWidget(stripe_acc)
        pv.addWidget(stripe_text2)
        pv.addStretch()
        v.addWidget(preview)

        hint = QLabel(f"{bg} · {accent}")
        hint.setStyleSheet("color:#8a8985; font-size:10px; background:transparent;")
        v.addWidget(hint)

        card.mousePressEvent = lambda e, n=name: self._on_theme_card_clicked(n)
        return card

    def _on_theme_card_clicked(self, name: str):
        self._select_theme_card(name)
        old_theme = db.get_setting("theme", "dark")
        db.set_setting("theme", name)
        if name != old_theme:
            self.theme_changed.emit(name)

    def _select_theme_card(self, name: str):
        for n, card in self._theme_cards.items():
            card.setProperty("selected", "true" if n == name else "false")
            card.style().unpolish(card)
            card.style().polish(card)
            card.update()

    def _build_bridge_group(self) -> QGroupBox:
        g = QGroupBox("TikTok Bridge (HTTP-сервер для расширения)")
        lay = QVBoxLayout(g)

        row = QHBoxLayout()
        self.chk_bridge_auto = QCheckBox("Запускать автоматически при старте")
        row.addWidget(self.chk_bridge_auto)
        row.addStretch()
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Host:"))
        self.ed_bridge_host = QLineEdit()
        self.ed_bridge_host.setMaximumWidth(180)
        row.addWidget(self.ed_bridge_host)
        row.addSpacing(12)
        row.addWidget(QLabel("Port:"))
        self.sp_bridge_port = QSpinBox()
        self.sp_bridge_port.setRange(1024, 65535)
        row.addWidget(self.sp_bridge_port)
        row.addSpacing(12)
        row.addWidget(QLabel("Token:"))
        self.ed_bridge_token = QLineEdit()
        self.ed_bridge_token.setMaximumWidth(220)
        row.addWidget(self.ed_bridge_token)
        row.addStretch()
        lay.addLayout(row)
        return g

    def _build_userscript_group(self) -> QGroupBox:
        g = QGroupBox("Helper userscript для Tampermonkey")
        lay = QHBoxLayout(g)
        lbl = QLabel(
            "Сохраните helper.user.js и установите в Tampermonkey "
            "для автоматизации публикации в TikTok."
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        btn = QPushButton("Сохранить как…")
        btn.clicked.connect(self._save_userscript)
        lay.addWidget(btn)
        return g

    # ── Data ───────────────────────────────────────────────────────
    def refresh(self):
        self.sp_disk_limit.setValue(int(db.get_setting("disk_limit_gb", 0) or 0))
        theme = db.get_setting("theme", "dark") or "dark"
        if theme not in self._theme_cards:
            theme = "dark"
        self._select_theme_card(theme)
        self.chk_bridge_auto.setChecked(bool(db.get_setting("bridge_auto_start", False)))
        self.ed_bridge_host.setText(str(db.get_setting("bridge_host", "127.0.0.1") or ""))
        self.sp_bridge_port.setValue(int(db.get_setting("bridge_port", 8765) or 8765))
        self.ed_bridge_token.setText(str(db.get_setting("bridge_token", "1224444") or ""))

        # ── Куки YouTube ────────────────────────────────────────────
        mode = (db.get_setting("yt_cookies_mode", "auto") or "auto").strip().lower()
        browser = (db.get_setting("yt_cookies_browser", "chrome") or "chrome").strip().lower()
        cookies_file = str(db.get_setting("yt_cookies_file", "") or "")
        if browser in YT_BROWSERS:
            self.cmb_cookies_browser.setCurrentText(browser)
        self.ed_cookies_file.setText(cookies_file)
        if mode == "browser":
            self.rb_cookies_browser.setChecked(True)
        elif mode == "file":
            self.rb_cookies_file.setChecked(True)
        else:
            self.rb_cookies_auto.setChecked(True)
        self.lbl_cookies_status.setText("")

    def _save_all(self):
        db.set_setting("disk_limit_gb", int(self.sp_disk_limit.value()))
        db.set_setting("bridge_auto_start", bool(self.chk_bridge_auto.isChecked()))
        db.set_setting("bridge_host", self.ed_bridge_host.text().strip() or "127.0.0.1")
        db.set_setting("bridge_port", int(self.sp_bridge_port.value()))
        db.set_setting("bridge_token", self.ed_bridge_token.text().strip() or "1224444")
        self._save_cookies_settings()
        QMessageBox.information(self, "Сохранено", "Настройки сохранены.")

    # ── Actions ────────────────────────────────────────────────────
    def _clear_cache(self):
        from main import BASE_DIR  # type: ignore
        targets = [
            os.path.join(BASE_DIR, "downloads"),
            os.path.join(BASE_DIR, "processed"),
        ]
        reply = QMessageBox.question(
            self, "Очистка кэша",
            "Удалить содержимое папок downloads/ и processed/?\n"
            "Файлы будут удалены безвозвратно.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        removed = 0
        for d in targets:
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                p = os.path.join(d, name)
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                    removed += 1
                except Exception as e:
                    log.warning("clear cache: %s: %s", p, e)
        self.lbl_disk_status.setText(f"Удалено объектов: {removed}")

    def _save_userscript(self):
        from main import BASE_DIR  # type: ignore
        src = os.path.join(BASE_DIR, USERSCRIPT_REL)
        if not os.path.isfile(src):
            QMessageBox.warning(
                self, "Не найдено",
                f"Файл userscript не найден:\n{src}"
            )
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Сохранить helper.user.js",
            "helper.user.js", "Userscript (*.user.js)"
        )
        if not target:
            return
        try:
            shutil.copyfile(src, target)
            QMessageBox.information(
                self, "Готово",
                f"Файл сохранён:\n{target}\n\n"
                "Откройте его в Tampermonkey для установки."
            )
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить:\n{e}")
