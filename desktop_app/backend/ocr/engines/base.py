from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class EngineResult:
    fields: dict[str, str]
    raw_text: str
    source: str


class BaseOCREngine:
    key = "base"
    display_name = "Base OCR"

    def available(self) -> bool:
        return True

    def recognize(self, image: np.ndarray) -> EngineResult | None:
        raise NotImplementedError
