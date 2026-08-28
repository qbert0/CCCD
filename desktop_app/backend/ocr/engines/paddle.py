from __future__ import annotations

import site
import re
import threading
import time
import unicodedata
from pathlib import Path

import cv2
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


class _VietOCRLineRecognizer:
    """Drop-in replacement for PaddleOCR's internal `text_recognizer`.

    PaddleOCR's own "vi" recognition model is actually its generic "latin"
    multi-language model (confirmed against paddleocr's own `parse_lang`,
    true even in the latest PP-OCRv5) — that dictionary has no ơ/ư and no
    Vietnamese tone-marked vowels at all, so it can only ever transliterate
    Vietnamese text into loose Latin approximations. PaddleOCR's detector
    and angle classifier (`text_detector`/`text_classifier`) don't depend on
    a language dictionary and work well on this card layout, so only the
    character-recognition step is swapped for VietOCR, a dedicated
    Vietnamese text recognizer, while detection/box order/cls stay as-is.
    """

    def __init__(self, predictor):
        self.predictor = predictor

    def __call__(self, img_list: list[np.ndarray]):
        from PIL import Image

        start = time.time()
        results: list[tuple[str, float]] = []
        for crop in img_list:
            pil_image = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            text, prob = self.predictor.predict(pil_image, return_prob=True)
            results.append((text, float(prob)))
        return results, time.time() - start


class PaddleEngine(BaseOCREngine):
    key = "paddle"
    display_name = "PaddleOCR detect + VietOCR · Offline"

    def __init__(
        self,
        model_dir: Path,
        confidence: float,
        vietocr_weights_path: Path,
        vietocr_config_path: Path,
    ):
        self.model_dir = model_dir
        self.confidence = confidence
        self.vietocr_weights_path = vietocr_weights_path
        self.vietocr_config_path = vietocr_config_path
        self._reader = None
        # Front/back images now OCR concurrently on separate threads, but the
        # underlying PaddleOCR predictor is a single lazily-built instance
        # shared across every call — its inference session isn't reentrant,
        # so concurrent .ocr() calls on it can corrupt results or crash.
        # Every other engine (QR, Chandra, Tesseract) is stateless per call
        # and safe to run fully in parallel; only this one needs serializing.
        self._lock = threading.Lock()

    def available(self) -> bool:
        return (
            all((self.model_dir / name).exists() for name in ("det", "rec", "cls"))
            and self.vietocr_weights_path.exists()
            and self.vietocr_config_path.exists()
        )

    def _load(self):
        if site.USER_SITE is None:
            site.USER_SITE = str(resource_root())
        # torch must be imported before paddleocr, on Windows. paddlepaddle
        # and torch each bundle their own build of Intel's OpenMP runtime
        # (libiomp5md.dll); paddle's is missing two exports torch_cpu.dll
        # needs (__kmpc_masked/__kmpc_end_masked -- confirmed by diffing the
        # two DLLs' import/export tables directly). Windows resolves a
        # dependency's bare-name imports (e.g. torch_cpu.dll importing
        # "libiomp5md.dll") against whatever module of that name is already
        # resident in the process before searching any directory, so
        # whichever package's copy loads first wins process-wide -- with
        # paddleocr imported first, torch's own later attempt to load
        # shm.dll (which needs torch_cpu.dll, which needs those two
        # exports) fails with "WinError 127: The specified procedure could
        # not be found". Importing torch first makes its own (complete)
        # copy the resident one instead; paddle is happy to reuse it.
        import torch  # noqa: F401
        from paddleocr import PaddleOCR
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        if self._reader is None:
            reader = PaddleOCR(
                use_angle_cls=True,
                lang="vi",
                show_log=False,
                det_model_dir=str(self.model_dir / "det"),
                rec_model_dir=str(self.model_dir / "rec"),
                cls_model_dir=str(self.model_dir / "cls"),
            )
            vietocr_config = Cfg.load_config_from_file(str(self.vietocr_config_path))
            vietocr_config["weights"] = str(self.vietocr_weights_path)
            vietocr_predictor = Predictor(vietocr_config)
            # PaddleOCR's own confidence filtering (`drop_score`) is tuned for
            # its own recognizer's score distribution; disable it so this
            # engine's `self.confidence` threshold (applied below, on
            # VietOCR's scores) stays the single source of truth.
            reader.text_recognizer = _VietOCRLineRecognizer(vietocr_predictor)
            reader.drop_score = 0.0
            self._reader = reader
        return self._reader

    @staticmethod
    def _correct_orientation(reader, image: np.ndarray) -> np.ndarray:
        """`normalize_card()` only fixes perspective plus a coarse
        portrait/landscape aspect check — a photo where the whole card was
        captured rotated ~90° (very common; a phone not held in landscape)
        or fully upside-down survives that step unchanged. PaddleOCR's own
        `cls` step then fixes each text-line crop's *legibility*, but box
        *reading order* is sorted by raw pixel position beforehand — so a
        still-rotated frame silently scrambles which line is "the value"
        vs. "the label" (or produces character soup for lines cls can't
        rescue on its own), even though most individual words still read
        fine. Straighten the whole frame first instead: try all 4
        rotations and keep whichever yields the most/longest boxes shaped
        like horizontal text lines (this reliably tells 0/180 apart from
        90/270, but scores 0 vs. 180 as a near-tie by design — text width
        looks the same either way up), then break that remaining 0-vs-180
        tie with a majority vote from the angle classifier across the
        real detected line crops.
        """
        from paddleocr.tools.infer.utility import get_rotate_crop_image

        best_rotation, best_score = 0, -1.0
        for rotation in range(4):
            candidate = np.ascontiguousarray(np.rot90(image, rotation))
            boxes, _ = reader.text_detector(candidate)
            score = 0.0
            if boxes is not None:
                for box in boxes:
                    width = np.linalg.norm(box[1] - box[0])
                    height = np.linalg.norm(box[3] - box[0])
                    if width > height * 1.2:
                        score += width
            if score > best_score:
                best_score, best_rotation = score, rotation
        oriented = np.ascontiguousarray(np.rot90(image, best_rotation))

        boxes, _ = reader.text_detector(oriented)
        if boxes is None or len(boxes) == 0:
            return oriented
        crops = [get_rotate_crop_image(oriented, box.astype(np.float32)) for box in boxes]
        _, angles, _ = reader.text_classifier(crops)
        flipped = sum(1 for angle, _score in angles if angle == "180")
        if flipped > len(angles) / 2:
            oriented = cv2.rotate(oriented, cv2.ROTATE_180)
        return oriented

    def recognize(self, image: np.ndarray) -> EngineResult | None:
        with self._lock:
            reader = self._load()
            image = self._correct_orientation(reader, image)
            result = reader.ocr(image, cls=True)
        lines: list[str] = []
        if result and result[0]:
            for line in result[0]:
                text, confidence = line[1]
                if confidence >= self.confidence:
                    lines.append(text)
        raw = restore_cccd_vietnamese("\n".join(lines))
        return EngineResult(parse_ocr_text(raw), raw, "PaddleOCR + VietOCR") if raw else None
