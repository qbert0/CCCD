from __future__ import annotations

import subprocess
import tempfile

import cv2
import numpy as np

from desktop_app.backend.ocr.parser import parse_ocr_text

from .base import BaseOCREngine, EngineResult


class TesseractEngine(BaseOCREngine):
    key = "tesseract"
    display_name = "Tesseract · Fallback"

    def available(self) -> bool:
        try:
            subprocess.run(
                ["tesseract", "--version"], capture_output=True, timeout=5, check=False
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
        return True

    def recognize(self, image: np.ndarray) -> EngineResult | None:
        languages = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10, check=False
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
            )
        raw = process.stdout.strip()
        if not raw:
            return None
        return EngineResult(parse_ocr_text(raw), raw, f"Tesseract {language}")
