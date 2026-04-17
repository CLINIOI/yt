#!/bin/bash
echo "============================================"
echo " YT Manager — Установка зависимостей"
echo "============================================"

pip install PyQt6 PyQt6-Qt6 yt-dlp ffmpeg-python Pillow requests python-dateutil
pip install "numpy>=1.24.0" "moviepy==1.0.3" "edge-tts>=6.1.0"
pip install opencv-python

echo ""
echo "Установка завершена!"
echo "Запуск: bash run.sh"
echo ""
echo "[Опционально] XTTS v2 локальный TTS (~2 ГБ):"
echo "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu"
echo "pip install coqui-tts"
