@echo off
chcp 65001 > nul
title YT Manager — Установка

echo.
echo  ╔══════════════════════════════════════╗
echo  ║      YT Manager — Установка          ║
echo  ╚══════════════════════════════════════╝
echo.

:: Проверяем Python
where python > nul 2>&1
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Python не найден в PATH.
    echo  Скачай Python 3.10+ с https://python.org
    echo  При установке обязательно включи "Add Python to PATH"
    pause
    exit /b 1
)

:: Версия Python
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PY_VER=%%V
echo  [OK] Python %PY_VER%

:: Создаём виртуальное окружение
if not exist ".venv\" (
    echo  Создаю виртуальное окружение...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [ОШИБКА] Не удалось создать venv.
        pause
        exit /b 1
    )
    echo  [OK] Окружение .venv создано
) else (
    echo  [OK] Окружение .venv уже существует
)

:: Активируем и устанавливаем зависимости
echo  Устанавливаю зависимости...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Ошибка при установке зависимостей.
    pause
    exit /b 1
)

:: Проверяем ffmpeg
where ffmpeg > nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] ffmpeg найден
) else (
    echo.
    echo  [ПРЕДУПРЕЖДЕНИЕ] ffmpeg не найден.
    echo  Нарезка и склейка видео будут недоступны.
    echo  Установи ffmpeg: https://ffmpeg.org/download.html
    echo  Затем добавь папку bin\ в системный PATH.
)

:: Проверяем yt-dlp
where yt-dlp > nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] yt-dlp найден
) else (
    :: yt-dlp может быть установлен как Python-модуль
    python -c "import yt_dlp" > nul 2>&1
    if %errorlevel% equ 0 (
        echo  [OK] yt-dlp ^(Python-модуль^)
    ) else (
        echo  [OK] yt-dlp установлен как пакет pip
    )
)

echo.
echo  ══════════════════════════════════════
echo  Установка завершена!
echo  Запусти приложение командой:  run.bat
echo  ══════════════════════════════════════
echo.
pause
