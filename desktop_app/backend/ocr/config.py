from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from desktop_app.backend.paths import resource_root


@dataclass(frozen=True)
class OCRConfig:
    engine_order: tuple[str, ...]
    chandra_api_url: str
    paddle_model_dir: Path
    paddle_confidence: float

    @classmethod
    def from_environment(cls) -> "OCRConfig":
        order = tuple(
            item.strip().casefold()
            for item in os.getenv("CCCD_OCR_ENGINE_ORDER", "qr,chandra,paddle,tesseract").split(",")
            if item.strip()
        )
        configured_model = os.getenv("CCCD_PADDLE_MODEL_DIR", "").strip()
        model_dir = (
            Path(configured_model)
            if configured_model
            else resource_root() / "runtime_models" / "paddle"
        )
        try:
            confidence = float(os.getenv("CCCD_PADDLE_CONFIDENCE", "0.45"))
        except ValueError:
            confidence = 0.45
        return cls(
            engine_order=order,
            chandra_api_url=os.getenv("CCCD_OCR_API_URL", "").strip(),
            paddle_model_dir=model_dir,
            paddle_confidence=max(0.0, min(1.0, confidence)),
        )
