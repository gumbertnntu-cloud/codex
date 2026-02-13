#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "[ERROR] .venv not found. Create it first: python3 -m venv .venv"
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -e .
python -m pip install pyinstaller

pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "TJR" \
  --osx-bundle-identifier "com.tjr.desktop" \
  --paths "src" \
  "src/tjr/__main__.py"

APP_PATH="$ROOT_DIR/dist/TJR.app"
if [[ -d "$APP_PATH" ]]; then
  echo "[OK] App built: $APP_PATH"
else
  echo "[ERROR] Build finished but app bundle not found"
  exit 1
fi
