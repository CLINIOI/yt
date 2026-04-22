@echo off
title YT Manager
echo.
echo  ========================================
echo   YT Manager - Starting...
echo  ========================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found!
    echo.
    echo  Download Python 3.10+ from:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: check "Add Python to PATH" during install!
    echo.
    pause
    exit /b 1
)

echo  Python found:
python --version
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo  First run - installing dependencies...
    echo  Please wait 2-5 minutes...
    echo.

    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )

    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip --quiet

    echo  Installing PyQt6 and core packages...
    pip install PyQt6 PyQt6-Qt6 yt-dlp ffmpeg-python Pillow requests python-dateutil
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to install dependencies!
        pause
        exit /b 1
    )

    echo  Installing moviepy and edge-tts...
    pip install "numpy>=1.24.0" "moviepy==1.0.3" "edge-tts>=6.1.0"

    echo  Installing opencv...
    pip install opencv-python

    echo.
    echo  ========================================
    echo   Done! Starting app...
    echo  ========================================
    echo.
) else (
    call .venv\Scripts\activate.bat
    echo  Environment found. Starting...
    echo.
)

python main.py %*

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] App crashed! Error code: %errorlevel%
    echo.
    pause
)
