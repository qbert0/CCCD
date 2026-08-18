from __future__ import annotations

import stat
from abc import ABC
from datetime import datetime
from pathlib import Path

from desktop_app.backend.domain.models import DocumentType, ReportData
from desktop_app.backend.validation import FieldError

from .renderer import render_document


class BaseDocumentModule(ABC):
    document_type: DocumentType
    template: Path
    suffix: str
    schema = None
    placeholders: frozenset[str] = frozenset()

    def __init__(self) -> None:
        if not self.template.exists():
            raise FileNotFoundError(f"Thiếu file mẫu: {self.template}")

    def check(self, data: ReportData) -> list[FieldError]:
        if data.document_type != self.document_type:
            return [FieldError("document_type", "Loại dữ liệu không đúng module tài liệu")]
        return self.schema.validate(data)

    def required_paths(self, data: ReportData) -> list[str]:
        return self.schema.required_paths(data)

    @staticmethod
    def _unique_output(output_dir: Path, stem: str, suffix: str) -> Path:
        candidate = output_dir / f"{stem}{suffix}"
        if not candidate.exists():
            return candidate
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return output_dir / f"{stem}_{timestamp}{suffix}"

    def generate(self, data: ReportData, output_dir: Path, preview: bool = False) -> Path:
        if not preview:
            errors = self.check(data)
            if errors:
                raise ValueError("\n".join(error.message for error in errors))
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = data.safe_stem() + ("_Xem_truoc" if preview else "")
        output = self._unique_output(output_dir, stem, self.suffix)
        render_document(data, self.template, output, self.placeholders)
        if preview:
            # A preview is only meant to be looked at — make it read-only so
            # opening it in Word/LibreOffice can't silently overwrite it as
            # if it were the real, final document.
            output.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        return output

    def preview(self, data: ReportData, preview_dir: Path) -> Path:
        return self.generate(data, preview_dir, preview=True)
