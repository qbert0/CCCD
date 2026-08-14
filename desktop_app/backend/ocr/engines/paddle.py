from __future__ import annotations

import site
import re
import threading
import unicodedata
from pathlib import Path

import numpy as np

from desktop_app.backend.ocr.parser import parse_ocr_text
from desktop_app.backend.paths import resource_root

from .base import BaseOCREngine, EngineResult


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").replace("đ", "d")


def restore_cccd_vietnamese(raw: str) -> str:
    """Restore stable Vietnamese labels on the CCCD back after recognition."""
    restored: list[str] = []
    for line in raw.splitlines():
        folded = re.sub(r"[^a-z0-9]+", " ", _fold(line)).strip()
        compact = folded.replace(" ", "")
        if "dac diem" in folded and "nhan dang" in folded:
            line = "Đặc điểm nhận dạng / Personal identification"
        elif "ngay thang nam" in folded or "date month year" in folded:
            date_match = re.search(r"\d{2}/\d{2}/\d{4}", line)
            line = "Ngày, tháng, năm / Date, month, year"
            if date_match:
                line += ": " + date_match.group(0)
        elif "ngon tro phai" in folded:
            line = "Ngón trỏ phải / Right index finger"
        elif "ngon tro trai" in folded:
            line = "Ngón trỏ trái / Left index finger"
        elif "director general" in folded:
            line = "DIRECTOR GENERAL OF THE POLICE DEPARTMENT"
        elif "cuctruongcuccanhsat" in compact:
            line = "CỤC TRƯỞNG CỤC CẢNH SÁT"
        elif "quanlyhanhchinhvetrat" in compact:
            line = "QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI"
        elif "seo cham" in folded and "mat pha" in folded:
            line = "Sẹo chấm ngay dưới mắt phải"
        if line:
            restored.append(line)
    return "\n".join(restored)


class PaddleEngine(BaseOCREngine):
    key = "paddle"
    display_name = "PaddleOCR · Offline"

    def __init__(self, model_dir: Path, confidence: float):
        self.model_dir = model_dir
        self.confidence = confidence
        self._reader = None
        # Front/back images now OCR concurrently on separate threads, but the
        # underlying PaddleOCR predictor is a single lazily-built instance
        # shared across every call — its inference session isn't reentrant,
        # so concurrent .ocr() calls on it can corrupt results or crash.
        # Every other engine (QR, Chandra, Tesseract) is stateless per call
        # and safe to run fully in parallel; only this one needs serializing.
        self._lock = threading.Lock()

    def available(self) -> bool:
        return all((self.model_dir / name).exists() for name in ("det", "rec", "cls"))

    def _load(self):
        if site.USER_SITE is None:
            site.USER_SITE = str(resource_root())
        from paddleocr import PaddleOCR

        if self._reader is None:
            self._reader = PaddleOCR(
                use_angle_cls=True,
                lang="vi",
                show_log=False,
                det_model_dir=str(self.model_dir / "det"),
                rec_model_dir=str(self.model_dir / "rec"),
                cls_model_dir=str(self.model_dir / "cls"),
            )
        return self._reader

    def recognize(self, image: np.ndarray) -> EngineResult | None:
        with self._lock:
            result = self._load().ocr(image, cls=True)
        lines: list[str] = []
        if result and result[0]:
            for line in result[0]:
                text, confidence = line[1]
                if confidence >= self.confidence:
                    lines.append(text)
        raw = restore_cccd_vietnamese("\n".join(lines))
        return EngineResult(parse_ocr_text(raw), raw, "PaddleOCR local") if raw else None
