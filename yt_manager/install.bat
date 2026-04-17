@echo off
chcp 65001 >nul
echo ============================================
echo  YT Manager — Установка зависимостей
echo ============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден! Установите Python 3.10+
    pause
    exit /b 1
)

echo [1/3] Установка основных зависимостей...
pip install PyQt6 PyQt6-Qt6 yt-dlp ffmpeg-python Pillow requests python-dateutil

echo.
echo [2/3] Установка зависимостей Typewriter Video Generator...
pip install "numpy>=1.24.0" "moviepy==1.0.3" "edge-tts>=6.1.0"

echo.
echo [3/3] Установка OpenCV (видео-фон, опционально)...
pip install opencv-python

echo.
echo ============================================
echo  Установка завершена!
echo  Для запуска: run.bat
echo.
echo  [Опционально] XTTS v2 локальный TTS (~2 ГБ):
echo  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
echo  pip install coqui-tts
echo ============================================
pause
