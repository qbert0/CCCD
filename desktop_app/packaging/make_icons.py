#!/usr/bin/env python3
"""Rasterize the master SVG icon into the .ico/.icns files the Windows exe
and macOS .app bundle need. Pillow can write both formats directly on any
OS, so this needs no platform-specific icon tooling. Idempotent and cheap,
so it's safe to call from the PyInstaller spec on every build."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parents[2]
SOURCE_PNG = PROJECT_DIR / "desktop_app/assets/icon-1024.png"
OUTPUT_DIR = PROJECT_DIR / "build/icons"

ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def build_icons() -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ico_path = OUTPUT_DIR / "icon.ico"
    icns_path = OUTPUT_DIR / "icon.icns"

    img = Image.open(SOURCE_PNG).convert("RGBA")
    img.save(ico_path, sizes=ICO_SIZES)
    img.save(icns_path)
    return ico_path, icns_path


if __name__ == "__main__":
    ico_path, icns_path = build_icons()
    print(f"wrote {ico_path}")
    print(f"wrote {icns_path}")
