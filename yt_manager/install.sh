#!/usr/bin/env bash
set -e

echo ""
echo " ╔══════════════════════════════════════╗"
echo " ║      YT Manager — Установка          ║"
echo " ╚══════════════════════════════════════╝"
echo ""

# Python
if ! command -v python3 &>/dev/null; then
    echo " [ОШИБКА] python3 не найден."
    echo " Установи Python 3.10+ через менеджер пакетов:"
    echo "   Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "   macOS:         brew install python"
    exit 1
fi

PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
echo " [OK] Python $PY_VER"

# Проверка минимальной версии
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo " [ОШИБКА] Требуется Python 3.10+, установлена $PY_VER"
    exit 1
fi

# Виртуальное окружение
if [ ! -d ".venv" ]; then
    echo " Создаю виртуальное окружение..."
    python3 -m venv .venv
    echo " [OK] Окружение .venv создано"
else
    echo " [OK] Окружение .venv уже существует"
fi

# Активируем
# shellcheck disable=SC1091
source .venv/bin/activate

# Зависимости
echo " Устанавливаю зависимости..."
pip install --upgrade pip --quiet
pip install -r requirements.txt
echo " [OK] Зависимости установлены"

# ffmpeg
if command -v ffmpeg &>/dev/null; then
    FFMPEG_VER=$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')
    echo " [OK] ffmpeg $FFMPEG_VER"
else
    echo ""
    echo " [ПРЕДУПРЕЖДЕНИЕ] ffmpeg не найден."
    echo " Нарезка и склейка недоступны."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "   Установи: brew install ffmpeg"
    else
        echo "   Ubuntu/Debian: sudo apt install ffmpeg"
        echo "   Fedora/RHEL:   sudo dnf install ffmpeg"
    fi
fi

# yt-dlp
if command -v yt-dlp &>/dev/null; then
    YTDLP_VER=$(yt-dlp --version 2>/dev/null || echo "установлен")
    echo " [OK] yt-dlp $YTDLP_VER"
else
    python3 -c "import yt_dlp" 2>/dev/null && echo " [OK] yt-dlp (Python-модуль)" || true
fi

# Права на run.sh
chmod +x run.sh 2>/dev/null || true

echo ""
echo " ══════════════════════════════════════"
echo " Установка завершена!"
echo " Запусти приложение:  ./run.sh"
echo " ══════════════════════════════════════"
echo ""
