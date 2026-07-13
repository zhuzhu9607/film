#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV="$ROOT/.venv-macos"
APP_NAME="FilmStripCutter"
NATIVE_ARCH="$(uname -m)"
TARGET_ARCH="${TARGET_ARCH:-$NATIVE_ARCH}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This build must run on macOS."
    exit 1
fi

if [[ "$TARGET_ARCH" != "arm64" && "$TARGET_ARCH" != "x86_64" && "$TARGET_ARCH" != "universal2" ]]; then
    echo "TARGET_ARCH must be arm64, x86_64, or universal2."
    exit 1
fi

if [[ ! -x "$VENV/bin/python" ]]; then
    "$PYTHON_BIN" -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r requirements.txt
"$VENV/bin/python" tools/create_macos_icon.py

rm -rf "$ROOT/build/$APP_NAME" "$ROOT/dist/$APP_NAME.app"
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --windowed --onedir \
    --name "$APP_NAME" \
    --target-arch "$TARGET_ARCH" \
    --osx-bundle-identifier "com.local.filmstripcutter" \
    --icon "assets/filmstrip.icns" \
    --add-data "assets/filmstrip.icns:assets" \
    --collect-all rawpy --collect-all tifffile --collect-all imagecodecs \
    --hidden-import cv2 --hidden-import numpy \
    main.py

APP="$ROOT/dist/$APP_NAME.app"
SIGN_IDENTITY="${SIGN_IDENTITY:--}"
codesign --force --deep --sign "$SIGN_IDENTITY" "$APP"
codesign --verify --deep --strict "$APP"

DMG="$ROOT/dist/FilmStripCutter-macOS-$TARGET_ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "FilmStrip Cutter" -srcfolder "$APP" -ov -format UDZO "$DMG"

echo "Build complete: $APP"
echo "Disk image: $DMG"
