from __future__ import annotations

import stat
from abc import ABC, abstractmethod
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
    # Most templates use an exact placeholder contract so an accidental
    # deletion is caught early. A module may opt into treating its DOCX as
    # the source of truth, in which case any supported subset is valid.
    allow_missing_placeholders = False

    def __init__(self) -> None:
        for template in self._all_templates():
            if not template.exists():
                raise FileNotFoundError(f"Thiếu file mẫu: {template}")

    def _all_templates(self) -> tuple[Path, ...]:
        """Every template file this module might render, checked up front at
        construction time so a missing file fails fast. A module needing more
        than one template (see AftersaleDocumentModule) overrides this
        alongside _resolve_template."""
        return (self.template,)

    def _resolve_template(self, data: ReportData) -> Path:
        """Which template file to render for this specific `data`. Defaults
        to the module's single `template`; override alongside
        _all_templates for a module that picks between several."""
        return self.template

    @abstractmethod
    def build_context(self, data: ReportData) -> dict[str, str]:
        """Every `{{ }}` placeholder's value for this document type.

        Every subclass merges renderer._common_context() (the handful of
        fields genuinely shared across document types, verified by an
        audit of every module's own `placeholders`) with its own
        type-specific fields -- see sim_change_form/module.py for the
        simplest example. A NEW document type must implement this too
        (that's the point of it being abstract): copy that same shape,
        don't add a case to some shared branch."""
        raise NotImplementedError

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
        render_document(
            data,
            self._resolve_template(data),
            output,
            self.placeholders,
            allow_missing_placeholders=self.allow_missing_placeholders,
            build_context=self.build_context,
        )
        if preview:
            # A preview is only meant to be looked at — make it read-only so
            # opening it in Word/LibreOffice can't silently overwrite it as
            # if it were the real, final document.
            output.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        return output

    def preview(self, data: ReportData, preview_dir: Path) -> Path:
        return self.generate(data, preview_dir, preview=True)
