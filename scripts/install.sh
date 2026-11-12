#!/usr/bin/env bash
# Встановити Board Studio у теку розширень IngeTrazo.
#   ./scripts/install.sh          — симлінк (для розробки: зміни видно після перезапуску)
#   ./scripts/install.sh --copy   — копія
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)/board_studio"
if [ -d "$HOME/.var/app/com.ingetrazo.IngeTrazo" ]; then
  DEST="$HOME/.var/app/com.ingetrazo.IngeTrazo/data/ingetrazo/plugins"   # flatpak
else
  DEST="${XDG_DATA_HOME:-$HOME/.local/share}/ingetrazo/plugins"
fi
mkdir -p "$DEST"
rm -rf "$DEST/board_studio"
if [ "${1:-}" = "--copy" ]; then
  cp -r "$SRC" "$DEST/board_studio"
  find "$DEST/board_studio" -name __pycache__ -prune -exec rm -rf {} +
else
  ln -s "$SRC" "$DEST/board_studio"
fi
echo "Installed to $DEST/board_studio — restart IngeTrazo."
