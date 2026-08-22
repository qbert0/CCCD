from __future__ import annotations

import json
from typing import Any

from desktop_app.backend.domain.models import (
    SERVICE_TEMPLATE_DOCUMENTS,
    DocumentType,
    ServiceTemplate,
)

SETTINGS_KEY = "document_set_overrides_v1/items"


def load_document_set_overrides(settings: Any) -> dict[ServiceTemplate, list[DocumentType]]:
    """The document set each service generates, one list per service.

    Defaults to SERVICE_TEMPLATE_DOCUMENTS -- this only reflects the shop's
    own hand-picked adjustments, saved once they change something in the
    settings form. Always returns a complete mapping for all 5 services,
    even before anything has ever been saved.
    """
    raw = str(settings.value(SETTINGS_KEY, "") or "").strip()
    saved: dict[ServiceTemplate, list[DocumentType]] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            for template_value, document_values in parsed.items():
                template = ServiceTemplate(template_value)
                saved[template] = [DocumentType(value) for value in document_values]
        except (TypeError, ValueError, json.JSONDecodeError):
            saved = {}
    return {
        # An empty saved list (every document unchecked) falls back to the
        # default set rather than generating nothing -- a service with zero
        # documents is never a state the shop actually wants, just an
        # accidental one.
        template: saved.get(template) or list(SERVICE_TEMPLATE_DOCUMENTS[template])
        for template in ServiceTemplate
    }


def save_document_set_overrides(
    settings: Any, overrides: dict[ServiceTemplate, list[DocumentType]],
) -> None:
    settings.setValue(
        SETTINGS_KEY,
        json.dumps(
            {
                template.value: [document_type.value for document_type in document_types]
                for template, document_types in overrides.items()
            },
            ensure_ascii=False,
        ),
    )
    settings.sync()
