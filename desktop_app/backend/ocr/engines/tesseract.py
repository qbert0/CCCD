from __future__ import annotations

import subprocess
import sys
import tempfile

import cv2
import numpy as np

from desktop_app.backend.ocr.parser import parse_ocr_text

from .base import BaseOCREngine, EngineResult

# subprocess.run() on Windows spawns a new visible console window for a
# console-subsystem child (tesseract.exe is one) whenever the parent
# process itself has none -- true here, since the app's own EXE is built
# with console=False (see CCCDReportApp.spec's EXE(...)).
_NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class TesseractEngine(BaseOCREngine):
    key = "tesseract"
    display_name = "Tesseract · Fallback"

    def available(self) -> bool:
        try:
            subprocess.run(
                ["tesseract", "--version"], capture_output=True, timeout=5, check=False,
                creationflags=_NO_WINDOW_FLAGS,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
        return True

    def recognize(self, image: np.ndarray) -> EngineResult | None:
        languages = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10, check=False,
            creationflags=_NO_WINDOW_FLAGS,
        ).stdout
        language = "vie+eng" if "vie" in languages.split() else "eng"
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            cv2.imwrite(image_file.name, image)
            process = subprocess.run(
                ["tesseract", image_file.name, "stdout", "-l", language, "--psm", "6"],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
                creationflags=_NO_WINDOW_FLAGS,
            )
        raw = process.stdout.strip()
        if not raw:
            return None
        return EngineResult(parse_ocr_text(raw), raw, f"Tesseract {language}")
