from __future__ import annotations

import cv2
import numpy as np

from desktop_app.backend.ocr.parser import parse_qr

from .base import BaseOCREngine, EngineResult


class QREngine(BaseOCREngine):
    key = "qr"
    display_name = "QR CCCD · ZXing/OpenCV"

    def recognize(self, image: np.ndarray) -> EngineResult | None:
        raw = self._decode_zxing(image) or self._decode_opencv(image)
        return EngineResult(parse_qr(raw), raw, "QR CCCD") if raw else None

    @staticmethod
    def _decode_zxing(image: np.ndarray) -> str:
        try:
            import zxingcpp

            for rotation in range(4):
                candidate = np.rot90(image, rotation).copy()
                for barcode in zxingcpp.read_barcodes(candidate):
                    if barcode.text and "|" in barcode.text:
                        return barcode.text
        except ImportError:
            return ""
        return ""

    @staticmethod
    def _decode_opencv(image: np.ndarray) -> str:
        detector = cv2.QRCodeDetector()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variants = [
            image,
            gray,
            cv2.equalizeHist(gray),
            cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC),
        ]
        for variant in variants:
            for rotation in range(4):
                candidate = np.rot90(variant, rotation).copy()
                try:
                    value, _, _ = detector.detectAndDecode(candidate)
                    if value and "|" in value:
                        return value
                    ok, values, _, _ = detector.detectAndDecodeMulti(candidate)
                    if ok:
                        for item in values:
                            if item and "|" in item:
                                return item
                except cv2.error:
                    continue
        return ""
