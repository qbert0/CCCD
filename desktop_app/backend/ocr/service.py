from __future__ import annotations

import tempfile
import traceback
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path

import cv2
import numpy as np

from desktop_app.backend.ocr.engines import OCREngineRegistry


class CardSide(str, Enum):
    FRONT = "front"
    BACK = "back"
    UNKNOWN = "unknown"


@dataclass
class OCRFileResult:
    path: Path
    side: CardSide
    fields: dict[str, str]
    raw_text: str
    source: str
    error: str = ""
    expected_side: CardSide | None = None
    side_mismatch: bool = False


@dataclass
class OCRResult:
    fields: dict[str, str]
    raw_text: str
    source: str
    files: list[OCRFileResult] | None = None
    warnings: list[str] | None = None


def detect_side(raw_text: str, source: str) -> CardSide:
    normalized = unicodedata.normalize("NFD", raw_text.upper())
    folded = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    ).replace("Đ", "D")
    front_labels = (
        "CAN CUOC CONG DAN",
        "CITIZEN IDENTITY CARD",
        "HO VA TEN",
        "FULL NAME",
        "NGAY SINH",
        "DATE OF BIRTH",
        "QUE QUAN",
        "PLACE OF ORIGIN",
        "NOI THUONG TRU",
        "PLACE OF RESIDENCE",
    )
    if source == "QR CCCD" or any(label in folded for label in front_labels):
        return CardSide.FRONT
    mrz_like = "<<" in folded or sum(line.count("<") for line in folded.splitlines()) >= 4
    back_labels = (
        "DAC DIEM NHAN DANG",
        "NGAY, THANG, NAM",
        "DATE, MONTH, YEAR",
        "DATE OF ISSUE",
    )
    if mrz_like or any(label in folded for label in back_labels):
        return CardSide.BACK
    return CardSide.UNKNOWN


def _identity_value(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").casefold())
    return "".join(
        char for char in normalized
        if unicodedata.category(char) != "Mn" and char.isalnum()
    ).replace("đ", "d")


def _same_name(left: str, right: str) -> bool:
    first, second = _identity_value(left), _identity_value(right)
    if not first or not second:
        return True
    return first == second or SequenceMatcher(None, first, second).ratio() >= 0.88


def combine_file_results(
    file_results: list[OCRFileResult],
    warnings: list[str] | None = None,
) -> OCRResult:
    """Merge at most one detected front and back, checking they belong together."""
    recognized = [item for item in file_results if not item.error]
    if not recognized:
        detail = " | ".join(warnings or []) or "Không nhận dạng được dữ liệu"
        raise RuntimeError(f"Không đọc được ảnh CCCD. {detail}")
    usable = [item for item in recognized if not item.side_mismatch]
    merged: dict[str, str] = {}
    sources: list[str] = []
    combined_warnings = list(warnings or [])

    for item in usable:
        sources.append(item.source)
        for key, value in item.fields.items():
            if value and not merged.get(key):
                merged[key] = value
    for item in usable:
        if item.source == "QR CCCD" or item.side == CardSide.FRONT:
            for key, value in item.fields.items():
                if value:
                    merged[key] = value
    for item in usable:
        if item.side == CardSide.BACK:
            for key in ("expiry_date", "issue_date", "issue_place", "nationality"):
                if item.fields.get(key):
                    merged[key] = item.fields[key]

    front = next((item for item in usable if item.side == CardSide.FRONT), None)
    back = next((item for item in usable if item.side == CardSide.BACK), None)
    if front and back:
        front_name = front.fields.get("full_name", "")
        back_name = back.fields.get("full_name", "")
        front_id = _identity_value(front.fields.get("id_number", ""))
        back_id = _identity_value(back.fields.get("id_number", ""))
        conflicts = []
        if front_name and back_name and not _same_name(front_name, back_name):
            conflicts.append(f"họ tên mặt trước “{front_name}” khác mặt sau “{back_name}”")
        if front_id and back_id and front_id != back_id:
            conflicts.append("số định danh ở hai mặt không trùng nhau")
        if conflicts:
            combined_warnings.append(
                "Nguy cơ ảnh CCCD không hợp lệ: " + "; ".join(conflicts)
                + ". Hãy kiểm tra lại trước khi tạo tài liệu."
            )

    raw_parts = []
    for item in file_results:
        side_name = {
            CardSide.FRONT: "mặt trước",
            CardSide.BACK: "mặt sau",
            CardSide.UNKNOWN: "chưa rõ",
        }[item.side]
        body = item.error or item.raw_text
        raw_parts.append(f"--- {item.path.name} · {side_name} · {item.source} ---\n{body}")
    return OCRResult(
        merged,
        "\n\n".join(raw_parts),
        ", ".join(dict.fromkeys(sources)),
        file_results,
        combined_warnings,
    )


def _log_error(stage: str, error: Exception | str) -> None:
    try:
        log_path = Path(tempfile.gettempdir()) / "CCCDReport.log"
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(f"\n[{stage}] {error}\n")
            if isinstance(error, Exception):
                stream.write(traceback.format_exc())
    except OSError:
        pass


def read_image(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Không đọc được ảnh: {path.name}")
    return image


def _order_points(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(differences)]
    ordered[3] = points[np.argmax(differences)]
    return ordered


def normalize_card(image: np.ndarray) -> np.ndarray:
    """Find the largest card-like quadrilateral and correct its perspective."""
    height, width = image.shape[:2]
    scale = min(1.0, 1200 / max(height, width))
    small = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image.copy()
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 45, 140)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    card = None
    image_area = small.shape[0] * small.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        if cv2.contourArea(contour) < image_area * 0.18:
            break
        perimeter = cv2.arcLength(contour, True)
        approximation = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approximation) == 4:
            card = approximation.reshape(4, 2).astype(np.float32) / scale
            break

    if card is not None:
        top_left, top_right, bottom_right, bottom_left = _order_points(card)
        target_width = int(
            max(np.linalg.norm(bottom_right - bottom_left), np.linalg.norm(top_right - top_left))
        )
        target_height = int(
            max(np.linalg.norm(top_right - bottom_right), np.linalg.norm(top_left - bottom_left))
        )
        if target_width > 100 and target_height > 60:
            destination = np.array(
                [[0, 0], [target_width - 1, 0], [target_width - 1, target_height - 1], [0, target_height - 1]],
                dtype=np.float32,
            )
            matrix = cv2.getPerspectiveTransform(
                np.array([top_left, top_right, bottom_right, bottom_left]), destination
            )
            image = cv2.warpPerspective(image, matrix, (target_width, target_height))
    if image.shape[0] > image.shape[1] * 1.08:
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    return image


_REGISTRY: OCREngineRegistry | None = None


def engine_registry() -> OCREngineRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = OCREngineRegistry()
    return _REGISTRY


class OCRService:
    def __init__(self, registry: OCREngineRegistry | None = None):
        self.registry = registry or engine_registry()

    def scan_one(self, path: Path, expected: CardSide | None = None) -> OCRFileResult:
        """Scan exactly one image and never raise — any failure comes back
        as an OCRFileResult with `.error` set. This is the shared unit both
        `scan_files` (sequential) and per-image background threads (parallel)
        build on, so error handling and side-mismatch detection stay in one
        place regardless of which caller is driving it."""
        try:
            image = normalize_card(read_image(path))
            result = self.registry.recognize(image, _log_error)
        except Exception as exc:
            message = f"{path.name}: {exc}"
            _log_error("OCR từng ảnh", message)
            return OCRFileResult(path, CardSide.UNKNOWN, {}, "", "Lỗi nhận dạng", message, expected_side=expected)
        side = detect_side(result.raw_text, result.source)
        mismatch = bool(expected and side != CardSide.UNKNOWN and side != expected)
        return OCRFileResult(
            path, side, result.fields, result.raw_text, result.source,
            expected_side=expected, side_mismatch=mismatch,
        )

    def scan_files(
        self,
        paths: list[Path],
        expected_sides: list[CardSide] | None = None,
        on_file=None,
    ) -> OCRResult:
        """Scan every image in order, on the calling thread. If `on_file` is
        given, it's called with each OCRFileResult the moment that single
        image finishes."""
        if not paths:
            raise ValueError("Chưa chọn ảnh CCCD")
        if expected_sides is not None and len(expected_sides) != len(paths):
            raise ValueError("Số mặt CCCD dự kiến không khớp với số ảnh")
        file_results: list[OCRFileResult] = []
        warnings: list[str] = []

        for index, path in enumerate(paths):
            expected = expected_sides[index] if expected_sides is not None else None
            item = self.scan_one(path, expected)
            file_results.append(item)
            if item.error:
                warnings.append(item.error)
            elif item.side_mismatch:
                expected_name = "MẶT TRƯỚC" if expected == CardSide.FRONT else "MẶT SAU"
                detected_name = "MẶT TRƯỚC" if item.side == CardSide.FRONT else "MẶT SAU"
                warnings.append(
                    f"{path.name}: ảnh trong khung {expected_name} được nhận dạng là {detected_name}."
                )
            if on_file:
                on_file(item)

        return combine_file_results(file_results, warnings)
