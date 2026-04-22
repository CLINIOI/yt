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
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QSpinBox, QVBoxLayout, QWidget,
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


# Тестируем два разных видео: обычное + потенциально возрастное
COOKIES_TEST_URLS: list[tuple[str, str]] = [
    ("Обычное", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("Возрастное", "https://www.youtube.com/watch?v=HyHNuVaZJ-k"),
]


class CookiesTestWorker(QThread):
    """Фоновая проверка куки: пробует yt-dlp получить info тестовых видео.

    Проверяет два разных видео (обычное + возрастное) и собирает
    детализированный отчёт: какие куки применяются, получены ли форматы,
    полный текст ошибки при падении.
    """

    finished_report = pyqtSignal(bool, str)  # ok, html/text report

    def __init__(self, mode: str, browser: str, file_path: str,
                 use_mobile: bool, parent=None):
        super().__init__(parent)
        self.mode       = mode
        self.browser    = browser
        self.file_path  = file_path
        self.use_mobile = use_mobile

    def _build_opts(self) -> tuple[dict, str]:
        """Формирует opts и описание применяемых куки."""
        opts: dict = {"quiet": True, "no_warnings": True, "skip_download": True}
        desc = ""
        if self.mode == "browser":
            opts["cookiesfrombrowser"] = (self.browser,)
            desc = f"Из браузера {self.browser}"
        elif self.mode == "file":
            if not self.file_path or not os.path.isfile(self.file_path):
                return {}, f"Файл cookies.txt не найден: {self.file_path}"
            opts["cookiefile"] = self.file_path
            # Считаем кол-во записей в файле (строки не-комментарии)
            try:
                with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [ln for ln in f
                             if ln.strip() and not ln.lstrip().startswith("#")]
                desc = f"Из файла {self.file_path} ({len(lines)} записей)"
            except Exception:
                desc = f"Из файла {self.file_path}"
        else:
            desc = "Авто (куки не применяются — проверяем доступ по IP)"

        if self.use_mobile:
            opts["extractor_args"] = {
                "youtube": {"player_client": ["ios", "android", "web"]}
            }
        return opts, desc

    def run(self):
        try:
            import yt_dlp
            from youtube_service import classify_download_error
        except Exception as e:
            self.finished_report.emit(False, f"yt-dlp недоступен: {e}")
            return

        opts, desc = self._build_opts()
        if not opts:
            self.finished_report.emit(False, desc or "Не удалось подготовить опции")
            return

        lines: list[str] = []
        lines.append(f"Применяется: {desc}")
        lines.append(
            f"Мобильные клиенты: {'ВКЛ (ios/android/web)' if self.use_mobile else 'выкл'}"
        )
        lines.append("")

        ok_total = True
        for label, url in COOKIES_TEST_URLS:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                title = (info or {}).get("title") or "(без названия)"
                fmts = (info or {}).get("formats") or []
                heights = sorted({int(f.get("height") or 0) for f in fmts
                                  if f.get("height")}, reverse=True)
                heights_s = ", ".join(f"{h}p" for h in heights[:8]) or "—"
                lines.append(f"✓ {label}: «{title}»")
                lines.append(f"    Доступные форматы: {heights_s}")
            except yt_dlp.utils.DownloadError as e:
                ok_total = False
                lines.append(f"✗ {label}: {classify_download_error(str(e))}")
                lines.append(f"    Полный текст: {e}")
            except Exception as e:
                ok_total = False
                lines.append(f"✗ {label}: {type(e).__name__}: {e}")

        self.finished_report.emit(ok_total, "\n".join(lines))


class YtDlpUpdateWorker(QThread):
    """Запускает `pip install -U yt-dlp` в фоне; стримит stdout в сигнал."""

    line_emitted = pyqtSignal(str)
    finished_ok  = pyqtSignal(str)   # итоговый stdout
    finished_fail = pyqtSignal(str)  # текст ошибки

    def run(self):
        import subprocess
        import sys
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
        except Exception as e:
            self.finished_fail.emit(f"Не удалось запустить pip: {e}")
            return

        buf: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                buf.append(line)
                self.line_emitted.emit(line)
        rc = proc.wait()
        output = "\n".join(buf)
        if rc == 0:
            self.finished_ok.emit(output)
        else:
            self.finished_fail.emit(
                f"pip завершился с кодом {rc}:\n{output}"
            )


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

        # Чекбокс «Мобильные клиенты» — обход проверки бота
        self.chk_mobile_clients = QCheckBox(
            "Мобильные клиенты YouTube (обход проверки бота, ios/android/web)"
        )
        self.chk_mobile_clients.setToolTip(
            "Использовать клиенты ios/android/web через extractor_args. "
            "Часто решает ошибку «Sign in to confirm you're not a bot» "
            "даже без куки. Рекомендуется держать ВКЛ."
        )
        lay.addWidget(self.chk_mobile_clients)

        # Подсказка с реально применяемыми куками
        self.lbl_applied_cookies = QLabel("")
        self.lbl_applied_cookies.setWordWrap(True)
        self.lbl_applied_cookies.setStyleSheet(
            "color:#4f98a3; font-size:11px; font-weight:600;"
        )
        lay.addWidget(self.lbl_applied_cookies)

        row_test = QHBoxLayout()
        self.btn_cookies_test = QPushButton("Проверить куки")
        self.btn_cookies_test.clicked.connect(self._run_cookies_test)
        row_test.addWidget(self.btn_cookies_test)
        self.btn_ytdlp_update = QPushButton("Обновить yt-dlp")
        self.btn_ytdlp_update.setToolTip(
            "Запускает `pip install -U yt-dlp`. Это решает большинство "
            "ошибок «Sign in to confirm» при новых изменениях YouTube."
        )
        self.btn_ytdlp_update.clicked.connect(self._run_ytdlp_update)
        row_test.addWidget(self.btn_ytdlp_update)
        self.lbl_cookies_status = QLabel("")
        self.lbl_cookies_status.setWordWrap(True)
        row_test.addWidget(self.lbl_cookies_status, 1)
        lay.addLayout(row_test)

        self._cookies_test_worker: Optional[CookiesTestWorker] = None
        self._ytdlp_update_worker: Optional[YtDlpUpdateWorker] = None

        # Обновлять подсказку при изменениях
        for w in (self.rb_cookies_auto, self.rb_cookies_browser,
                  self.rb_cookies_file):
            w.toggled.connect(self._update_applied_cookies_label)
        self.cmb_cookies_browser.currentTextChanged.connect(
            lambda *_: self._update_applied_cookies_label()
        )
        self.ed_cookies_file.textChanged.connect(
            lambda *_: self._update_applied_cookies_label()
        )
        return g

    def _update_applied_cookies_label(self):
        """Показывает что именно применится при следующем запуске yt-dlp."""
        mode = self._current_cookies_mode()
        if mode == "browser":
            br = self.cmb_cookies_browser.currentText().strip().lower()
            text = f"Применяется: Из браузера {br}"
        elif mode == "file":
            path = self.ed_cookies_file.text().strip()
            if path and os.path.isfile(path):
                text = f"Применяется: Из файла {path}"
            else:
                text = f"⚠ Файл не найден: {path or '(путь пуст)'} — будет использована автологика"
        else:
            from youtube_service import AUTO_COOKIES_FILE
            if os.path.isfile(AUTO_COOKIES_FILE):
                text = f"Применяется: Авто → {AUTO_COOKIES_FILE}"
            else:
                text = "Применяется: Авто (будет попытка прочитать куки из браузера)"
        self.lbl_applied_cookies.setText(text)

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
            use_mobile=bool(self.chk_mobile_clients.isChecked()),
            parent=self,
        )
        self._cookies_test_worker.finished_report.connect(self._on_cookies_report)
        self._cookies_test_worker.finished.connect(
            lambda: self.btn_cookies_test.setEnabled(True)
        )
        self._cookies_test_worker.start()

    def _on_cookies_report(self, ok: bool, report: str):
        if ok:
            self.lbl_cookies_status.setStyleSheet("color:#2e8b57; font-weight:700;")
            self.lbl_cookies_status.setText("✓ Куки работают (см. детали)")
        else:
            self.lbl_cookies_status.setStyleSheet("color:#d64545; font-weight:700;")
            self.lbl_cookies_status.setText("✗ Проверка не прошла (см. детали)")
        # Показываем подробный отчёт в прокручиваемом окне
        self._show_cookies_report_dialog(ok, report)

    def _show_cookies_report_dialog(self, ok: bool, report: str):
        dlg = QDialog(self)
        dlg.setWindowTitle("Проверка куки — результат")
        dlg.resize(720, 440)
        v = QVBoxLayout(dlg)
        title = QLabel("✓ Успешно" if ok else "✗ Ошибка")
        title.setStyleSheet(
            "color:#2e8b57; font-weight:700; font-size:14px;" if ok
            else "color:#d64545; font-weight:700; font-size:14px;"
        )
        v.addWidget(title)
        te = QPlainTextEdit()
        te.setReadOnly(True)
        te.setPlainText(report)
        v.addWidget(te, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()

    def _run_ytdlp_update(self):
        if self._ytdlp_update_worker and self._ytdlp_update_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, "Обновить yt-dlp",
            "Будет выполнено `pip install -U yt-dlp` в активном окружении.\n"
            "Продолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Обновление yt-dlp")
        dlg.resize(720, 440)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Запуск `pip install -U yt-dlp`…"))
        te = QPlainTextEdit()
        te.setReadOnly(True)
        v.addWidget(te, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        btn_close = bb.button(QDialogButtonBox.StandardButton.Close)
        btn_close.setEnabled(False)
        v.addWidget(bb)

        self._ytdlp_update_worker = YtDlpUpdateWorker(parent=self)
        w = self._ytdlp_update_worker
        w.line_emitted.connect(lambda ln: te.appendPlainText(ln))
        def _on_ok(out: str):
            te.appendPlainText("")
            te.appendPlainText("✓ Готово. Перезапустите приложение, чтобы "
                               "новая версия yt-dlp вступила в силу.")
            btn_close.setEnabled(True)
        def _on_fail(err: str):
            te.appendPlainText("")
            te.appendPlainText(f"✗ Ошибка:\n{err}")
            btn_close.setEnabled(True)
        w.finished_ok.connect(_on_ok)
        w.finished_fail.connect(_on_fail)
        w.start()
        dlg.exec()

    def _save_cookies_settings(self):
        db.set_setting("yt_cookies_mode", self._current_cookies_mode())
        db.set_setting("yt_cookies_browser",
                       self.cmb_cookies_browser.currentText().strip().lower())
        db.set_setting("yt_cookies_file", self.ed_cookies_file.text().strip())
        db.set_setting("yt_use_mobile_clients",
                       bool(self.chk_mobile_clients.isChecked()))

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
        # По умолчанию ВКЛ — helps обходить «Sign in to confirm»
        mobile_raw = db.get_setting("yt_use_mobile_clients", True)
        if isinstance(mobile_raw, str):
            mobile = mobile_raw.strip().lower() not in ("0", "false", "no", "")
        else:
            mobile = True if mobile_raw is None else bool(mobile_raw)
        self.chk_mobile_clients.setChecked(mobile)
        self.lbl_cookies_status.setText("")
        self._update_applied_cookies_label()

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
