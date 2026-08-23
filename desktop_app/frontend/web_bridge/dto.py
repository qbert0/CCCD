"""JSON <-> dataclass conversion helpers for the web bridge."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from pathlib import Path

from PyQt5.QtCore import QBuffer, Qt
from PyQt5.QtGui import QPixmap

from desktop_app.backend.domain.models import PersonData
from desktop_app.backend.validation.rules import FieldError


def errors_to_json(errors: list[FieldError]) -> str:
    return json.dumps([{"path": e.path, "message": e.message} for e in errors])


def person_from_dict(values: dict) -> PersonData:
    base = PersonData()
    valid = set(asdict(base))
    for key, value in (values or {}).items():
        if key in valid:
            setattr(base, key, value)
    return base


def person_with_defaults_overlay(overlay: PersonData) -> PersonData:
    """Equivalent of PersonForm.set_person(): a fresh, defaulted PersonData
    (nationality="Việt Nam", issue_place="Cục Cảnh sát QLHC về TTXH", ...)
    with `overlay`'s non-empty fields applied on top -- so preserving a
    subject across a document-type switch never leaves the target's own
    sensible defaults blank."""
    base = PersonData()
    base.entity_type = overlay.entity_type or base.entity_type
    for key, value in asdict(overlay).items():
        if key == "entity_type":
            continue
        if str(value or "").strip():
            setattr(base, key, value)
    return base


def has_identity(person: PersonData) -> bool:
    return any(
        str(value or "").strip()
        for value in (person.full_name, person.organization_name, person.id_number, person.date_of_birth, person.address, person.phone)
    )


def thumbnail_data_url(path: Path, max_size: int = 210) -> str:
    """Small scaled image as a base64 data URL -- the web view never reads
    a filesystem path directly, for either the native-dialog or the
    HTML5-drop upload entry point.

    PNG (lossless, keeps alpha) when the source actually has transparency
    -- a background-removed signature photo saved as JPEG here would have
    every transparent pixel flattened to opaque black (Qt fills dropped
    alpha with black, not white, and JPEG has no alpha channel at all to
    begin with). JPEG otherwise, since most sources (CCCD scans etc.) are
    fully opaque photos where the smaller lossy encoding doesn't cost
    anything visible."""
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return ""
    scaled = pixmap.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    if scaled.hasAlphaChannel():
        scaled.save(buffer, "PNG")
        mime = "image/png"
    else:
        scaled.save(buffer, "JPEG", quality=85)
        mime = "image/jpeg"
    encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
    return f"data:{mime};base64,{encoded}"
