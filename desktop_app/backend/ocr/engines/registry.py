from __future__ import annotations

from collections.abc import Callable

import numpy as np

from desktop_app.backend.ocr.config import OCRConfig

from .base import BaseOCREngine, EngineResult
from .chandra import ChandraAPIEngine
from .paddle import PaddleEngine
from .qr import QREngine
from .tesseract import TesseractEngine


class OCREngineRegistry:
    """Single place to register, order, enable and inspect every OCR engine."""

    def __init__(self, config: OCRConfig | None = None):
        self.config = config or OCRConfig.from_environment()
        engines: list[BaseOCREngine] = [
            QREngine(),
            ChandraAPIEngine(self.config.chandra_api_url),
            PaddleEngine(self.config.paddle_model_dir, self.config.paddle_confidence),
            TesseractEngine(),
        ]
        self._engines = {engine.key: engine for engine in engines}

    def ordered_engines(self) -> list[BaseOCREngine]:
        return [self._engines[key] for key in self.config.engine_order if key in self._engines]

    def status(self) -> list[dict[str, str | bool]]:
        return [
            {"key": engine.key, "name": engine.display_name, "available": engine.available()}
            for engine in self.ordered_engines()
        ]

    def recognize(
        self,
        image: np.ndarray,
        logger: Callable[[str, Exception | str], None] | None = None,
    ) -> EngineResult:
        errors: list[str] = []
        for engine in self.ordered_engines():
            if not engine.available():
                continue
            try:
                result = engine.recognize(image)
                if result is not None:
                    return result
            except Exception as exc:
                if logger:
                    logger(engine.display_name, exc)
                errors.append(f"{engine.display_name}: {exc}")
        raise RuntimeError("Không OCR được ảnh. " + " | ".join(errors))
