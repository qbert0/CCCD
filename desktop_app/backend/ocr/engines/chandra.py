from __future__ import annotations

import json
import urllib.request
import uuid

import cv2
import numpy as np

from desktop_app.backend.ocr.parser import parse_ocr_text

from .base import BaseOCREngine, EngineResult


class ChandraAPIEngine(BaseOCREngine):
    key = "chandra"
    display_name = "Chandra OCR 2 · API"

    def __init__(self, api_url: str):
        self.api_url = api_url

    def available(self) -> bool:
        return bool(self.api_url)

    def recognize(self, image: np.ndarray) -> EngineResult | None:
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            raise RuntimeError("Không thể mã hóa ảnh cho Chandra API")
        boundary = f"----CCCDDesktop{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="cccd.jpg"\r\n'
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode("ascii") + encoded.tobytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
        request = urllib.request.Request(
            self.api_url,
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = payload.get("text", "")
        fields = payload.get("fields") or parse_ocr_text(raw)
        if not raw and not any(fields.values()):
            return None
        return EngineResult(fields, raw, payload.get("engine", self.display_name))
