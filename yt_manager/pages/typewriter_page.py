# pages/typewriter_page.py — Страница генератора видео с эффектом печатной машинки
#
# Адаптировано из app_v15.py (typewriter-video) и интегрировано в YT Manager
# Использует PyQt6 вместо tkinter, сохраняя весь движок рендера оригинала.
#
# Возможности:
#   • Edge TTS (онлайн, ~200 голосов) и XTTS v2 (локальный, если установлен)
#   • Видео-фон (mp4/avi/mov)
#   • Режимы переполнения: обычный / сброс / прокрутка
#   • Режимы текста: обычный / субтитры / без текста
#   • Позиция и выравнивание текста
#   • Пакетный режим (папка с TXT)
#   • Выбор разрешения, размера шрифта, цветов, скорости печати

import os
import sys
import asyncio
import threading
import tempfile
import shutil
import queue
from pathlib import Path
from typing import Optional, List, Tuple

from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QSpinBox,
    QCheckBox, QComboBox, QScrollArea, QFileDialog,
    QSizePolicy, QProgressBar, QButtonGroup, QRadioButton,
    QSlider, QColorDialog, QGroupBox, QSplitter,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont

from pages.base_page import BasePage

# ── Опциональные зависимости рендера ──────────────────────────────────
try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    from moviepy.editor import ImageSequenceClip, AudioFileClip
    RENDER_AVAILABLE = True
    RENDER_ERROR = ""
except ImportError as e:
    RENDER_AVAILABLE = False
    RENDER_ERROR = str(e)

try:
    import cv2 as _cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from TTS.api import TTS as _CoquiTTS  # noqa: F401
    XTTS_AVAILABLE = True
    XTTS_ERROR = ""
except Exception as e:
    XTTS_AVAILABLE = False
    XTTS_ERROR = str(e)

try:
    import edge_tts as _edge_tts
    EDGE_AVAILABLE = True
except ImportError:
    EDGE_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ══════════════════════════════════════════════════════════════════════
FPS = 24
DEFAULT_BG = "#000000"
DEFAULT_FG = "#FFFFFF"

ENGINE_XTTS = "🧠 XTTS v2 (локальный, ~2 ГБ)"
ENGINE_EDGE = "☁ Edge TTS (онлайн, бесплатно)"

OVERFLOW_NONE   = "Обычный (весь текст сразу)"
OVERFLOW_CLEAR  = "📺 Сброс — очистить и печатать с начала"
OVERFLOW_SCROLL = "📜 Прокрутка — текст уезжает вверх"

HALIGN_LEFT   = "← Слева"
HALIGN_CENTER = "↔ По центру"
HALIGN_RIGHT  = "→ Справа"

VALIGN_TOP    = "↑ Сверху"
VALIGN_CENTER = "↕ По центру"
VALIGN_BOTTOM = "↓ Снизу"

TEXTMODE_NORMAL   = "normal"
TEXTMODE_SUBTITLE = "subtitle"
TEXTMODE_NOTEXT   = "no_text"

RESOLUTIONS = {
    "1920×1080 Full HD": (1920, 1080),
    "1280×720 HD":       (1280, 720),
    "1080×1080 Квадрат": (1080, 1080),
    "1080×1920 TikTok":  (1080, 1920),
    "854×480 SD":        (854,  480),
}

SPEED_MAP = {
    "Медленно":   5,
    "Нормально": 15,
    "Быстро":    30,
    "Мгновенно": 60,
}

XTTS_LANGUAGES = {
    "English":"en","Русский":"ru","Español":"es","Français":"fr",
    "Deutsch":"de","Italiano":"it","Português":"pt","Polski":"pl",
    "Türkçe":"tr","Nederlands":"nl","Čeština":"cs","中文":"zh-cn",
    "日本語":"ja","한국어":"ko","हिन्दी":"hi","العربية":"ar",
}

XTTS_SPEAKERS = sorted([
    "Claribel Dervla","Daisy Studious","Gracie Wise","Tammie Ema",
    "Alison Dietlinde","Ana Florence","Annmarie Nele","Asya Anara",
    "Brenda Stern","Gitta Nikolina","Henriette Usha","Sofia Hellen",
    "Tammy Grit","Tanja Adelina","Vjollca Johnnie","Andrew Chipper",
    "Badr Odhiambo","Dionisio Schuyler","Royston Min","Viktor Eka",
    "Abrahan Mack","Adde Michal","Baldur Sanjin","Craig Gutsy",
    "Damien Black","Gilberto Mathias","Ilkin Urbano","Kazuhiko Atallah",
    "Ludvig Milivoj","Suad Qasim","Torcull Diarmuid","Viktor Menelaos",
    "Zacharie Aimilios","Nova Hogarth","Maja Ruoho","Uta Obando",
])

EDGE_LANG_FILTER = {
    "Все": None, "Английский": "en-", "Русский": "ru-",
    "Испанский": "es-", "Немецкий": "de-", "Французский": "fr-",
}

FONT_CANDIDATES = [
    "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]

# ══════════════════════════════════════════════════════════════════════
# QSS
# ══════════════════════════════════════════════════════════════════════
PAGE_QSS = """
QWidget#tw_page { background: #171614; }

/* ── Тулбар ── */
QFrame#tw_toolbar {
    background: #1c1b19;
    border-bottom: 1px solid #2d2c2a;
}
QLabel#tw_heading {
    color: #cdccca; font-size: 16px; font-weight: 600;
}
QLabel#tw_sub {
    color: #5a5957; font-size: 11px;
}

/* ── Секции ── */
QFrame#tw_section {
    background: #1c1b19;
    border: 1px solid #2d2c2a;
    border-radius: 10px;
}
QFrame#tw_section_header {
    background: #201f1d;
    border-radius: 8px 8px 0 0;
    border-bottom: 1px solid #2d2c2a;
}
QLabel#tw_section_title {
    color: #cdccca; font-size: 13px; font-weight: 700;
}
QLabel#tw_label {
    color: #797876; font-size: 11px; font-weight: 600;
    letter-spacing: 0.5px;
}
QLabel#tw_hint {
    color: #3a3937; font-size: 10px; font-style: italic;
}
QLabel#tw_badge_ok {
    color: #6daa45; font-size: 10px;
    background: #1e2e16; border-radius: 4px;
    padding: 2px 8px;
}
QLabel#tw_badge_warn {
    color: #bb653b; font-size: 10px;
    background: #2e1e10; border-radius: 4px;
    padding: 2px 8px;
}
QLabel#tw_color_preview {
    border-radius: 6px;
    border: 1px solid #393836;
    min-width: 32px; min-height: 32px;
    max-width: 32px; max-height: 32px;
}

/* ── Поля ввода ── */
QTextEdit#tw_text_input {
    background: #201f1d;
    border: 1px solid #393836;
    border-radius: 8px;
    color: #cdccca;
    font-size: 13px;
    padding: 10px;
    selection-background-color: #313b3b;
}
QTextEdit#tw_text_input:focus { border-color: #4f98a3; }

QLineEdit#tw_field {
    background: #201f1d;
    border: 1px solid #393836;
    border-radius: 6px;
    color: #cdccca;
    font-size: 12px;
    padding: 6px 10px;
}
QLineEdit#tw_field:focus { border-color: #4f98a3; }

/* ── Комбобоксы ── */
QComboBox#tw_combo {
    background: #201f1d;
    border: 1px solid #393836;
    border-radius: 6px;
    color: #cdccca;
    font-size: 12px;
    padding: 5px 10px;
    min-width: 120px;
}
QComboBox#tw_combo:focus { border-color: #4f98a3; }
QComboBox#tw_combo::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #201f1d; color: #cdccca;
    border: 1px solid #393836; outline: none;
    selection-background-color: #313b3b;
}

/* ── Чекбоксы и радиокнопки ── */
QCheckBox#tw_check {
    color: #cdccca; font-size: 12px; spacing: 8px;
}
QCheckBox#tw_check::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid #393836;
    background: #201f1d;
}
QCheckBox#tw_check::indicator:checked {
    background: #4f98a3;
    border-color: #4f98a3;
}
QRadioButton#tw_radio {
    color: #cdccca; font-size: 12px; spacing: 8px;
}
QRadioButton#tw_radio::indicator {
    width: 14px; height: 14px;
    border-radius: 7px;
    border: 1px solid #393836;
    background: #201f1d;
}
QRadioButton#tw_radio::indicator:checked {
    background: #4f98a3;
    border-color: #4f98a3;
}

/* ── Слайдер ── */
QSlider#tw_slider::groove:horizontal {
    height: 4px; background: #2d2c2a;
    border-radius: 2px;
}
QSlider#tw_slider::handle:horizontal {
    background: #4f98a3;
    border: 2px solid #4f98a3;
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider#tw_slider::sub-page:horizontal {
    background: #4f98a3; border-radius: 2px;
}

/* ── Кнопки ── */
QPushButton#btn_generate {
    background: #4f98a3;
    color: #171614;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
    padding: 14px 32px;
    min-height: 48px;
}
QPushButton#btn_generate:hover   { background: #227f8b; }
QPushButton#btn_generate:pressed { background: #1a626b; }
QPushButton#btn_generate:disabled { background: #2d2c2a; color: #5a5957; }

QPushButton#btn_secondary {
    background: #201f1d;
    border: 1px solid #393836;
    border-radius: 6px;
    color: #cdccca;
    font-size: 12px;
    padding: 7px 14px;
}
QPushButton#btn_secondary:hover { border-color: #4f98a3; color: #4f98a3; }

QPushButton#btn_open_file {
    background: #1a3535;
    border: 1px solid #4f98a3;
    border-radius: 6px;
    color: #4f98a3;
    font-size: 11px;
    padding: 5px 12px;
}
QPushButton#btn_open_file:hover { background: #253535; }

/* ── Прогресс ── */
QProgressBar#tw_progress {
    background: #201f1d;
    border: 1px solid #2d2c2a;
    border-radius: 6px;
    text-align: center;
    color: #cdccca;
    font-size: 11px;
    height: 18px;
}
QProgressBar#tw_progress::chunk {
    background: #4f98a3;
    border-radius: 5px;
}

/* ── Лог ── */
QTextEdit#tw_log {
    background: #1c1b19;
    border: 1px solid #2d2c2a;
    border-radius: 6px;
    color: #797876;
    font-size: 11px;
    font-family: "Consolas", monospace;
    padding: 8px;
}
"""

# ══════════════════════════════════════════════════════════════════════
# RENDER ENGINE (из app_v15.py, без изменений)
# ══════════════════════════════════════════════════════════════════════

def _load_font(size: int):
    if not RENDER_AVAILABLE:
        return None
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, max(8, int(size)))
        except (IOError, OSError):
            continue
    return ImageFont.load_default()

def _text_w(text: str, font) -> float:
    try:
        return font.getlength(text)
    except AttributeError:
        return font.getsize(text)[0]

def _line_h(font, spacing: float = 1.45) -> int:
    try:
        bb  = font.getbbox("Ágjq|Щ")
        raw = bb[3] - bb[1]
    except AttributeError:
        raw = font.getsize("Ágjq|")[1]
    return max(1, int(raw * spacing))

def _wrap(text: str, font, max_w: int) -> List[str]:
    result: List[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            result.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            cand = cur + " " + w
            if _text_w(cand, font) <= max_w:
                cur = cand
            else:
                result.append(cur)
                cur = w
        result.append(cur)
    return result

def _auto_fit(text, frame_w, frame_h, requested_size, padding, spacing=1.45):
    max_w = frame_w - padding * 2
    max_h = frame_h - padding * 2
    size  = requested_size
    while size >= 8:
        font  = _load_font(size)
        lh    = _line_h(font, spacing)
        lines = _wrap(text, font, max_w)
        if lh * len(lines) <= max_h:
            return font, lines, lh, size
        size -= 2
    font  = _load_font(8)
    lh    = _line_h(font, spacing)
    lines = _wrap(text, font, max_w)
    return font, lines, lh, 8

def _hex_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _calc_x(lw: float, fw: int, padding: int, halign: str) -> int:
    if halign == HALIGN_LEFT:
        return padding
    if halign == HALIGN_RIGHT:
        return fw - int(lw) - padding
    return (fw - int(lw)) // 2

def _calc_y0(total_h: int, fh: int, padding: int, valign: str) -> int:
    if valign == VALIGN_TOP:
        return padding
    if valign == VALIGN_BOTTOM:
        return fh - total_h - padding
    return (fh - total_h) // 2

class BgVideoReader:
    def __init__(self, video_path: str, width: int, height: int):
        import cv2
        self._cap    = cv2.VideoCapture(video_path)
        self._width  = width
        self._height = height
        self._total  = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._cache: dict = {}

    def get_frame(self, fi: int) -> Optional[Image.Image]:
        import cv2
        if self._total <= 0:
            return None
        idx = fi % self._total
        if idx in self._cache:
            return self._cache[idx].copy()
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self._cap.read()
        if not ret:
            return None
        frame_rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil        = Image.fromarray(frame_rgb).resize(
            (self._width, self._height), Image.LANCZOS)
        if len(self._cache) < 120:
            self._cache[idx] = pil.copy()
        return pil

    def close(self):
        self._cap.release()
        self._cache.clear()

def _render_frame_normal(text, font, full_lines, lh, fw, fh,
                          bg_img, bg_rgb, fg_rgb, padding, max_w,
                          halign=HALIGN_CENTER, valign=VALIGN_CENTER,
                          scroll_offset=0):
    lines_so_far = _wrap(text, font, max_w) if text else []
    if bg_img is not None:
        img = bg_img.copy()
    else:
        img = Image.new("RGB", (fw, fh), bg_rgb)
    draw = ImageDraw.Draw(img)
    block_h = lh * len(lines_so_far)
    y = _calc_y0(block_h, fh, padding, valign) - scroll_offset
    for line in lines_so_far:
        if y + lh > 0 and y < fh:
            lw = _text_w(line, font)
            x  = _calc_x(lw, fw, padding, halign)
            draw.text((x, y), line, font=font, fill=fg_rgb)
        y += lh
    return img

def _render_subtitle_bar(visible, font, lh, fw, fh, bg_img,
                          bg_rgb, fg_rgb, padding, max_w,
                          bar_alpha=160, bottom_margin=40):
    if bg_img is not None:
        base = bg_img.copy().convert("RGBA")
    else:
        base = Image.new("RGBA", (fw, fh), bg_rgb + (255,))
    if not visible:
        return base.convert("RGB")
    vis_lines = _wrap(visible, font, max_w)
    if not vis_lines:
        return base.convert("RGB")
    n_lines = len(vis_lines)
    bar_h   = lh * n_lines + padding
    bar_y   = fh - bottom_margin - bar_h
    overlay = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([0, bar_y, fw, bar_y + bar_h], fill=(0, 0, 0, bar_alpha))
    composed = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(composed)
    y = bar_y + padding // 2
    for line in vis_lines:
        if not line:
            y += lh
            continue
        lw = _text_w(line, font)
        x  = (fw - int(lw)) // 2
        draw.text((x, y), line, font=font, fill=fg_rgb)
        y += lh
    return composed.convert("RGB")

def render_frames(text, width, height, font_size, bg_color, text_color,
                  chars_per_sec, audio_duration, overflow_mode,
                  bg_video_path, text_halign=HALIGN_CENTER,
                  text_valign=VALIGN_CENTER, text_padding=None,
                  subtitle_mode=False, no_text=False,
                  fps=FPS, tmp_dir="", status_cb=None) -> List[str]:
    padding = text_padding if (text_padding is not None and text_padding > 0) \
              else max(40, int(min(width, height) * 0.05))
    bg_rgb  = _hex_rgb(bg_color)
    fg_rgb  = _hex_rgb(text_color)
    max_w   = width - padding * 2

    total_frames  = max(1, int(audio_duration * fps))
    total_chars   = len(text)
    natural_cps   = total_chars / audio_duration if audio_duration > 0 else chars_per_sec
    eff_cps       = min(natural_cps, chars_per_sec)
    typing_frames = min(int(total_chars / max(eff_cps, 0.001) * fps), total_frames)

    bg_reader = None
    if bg_video_path and os.path.isfile(bg_video_path) and CV2_AVAILABLE:
        if status_cb: status_cb("🎬 Открытие видео-фона...")
        bg_reader = BgVideoReader(bg_video_path, width, height)

    def get_bg_pil(fi):
        return bg_reader.get_frame(fi) if bg_reader else None

    if status_cb: status_cb("🎞 Рендер кадров... 0%")
    paths: List[str] = []

    if no_text:
        for fi in range(total_frames):
            bg_pil = get_bg_pil(fi)
            img = bg_pil.copy() if bg_pil else Image.new("RGB", (width, height), bg_rgb)
            path = os.path.join(tmp_dir, f"frame_{fi:07d}.png")
            img.save(path, "PNG"); paths.append(path)
            if status_cb and fi % fps == 0:
                status_cb(f"🎞 Рендер кадров... {int(fi/total_frames*100)}%")
        if bg_reader: bg_reader.close()
        return paths

    if subtitle_mode:
        font = _load_font(font_size)
        lh   = _line_h(font)
        prev_idx = -1; last_img = None
        for fi in range(total_frames):
            char_idx = min(int((fi/fps)*eff_cps), total_chars) if fi < typing_frames else total_chars
            if char_idx != prev_idx:
                bg_pil = get_bg_pil(fi)
                last_img = _render_subtitle_bar(
                    text[:char_idx], font, lh, width, height,
                    bg_pil, bg_rgb, fg_rgb, padding, max_w)
                prev_idx = char_idx
            path = os.path.join(tmp_dir, f"frame_{fi:07d}.png")
            last_img.save(path, "PNG"); paths.append(path)
            if status_cb and fi % fps == 0:
                status_cb(f"🎞 Рендер кадров... {int(fi/total_frames*100)}%")
        if bg_reader: bg_reader.close()
        return paths

    if overflow_mode == OVERFLOW_NONE:
        font, full_lines, lh, _ = _auto_fit(text, width, height, font_size, padding)
        prev_idx = -1; last_img = None
        for fi in range(total_frames):
            char_idx = min(int((fi/fps)*eff_cps), total_chars) if fi < typing_frames else total_chars
            if char_idx != prev_idx:
                bg_pil   = get_bg_pil(fi)
                last_img = _render_frame_normal(
                    text[:char_idx], font, full_lines, lh,
                    width, height, bg_pil, bg_rgb, fg_rgb, padding, max_w,
                    halign=text_halign, valign=text_valign)
                prev_idx = char_idx
            path = os.path.join(tmp_dir, f"frame_{fi:07d}.png")
            last_img.save(path, "PNG"); paths.append(path)
            if status_cb and fi % fps == 0:
                status_cb(f"🎞 Рендер кадров... {int(fi/total_frames*100)}%")

    elif overflow_mode == OVERFLOW_CLEAR:
        font = _load_font(font_size)
        lh   = _line_h(font)
        max_lines_per_screen = max(1, (height - padding*2) // lh)
        all_wrapped = _wrap(text, font, max_w)
        screens = [all_wrapped[i:i+max_lines_per_screen]
                   for i in range(0, len(all_wrapped), max_lines_per_screen)] or [[""]]
        screen_start_chars = [0]
        built = 0
        for s in screens[:-1]:
            built += sum(len(l) + 1 for l in s)
            screen_start_chars.append(min(built, total_chars))
        prev_idx = -1; last_img = None
        for fi in range(total_frames):
            char_idx = min(int((fi/fps)*eff_cps), total_chars) if fi < typing_frames else total_chars
            if char_idx != prev_idx:
                cur_screen = 0
                for si, sc in enumerate(screen_start_chars):
                    if char_idx >= sc: cur_screen = si
                start_c    = screen_start_chars[cur_screen]
                local_text = text[start_c:char_idx]
                bg_pil = get_bg_pil(fi)
                img = bg_pil.copy() if bg_pil else Image.new("RGB", (width, height), bg_rgb)
                draw = ImageDraw.Draw(img)
                vis_lines = _wrap(local_text, font, max_w)
                block_h   = lh * len(vis_lines)
                y = _calc_y0(block_h, height, padding, text_valign)
                for line in vis_lines:
                    if not line: y += lh; continue
                    lw = _text_w(line, font)
                    x  = _calc_x(lw, width, padding, text_halign)
                    draw.text((x, y), line, font=font, fill=fg_rgb)
                    y += lh
                last_img = img; prev_idx = char_idx
            path = os.path.join(tmp_dir, f"frame_{fi:07d}.png")
            last_img.save(path, "PNG"); paths.append(path)
            if status_cb and fi % fps == 0:
                status_cb(f"🎞 Рендер кадров... {int(fi/total_frames*100)}%")

    elif overflow_mode == OVERFLOW_SCROLL:
        font = _load_font(font_size)
        lh   = _line_h(font)
        max_lines_visible = max(1, (height - padding*2) // lh)
        prev_idx = -1; scroll_target = 0; scroll_now = 0.0
        SCROLL_SPEED = lh * 0.15
        prev_lines = []; last_img = None
        for fi in range(total_frames):
            char_idx = min(int((fi/fps)*eff_cps), total_chars) if fi < typing_frames else total_chars
            if char_idx != prev_idx:
                all_lines  = _wrap(text[:char_idx], font, max_w)
                prev_lines = all_lines
                overflow   = len(all_lines) - max_lines_visible
                scroll_target = overflow * lh if overflow > 0 else 0
                prev_idx = char_idx
            if scroll_now < scroll_target:
                scroll_now = min(scroll_now + SCROLL_SPEED, scroll_target)
            elif scroll_now > scroll_target:
                scroll_now = max(scroll_now - SCROLL_SPEED, scroll_target)
            bg_pil = get_bg_pil(fi)
            img = bg_pil.copy() if bg_pil else Image.new("RGB", (width, height), bg_rgb)
            draw = ImageDraw.Draw(img)
            y = padding - int(scroll_now)
            for line in prev_lines:
                if y + lh > 0 and y < height:
                    lw = _text_w(line, font)
                    x  = _calc_x(lw, width, padding, text_halign)
                    draw.text((x, y), line, font=font, fill=fg_rgb)
                y += lh
            last_img = img
            path = os.path.join(tmp_dir, f"frame_{fi:07d}.png")
            img.save(path, "PNG"); paths.append(path)
            if status_cb and fi % fps == 0:
                status_cb(f"🎞 Рендер кадров... {int(fi/total_frames*100)}%")

    if bg_reader: bg_reader.close()
    return paths

def assemble_video(frame_paths, audio_path, output_path, fps=FPS):
    vid   = ImageSequenceClip(frame_paths, fps=fps)
    aud   = AudioFileClip(audio_path)
    final = vid.set_audio(aud)
    final.write_videofile(
        output_path, codec="libx264", audio_codec="aac",
        logger=None, temp_audiofile=output_path + ".tmp_audio.m4a",
    )
    aud.close(); vid.close(); final.close()

# ── TTS ───────────────────────────────────────────────────────────────
_xtts_model = None
_xtts_lock  = threading.Lock()

def _get_xtts(status_cb=None):
    global _xtts_model
    with _xtts_lock:
        if _xtts_model is None:
            if not XTTS_AVAILABLE:
                raise RuntimeError(
                    "XTTS v2 не установлен.\n"
                    "pip install torch torchaudio\n"
                    "pip install coqui-tts\n\n"
                    "Или переключись на ☁ Edge TTS.")
            if status_cb: status_cb("⏳ Загрузка XTTS v2 (~2 ГБ, только первый запуск)...")
            from TTS.api import TTS as CoquiTTS
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
            _xtts_model = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    return _xtts_model

def generate_audio_xtts(text, language, speaker, speaker_wav, output_path, status_cb=None):
    tts = _get_xtts(status_cb)
    if status_cb: status_cb("🔊 Синтез речи XTTS v2...")
    kw = {"text": text, "language": language, "file_path": output_path}
    if speaker_wav and os.path.isfile(speaker_wav):
        kw["speaker_wav"] = speaker_wav
    else:
        kw["speaker"] = speaker
    tts.tts_to_file(**kw)

async def _edge_synth_async(text, voice, output_path):
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    await comm.save(output_path)

async def _edge_list_voices_async():
    import edge_tts
    return await edge_tts.list_voices()

def generate_audio_edge(text, voice, output_path, status_cb=None):
    if not EDGE_AVAILABLE:
        raise RuntimeError("edge-tts не установлен.\npip install edge-tts")
    if status_cb: status_cb("🔊 Синтез речи Edge TTS...")
    asyncio.run(_edge_synth_async(text, voice, output_path))

def run_pipeline(params: dict, status_cb, done_cb, error_cb):
    tmp = tempfile.mkdtemp(prefix="tw_yt_")
    try:
        ext        = "wav" if params["engine"] == ENGINE_XTTS else "mp3"
        audio_path = os.path.join(tmp, f"speech.{ext}")
        if params["engine"] == ENGINE_XTTS:
            generate_audio_xtts(
                text=params["text"], language=params["xtts_lang"],
                speaker=params["xtts_speaker"],
                speaker_wav=params.get("speaker_wav"),
                output_path=audio_path, status_cb=status_cb,
            )
        else:
            generate_audio_edge(
                text=params["text"], voice=params["edge_voice"],
                output_path=audio_path, status_cb=status_cb,
            )
        ac  = AudioFileClip(audio_path)
        dur = ac.duration; ac.close()

        frame_dir = os.path.join(tmp, "frames")
        os.makedirs(frame_dir)
        frame_paths = render_frames(
            text=params["text"],
            width=params["width"], height=params["height"],
            font_size=params["font_size"],
            bg_color=params["bg_color"], text_color=params["text_color"],
            chars_per_sec=params["chars_per_sec"],
            audio_duration=dur,
            overflow_mode=params["overflow_mode"],
            bg_video_path=params.get("bg_video_path"),
            text_halign=params.get("text_halign", HALIGN_CENTER),
            text_valign=params.get("text_valign", VALIGN_CENTER),
            text_padding=params.get("text_padding"),
            subtitle_mode=params.get("subtitle_mode", False),
            no_text=params.get("no_text", False),
            fps=FPS, tmp_dir=frame_dir, status_cb=status_cb,
        )
        status_cb("🎬 Сборка видео...")
        out = os.path.join(params["save_dir"], params["filename"])
        assemble_video(frame_paths, audio_path, out, fps=FPS)
        status_cb("✅ Готово!")
        done_cb(out)
    except Exception as exc:
        import traceback
        error_cb(f"{exc}\n\n{traceback.format_exc()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ══════════════════════════════════════════════════════════════════════
# WORKER THREAD
# ══════════════════════════════════════════════════════════════════════
class RenderWorker(QThread):
    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    finished       = pyqtSignal(str)
    error          = pyqtSignal(str)

    def __init__(self, params: dict):
        super().__init__()
        self.params = params

    def run(self):
        def status_cb(msg):
            self.status_update.emit(msg)
            if "%" in msg:
                try:
                    pct = int(msg.split("%")[0].split()[-1])
                    self.progress_update.emit(pct)
                except Exception:
                    pass

        run_pipeline(
            self.params,
            status_cb=status_cb,
            done_cb=lambda p: self.finished.emit(p),
            error_cb=lambda e: self.error.emit(e),
        )

class EdgeVoiceLoader(QThread):
    loaded = pyqtSignal(list)
    def run(self):
        try:
            voices = asyncio.run(_edge_list_voices_async())
            self.loaded.emit(voices)
        except Exception:
            self.loaded.emit([])

# ══════════════════════════════════════════════════════════════════════
# СТРАНИЦА
# ══════════════════════════════════════════════════════════════════════
class TypewriterPage(BasePage):
    PAGE_ICON  = "🎬"
    PAGE_TITLE = "Генератор видео"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_color    = DEFAULT_BG
        self._text_color  = DEFAULT_FG
        self._save_dir    = str(Path.home())
        self._speaker_wav: Optional[str] = None
        self._bg_video:   Optional[str] = None
        self._edge_voices_raw: list = []
        self._worker:    Optional[RenderWorker] = None
        self._build_ui()
        self.setStyleSheet(PAGE_QSS)
        self._load_edge_voices()

    # ── Build UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        self.setObjectName("tw_page")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar
        root.addWidget(self._build_toolbar())

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #171614; border: none; }"
                             "QScrollBar:vertical { background: #1c1b19; width: 8px; }"
                             "QScrollBar::handle:vertical { background: #2d2c2a; border-radius: 4px; }"
                             "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")

        content = QWidget()
        content.setObjectName("tw_page")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 24)
        cl.setSpacing(16)

        cl.addWidget(self._build_text_section())
        cl.addWidget(self._build_engine_section())
        cl.addWidget(self._build_video_section())
        cl.addWidget(self._build_text_style_section())
        cl.addWidget(self._build_output_section())
        cl.addWidget(self._build_generate_section())
        cl.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("tw_toolbar")
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 0, 24, 0)

        title = QLabel("🎬  Генератор видео")
        title.setObjectName("tw_heading")
        lay.addWidget(title)
        lay.addSpacing(12)

        sub = QLabel("Typewriter Effect · TTS · BG Video · HD Export")
        sub.setObjectName("tw_sub")
        lay.addWidget(sub)
        lay.addStretch()

        if not RENDER_AVAILABLE:
            warn = QLabel("⚠ Зависимости не установлены")
            warn.setObjectName("tw_badge_warn")
            lay.addWidget(warn)

        return bar

    def _section(self, title: str, icon: str = "") -> tuple:
        """Возвращает (section_frame, body_layout)."""
        frame = QFrame()
        frame.setObjectName("tw_section")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)

        hdr = QFrame()
        hdr.setObjectName("tw_section_header")
        hdr.setFixedHeight(40)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel(f"{icon}  {title}" if icon else title)
        lbl.setObjectName("tw_section_title")
        hl.addWidget(lbl)
        fl.addWidget(hdr)

        body = QWidget()
        body.setObjectName("tw_page")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 16)
        bl.setSpacing(10)
        fl.addWidget(body)

        return frame, bl

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName("tw_label")
        return l

    def _hint(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName("tw_hint")
        return l

    # ── Секция: Текст ─────────────────────────────────────────────────
    def _build_text_section(self) -> QFrame:
        frame, bl = self._section("Текст для озвучки", "📝")

        self.text_input = QTextEdit()
        self.text_input.setObjectName("tw_text_input")
        self.text_input.setPlaceholderText("Введите текст, который будет напечатан на видео и озвучен...")
        self.text_input.setMinimumHeight(120)
        self.text_input.setMaximumHeight(200)
        bl.addWidget(self.text_input)

        bl.addWidget(self._hint("Текст будет напечатан с эффектом печатной машинки и синхронизирован с голосом"))
        return frame

    # ── Секция: Движок TTS ────────────────────────────────────────────
    def _build_engine_section(self) -> QFrame:
        frame, bl = self._section("Голос и движок TTS", "🔊")

        # Выбор движка
        eng_row = QHBoxLayout()
        eng_row.setSpacing(8)
        eng_row.addWidget(self._lbl("Движок:"))
        self.engine_combo = QComboBox()
        self.engine_combo.setObjectName("tw_combo")
        engines = [ENGINE_EDGE]
        if XTTS_AVAILABLE:
            engines.append(ENGINE_XTTS)
        self.engine_combo.addItems(engines)
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)
        eng_row.addWidget(self.engine_combo)
        eng_row.addStretch()
        bl.addLayout(eng_row)

        # Edge TTS блок
        self.edge_widget = QWidget()
        self.edge_widget.setObjectName("tw_page")
        ew = QVBoxLayout(self.edge_widget)
        ew.setContentsMargins(0, 0, 0, 0)
        ew.setSpacing(8)

        lang_row = QHBoxLayout()
        lang_row.addWidget(self._lbl("Язык фильтр:"))
        self.edge_lang_combo = QComboBox()
        self.edge_lang_combo.setObjectName("tw_combo")
        self.edge_lang_combo.addItems(list(EDGE_LANG_FILTER.keys()))
        self.edge_lang_combo.currentTextChanged.connect(self._filter_edge_voices)
        lang_row.addWidget(self.edge_lang_combo)
        lang_row.addStretch()
        ew.addLayout(lang_row)

        voice_row = QHBoxLayout()
        voice_row.addWidget(self._lbl("Голос:"))
        self.edge_voice_combo = QComboBox()
        self.edge_voice_combo.setObjectName("tw_combo")
        self.edge_voice_combo.setMinimumWidth(260)
        voice_row.addWidget(self.edge_voice_combo)
        self.edge_loading_lbl = QLabel("⏳ Загрузка голосов...")
        self.edge_loading_lbl.setObjectName("tw_hint")
        voice_row.addWidget(self.edge_loading_lbl)
        voice_row.addStretch()
        ew.addLayout(voice_row)

        bl.addWidget(self.edge_widget)

        # XTTS блок
        self.xtts_widget = QWidget()
        self.xtts_widget.setObjectName("tw_page")
        xw = QVBoxLayout(self.xtts_widget)
        xw.setContentsMargins(0, 0, 0, 0)
        xw.setSpacing(8)

        lang_row2 = QHBoxLayout()
        lang_row2.addWidget(self._lbl("Язык:"))
        self.xtts_lang_combo = QComboBox()
        self.xtts_lang_combo.setObjectName("tw_combo")
        self.xtts_lang_combo.addItems(list(XTTS_LANGUAGES.keys()))
        lang_row2.addWidget(self.xtts_lang_combo)
        lang_row2.addStretch()
        xw.addLayout(lang_row2)

        spkr_row = QHBoxLayout()
        spkr_row.addWidget(self._lbl("Диктор:"))
        self.xtts_speaker_combo = QComboBox()
        self.xtts_speaker_combo.setObjectName("tw_combo")
        self.xtts_speaker_combo.addItems(XTTS_SPEAKERS)
        spkr_row.addWidget(self.xtts_speaker_combo)
        spkr_row.addStretch()
        xw.addLayout(spkr_row)

        clone_row = QHBoxLayout()
        self.clone_check = QCheckBox("Клонировать голос из WAV файла")
        self.clone_check.setObjectName("tw_check")
        self.clone_check.toggled.connect(self._on_clone_toggled)
        clone_row.addWidget(self.clone_check)
        clone_row.addStretch()
        xw.addLayout(clone_row)

        self.wav_widget = QWidget()
        ww = QHBoxLayout(self.wav_widget)
        ww.setContentsMargins(0, 0, 0, 0)
        pick_wav = QPushButton("📂 Выбрать WAV")
        pick_wav.setObjectName("btn_secondary")
        pick_wav.clicked.connect(self._pick_wav)
        ww.addWidget(pick_wav)
        self.wav_lbl = QLabel("не выбран")
        self.wav_lbl.setObjectName("tw_hint")
        ww.addWidget(self.wav_lbl)
        ww.addStretch()
        self.wav_widget.setVisible(False)
        xw.addWidget(self.wav_widget)

        bl.addWidget(self.xtts_widget)
        self.xtts_widget.setVisible(False)
        return frame

    # ── Секция: Видео настройки ────────────────────────────────────────
    def _build_video_section(self) -> QFrame:
        frame, bl = self._section("Видео и фон", "🎬")

        # Разрешение
        res_row = QHBoxLayout()
        res_row.addWidget(self._lbl("Разрешение:"))
        self.res_combo = QComboBox()
        self.res_combo.setObjectName("tw_combo")
        self.res_combo.addItems(list(RESOLUTIONS.keys()))
        self.res_combo.setCurrentIndex(1)
        res_row.addWidget(self.res_combo)
        res_row.addStretch()
        bl.addLayout(res_row)

        # Видео-фон
        bg_row = QHBoxLayout()
        self.use_bg_video = QCheckBox("Видео-фон (mp4/avi/mov)")
        self.use_bg_video.setObjectName("tw_check")
        self.use_bg_video.toggled.connect(self._on_bg_video_toggled)
        bg_row.addWidget(self.use_bg_video)
        if not CV2_AVAILABLE:
            bg_row.addWidget(self._hint("  ⚠ pip install opencv-python"))
        bg_row.addStretch()
        bl.addLayout(bg_row)

        self.bg_video_widget = QWidget()
        bgvw = QHBoxLayout(self.bg_video_widget)
        bgvw.setContentsMargins(0, 0, 0, 0)
        pick_bg = QPushButton("📂 Выбрать видео")
        pick_bg.setObjectName("btn_secondary")
        pick_bg.clicked.connect(self._pick_bg_video)
        bgvw.addWidget(pick_bg)
        self.bg_video_lbl = QLabel("файл не выбран")
        self.bg_video_lbl.setObjectName("tw_hint")
        bgvw.addWidget(self.bg_video_lbl)
        clear_bg = QPushButton("✖")
        clear_bg.setObjectName("btn_secondary")
        clear_bg.setFixedWidth(32)
        clear_bg.clicked.connect(self._clear_bg_video)
        bgvw.addWidget(clear_bg)
        bgvw.addStretch()
        self.bg_video_widget.setVisible(False)
        bl.addWidget(self.bg_video_widget)

        return frame

    # ── Секция: Стиль текста ──────────────────────────────────────────
    def _build_text_style_section(self) -> QFrame:
        frame, bl = self._section("Стиль текста и анимация", "✏️")

        # Скорость + шрифт
        row1 = QHBoxLayout()
        row1.setSpacing(20)

        # Скорость печати
        speed_col = QVBoxLayout()
        speed_col.addWidget(self._lbl("Скорость печати:"))
        self.speed_combo = QComboBox()
        self.speed_combo.setObjectName("tw_combo")
        self.speed_combo.addItems(list(SPEED_MAP.keys()))
        self.speed_combo.setCurrentIndex(1)
        speed_col.addWidget(self.speed_combo)
        row1.addLayout(speed_col)

        # Размер шрифта
        font_col = QVBoxLayout()
        font_lbl_row = QHBoxLayout()
        font_lbl_row.addWidget(self._lbl("Размер шрифта:"))
        self.font_size_val_lbl = QLabel("56 px")
        self.font_size_val_lbl.setObjectName("tw_label")
        font_lbl_row.addWidget(self.font_size_val_lbl)
        font_lbl_row.addStretch()
        font_col.addLayout(font_lbl_row)
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setObjectName("tw_slider")
        self.font_size_slider.setRange(24, 120)
        self.font_size_slider.setValue(56)
        self.font_size_slider.valueChanged.connect(
            lambda v: self.font_size_val_lbl.setText(f"{v} px"))
        self.font_size_slider.setMinimumWidth(180)
        font_col.addWidget(self.font_size_slider)
        row1.addLayout(font_col)
        row1.addStretch()
        bl.addLayout(row1)

        # Цвета
        color_row = QHBoxLayout()
        color_row.setSpacing(12)
        color_row.addWidget(self._lbl("Цвета:"))

        self.bg_color_preview = QLabel()
        self.bg_color_preview.setObjectName("tw_color_preview")
        self.bg_color_preview.setStyleSheet(f"background: {self._bg_color}; border-radius: 6px; border: 1px solid #393836;")
        color_row.addWidget(self.bg_color_preview)
        btn_bg = QPushButton("⬛ Фон")
        btn_bg.setObjectName("btn_secondary")
        btn_bg.clicked.connect(self._pick_bg_color)
        color_row.addWidget(btn_bg)

        self.text_color_preview = QLabel()
        self.text_color_preview.setObjectName("tw_color_preview")
        self.text_color_preview.setStyleSheet(f"background: {self._text_color}; border-radius: 6px; border: 1px solid #393836;")
        color_row.addWidget(self.text_color_preview)
        btn_fg = QPushButton("⬜ Текст")
        btn_fg.setObjectName("btn_secondary")
        btn_fg.clicked.connect(self._pick_text_color)
        color_row.addWidget(btn_fg)
        color_row.addStretch()
        bl.addLayout(color_row)

        # Режим переполнения
        bl.addWidget(self._lbl("Режим при заполнении экрана:"))
        self.overflow_group = QButtonGroup(self)
        for i, (val, desc) in enumerate([
            (OVERFLOW_NONE,   "Обычный — авто-уменьшение шрифта"),
            (OVERFLOW_CLEAR,  "Сброс — очистить и начать сначала"),
            (OVERFLOW_SCROLL, "Прокрутка — текст уезжает вверх (телесуфлёр)"),
        ]):
            rb = QRadioButton(f"{val}  —  {desc}")
            rb.setObjectName("tw_radio")
            rb.setProperty("overflow_val", val)
            if i == 0: rb.setChecked(True)
            self.overflow_group.addButton(rb, i)
            bl.addWidget(rb)

        # Режим отображения текста
        bl.addWidget(self._lbl("Режим отображения:"))
        self.textmode_group = QButtonGroup(self)
        for i, (val, lbl, desc) in enumerate([
            (TEXTMODE_NORMAL,   "📝 Обычный",    "позиция и выравнивание как настроено"),
            (TEXTMODE_SUBTITLE, "📺 Субтитры",   "текст внизу на полупрозрачной подложке"),
            (TEXTMODE_NOTEXT,   "🔇 Без текста", "только озвучка, текст не рисуется"),
        ]):
            rb = QRadioButton(f"{lbl}  —  {desc}")
            rb.setObjectName("tw_radio")
            rb.setProperty("textmode_val", val)
            if i == 0: rb.setChecked(True)
            self.textmode_group.addButton(rb, i)
            bl.addWidget(rb)

        # Выравнивание
        align_row = QHBoxLayout()
        align_row.setSpacing(20)

        halign_col = QVBoxLayout()
        halign_col.addWidget(self._lbl("По горизонтали:"))
        self.halign_group = QButtonGroup(self)
        for i, val in enumerate([HALIGN_LEFT, HALIGN_CENTER, HALIGN_RIGHT]):
            rb = QRadioButton(val)
            rb.setObjectName("tw_radio")
            rb.setProperty("halign_val", val)
            if i == 1: rb.setChecked(True)
            self.halign_group.addButton(rb, i)
            halign_col.addWidget(rb)
        align_row.addLayout(halign_col)

        valign_col = QVBoxLayout()
        valign_col.addWidget(self._lbl("По вертикали:"))
        self.valign_group = QButtonGroup(self)
        for i, val in enumerate([VALIGN_TOP, VALIGN_CENTER, VALIGN_BOTTOM]):
            rb = QRadioButton(val)
            rb.setObjectName("tw_radio")
            rb.setProperty("valign_val", val)
            if i == 1: rb.setChecked(True)
            self.valign_group.addButton(rb, i)
            valign_col.addWidget(rb)
        align_row.addLayout(valign_col)

        padding_col = QVBoxLayout()
        pad_lbl_row = QHBoxLayout()
        pad_lbl_row.addWidget(self._lbl("Отступ от краёв:"))
        self.padding_val_lbl = QLabel("Авто")
        self.padding_val_lbl.setObjectName("tw_label")
        pad_lbl_row.addWidget(self.padding_val_lbl)
        pad_lbl_row.addStretch()
        padding_col.addLayout(pad_lbl_row)
        self.padding_slider = QSlider(Qt.Orientation.Horizontal)
        self.padding_slider.setObjectName("tw_slider")
        self.padding_slider.setRange(0, 300)
        self.padding_slider.setValue(0)
        self.padding_slider.valueChanged.connect(
            lambda v: self.padding_val_lbl.setText("Авто" if v == 0 else f"{v} px"))
        self.padding_slider.setMinimumWidth(160)
        padding_col.addWidget(self.padding_slider)
        padding_col.addWidget(self._hint("0 = авто"))
        align_row.addLayout(padding_col)
        align_row.addStretch()
        bl.addLayout(align_row)

        return frame

    # ── Секция: Вывод ─────────────────────────────────────────────────
    def _build_output_section(self) -> QFrame:
        frame, bl = self._section("Куда сохранить", "💾")

        out_row = QHBoxLayout()
        out_row.addWidget(self._lbl("Папка:"))
        self.save_dir_lbl = QLabel(self._save_dir)
        self.save_dir_lbl.setObjectName("tw_hint")
        self.save_dir_lbl.setWordWrap(True)
        out_row.addWidget(self.save_dir_lbl, stretch=1)
        pick_dir = QPushButton("📂 Изменить")
        pick_dir.setObjectName("btn_secondary")
        pick_dir.clicked.connect(self._pick_save_dir)
        out_row.addWidget(pick_dir)
        bl.addLayout(out_row)

        fname_row = QHBoxLayout()
        fname_row.addWidget(self._lbl("Имя файла:"))
        self.filename_input = QLineEdit("output.mp4")
        self.filename_input.setObjectName("tw_field")
        self.filename_input.setMaximumWidth(260)
        fname_row.addWidget(self.filename_input)
        fname_row.addStretch()
        bl.addLayout(fname_row)

        return frame

    # ── Секция: Генерация ─────────────────────────────────────────────
    def _build_generate_section(self) -> QFrame:
        frame, bl = self._section("Генерация", "▶")

        self.generate_btn = QPushButton("🎬  Сгенерировать видео")
        self.generate_btn.setObjectName("btn_generate")
        self.generate_btn.clicked.connect(self._on_generate)
        bl.addWidget(self.generate_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("tw_progress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        bl.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("tw_hint")
        bl.addWidget(self.status_lbl)

        self.log_output = QTextEdit()
        self.log_output.setObjectName("tw_log")
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(140)
        self.log_output.setVisible(False)
        bl.addWidget(self.log_output)

        return frame

    # ── Логика ────────────────────────────────────────────────────────
    def _load_edge_voices(self):
        if not EDGE_AVAILABLE:
            self.edge_loading_lbl.setText("⚠ pip install edge-tts")
            return
        self.edge_loading_lbl.setText("⏳ Загрузка голосов...")
        self._voice_loader = EdgeVoiceLoader()
        self._voice_loader.loaded.connect(self._on_voices_loaded)
        self._voice_loader.start()

    def _on_voices_loaded(self, voices: list):
        self._edge_voices_raw = voices
        self.edge_loading_lbl.setText(f"✅ {len(voices)} голосов")
        self._filter_edge_voices()

    def _filter_edge_voices(self):
        lang_key = self.edge_lang_combo.currentText()
        prefix   = EDGE_LANG_FILTER.get(lang_key)
        filtered = [
            v["ShortName"] for v in self._edge_voices_raw
            if prefix is None or v.get("Locale", "").startswith(prefix)
        ]
        self.edge_voice_combo.clear()
        self.edge_voice_combo.addItems(filtered if filtered else ["ru-RU-SvetlanaNeural"])

    def _on_engine_changed(self, eng: str):
        is_xtts = (eng == ENGINE_XTTS)
        self.edge_widget.setVisible(not is_xtts)
        self.xtts_widget.setVisible(is_xtts)

    def _on_clone_toggled(self, checked: bool):
        self.wav_widget.setVisible(checked)
        self.xtts_speaker_combo.setEnabled(not checked)

    def _on_bg_video_toggled(self, checked: bool):
        self.bg_video_widget.setVisible(checked)

    def _pick_wav(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать WAV", "", "Audio (*.wav)")
        if path:
            self._speaker_wav = path
            self.wav_lbl.setText(os.path.basename(path))

    def _pick_bg_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать видео-фон", "", "Video (*.mp4 *.avi *.mov *.mkv)")
        if path:
            self._bg_video = path
            self.bg_video_lbl.setText(os.path.basename(path))

    def _clear_bg_video(self):
        self._bg_video = None
        self.bg_video_lbl.setText("файл не выбран")

    def _pick_bg_color(self):
        c = QColorDialog.getColor(QColor(self._bg_color), self, "Цвет фона")
        if c.isValid():
            self._bg_color = c.name()
            self.bg_color_preview.setStyleSheet(
                f"background: {self._bg_color}; border-radius: 6px; border: 1px solid #393836;")

    def _pick_text_color(self):
        c = QColorDialog.getColor(QColor(self._text_color), self, "Цвет текста")
        if c.isValid():
            self._text_color = c.name()
            self.text_color_preview.setStyleSheet(
                f"background: {self._text_color}; border-radius: 6px; border: 1px solid #393836;")

    def _pick_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Выбрать папку", self._save_dir)
        if d:
            self._save_dir = d
            self.save_dir_lbl.setText(d)

    def _get_overflow_mode(self) -> str:
        btn = self.overflow_group.checkedButton()
        return btn.property("overflow_val") if btn else OVERFLOW_NONE

    def _get_textmode(self) -> str:
        btn = self.textmode_group.checkedButton()
        return btn.property("textmode_val") if btn else TEXTMODE_NORMAL

    def _get_halign(self) -> str:
        btn = self.halign_group.checkedButton()
        return btn.property("halign_val") if btn else HALIGN_CENTER

    def _get_valign(self) -> str:
        btn = self.valign_group.checkedButton()
        return btn.property("valign_val") if btn else VALIGN_CENTER

    def _on_generate(self):
        if not RENDER_AVAILABLE:
            self.log_output.setVisible(True)
            self.log_output.append(
                f"❌ Зависимости не установлены:\n{RENDER_ERROR}\n\n"
                "Выполни: pip install Pillow numpy moviepy\n"
                "Для видео-фона: pip install opencv-python\n"
                "Для Edge TTS:   pip install edge-tts\n"
                "Для XTTS v2:    pip install torch torchaudio coqui-tts"
            )
            return

        text = self.text_input.toPlainText().strip()
        if not text:
            self.status_lbl.setText("⚠ Введите текст!")
            return

        eng = self.engine_combo.currentText()
        if eng == ENGINE_EDGE and not EDGE_AVAILABLE:
            self.status_lbl.setText("⚠ edge-tts не установлен: pip install edge-tts")
            return

        edge_voice = self.edge_voice_combo.currentText() if self.edge_voice_combo.count() else "ru-RU-SvetlanaNeural"
        res_key    = self.res_combo.currentText()
        width, height = RESOLUTIONS.get(res_key, (1280, 720))
        textmode   = self._get_textmode()
        overflow   = self._get_overflow_mode()

        params = {
            "text":          text,
            "engine":        eng,
            "xtts_lang":     XTTS_LANGUAGES.get(self.xtts_lang_combo.currentText(), "ru"),
            "xtts_speaker":  self.xtts_speaker_combo.currentText(),
            "speaker_wav":   self._speaker_wav,
            "edge_voice":    edge_voice,
            "width":         width,
            "height":        height,
            "font_size":     self.font_size_slider.value(),
            "bg_color":      self._bg_color,
            "text_color":    self._text_color,
            "chars_per_sec": SPEED_MAP.get(self.speed_combo.currentText(), 15),
            "overflow_mode": overflow,
            "bg_video_path": self._bg_video if self.use_bg_video.isChecked() else None,
            "text_halign":   self._get_halign(),
            "text_valign":   self._get_valign(),
            "text_padding":  self.padding_slider.value(),
            "subtitle_mode": textmode == TEXTMODE_SUBTITLE,
            "no_text":       textmode == TEXTMODE_NOTEXT,
            "save_dir":      self._save_dir,
            "filename":      self.filename_input.text() or "output.mp4",
        }

        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log_output.setVisible(True)
        self.log_output.clear()
        self.status_lbl.setText("⏳ Генерация...")

        self._worker = RenderWorker(params)
        self._worker.status_update.connect(self._on_status)
        self._worker.progress_update.connect(self.progress_bar.setValue)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_status(self, msg: str):
        self.status_lbl.setText(msg)
        self.log_output.append(msg)

    def _on_done(self, path: str):
        self.generate_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.status_lbl.setText(f"✅ Сохранено: {path}")
        self.log_output.append(f"\n✅ Видео сохранено:\n{path}")
        self._worker = None

    def _on_error(self, err: str):
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_lbl.setText("❌ Ошибка!")
        self.log_output.append(f"\n❌ ОШИБКА:\n{err}")
        self._worker = None
