#!/usr/bin/env bash
# Запуск тестів Python-ом IngeTrazo (flatpak), без вікна.
set -euo pipefail
cd "$(dirname "$0")/.."
exec flatpak run --command=python3 \
  --env=QT_QPA_PLATFORM=offscreen \
  com.ingetrazo.IngeTrazo -I "$PWD/tests/test_board_studio.py"
