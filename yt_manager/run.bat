@echo off
chcp 65001 > nul
title YT Manager

:: Переходим в папку самого скрипта (независимо от того, откуда запущен)
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo  Виртуальное окружение не найдено.
    echo  Сначала запусти install.bat
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python main.py %*
