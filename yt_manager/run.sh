#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".venv/bin/activate" ]; then
    echo " Виртуальное окружение не найдено."
    echo " Запусти сначала:  ./install.sh"
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python main.py "$@"
