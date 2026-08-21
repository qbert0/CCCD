from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from desktop_app.backend.domain.models import (
    SERVICE_TEMPLATE_DOCUMENTS,
    DocumentType,
    ReportData,
    ServiceTemplate,
)
from desktop_app.backend.validation import FieldError

from .registry import DocumentRegistry


def _subscriber_rows(data: ReportData) -> list[dict[str, str]]:
    return [row for row in data.subscribers if str(row.get("subscriber_number", "")).strip()]


def _row_activation_date(row: dict[str, str]) -> str:
    # Same "default to today, not a required manual entry" treatment as
    # commitment_months falling back to data.commitment_months below -- a
    # SIM's hòa mạng date is virtually always "today" in practice, and the
    # UI's own row defaults already pre-fill it; this backend fallback just
    # keeps a blank row from blocking generation regardless of which UI
    # path produced it.
    return str(row.get("activation_date") or "").strip() or date.today().strftime("%d/%m/%Y")


def _variant_for(document_type: DocumentType, data: ReportData, template: ServiceTemplate) -> ReportData:
    """One document type's own ReportData, derived from the mẫu's shared
    `subscribers` list -- Transfer/Aftersale read `data.subscribers`
    directly inside renderer.py, so they need no per-variant field changes
    here; Beautiful Number and Prepaid Contract each have their OWN
    existing list field (`beautiful_subscribers`/`prepaid_subscribers`,
    already rendered correctly, unchanged) that just needs populating from
    the canonical list before generation."""
    # `template` (this function's own parameter, always the mẫu actually
    # being generated) always wins over whatever `data.service_template`
    # happened to carry in -- some validation (BeautifulNumberSchema's
    # "cước cam kết" requirement) reads this field, and it must reflect the
    # real mẫu even if a caller built `data` without setting it themselves.
    data = replace(data, service_template=template.value)
    rows = _subscriber_rows(data)
    # The beautiful-number appendix belongs to the subscriber who will use
    # the number after the ownership transfer.  `data.customer` is the old
    # owner throughout the transfer/aftersale documents, so the appendix
    # must deliberately switch its customer party to the new owner.
    document_customer = (
        data.new_owner if document_type == DocumentType.BEAUTIFUL_NUMBER else data.customer
    )
    if not rows:
        return replace(data, document_type=document_type, customer=document_customer)

    # Every existing schema (Prepaid Contract, Beautiful Number) still has
    # its own required_paths() checking the legacy scalar field directly,
    # independently of whichever list it also populates below -- keep it in
    # sync with the canonical list's first entry rather than touching each
    # schema.py to add yet another has_subscriber_number()-style OR-check.
    base = replace(
        data,
        document_type=document_type,
        customer=document_customer,
        subscriber_number=rows[0].get("subscriber_number", ""),
    )

    if document_type == DocumentType.BEAUTIFUL_NUMBER:
        return replace(
            base,
            beautiful_subscribers=[
                {
                    "subscriber_number": row.get("subscriber_number", ""),
                    "commitment_months": row.get("commitment_months") or data.commitment_months,
                    "monthly_fee": row.get("monthly_fee", ""),
                    "commitment_note": row.get("commitment_note", ""),
                }
                for row in rows
            ],
        )
    if document_type == DocumentType.PREPAID_CONTRACT:
        prepaid_company = (
            data.provider_company
            if data.prepaid_structured_parties and data.provider_company.organization_name
            else data.customer
        )
        return replace(
            base,
            customer=prepaid_company,
            sim_serial=rows[0].get("sim_serial", ""),
            activation_date=_row_activation_date(rows[0]),
            prepaid_subscribers=[
                {
                    "subscriber_number": row.get("subscriber_number", ""),
                    "sim_serial": row.get("sim_serial", ""),
                    "activation_date": _row_activation_date(row),
                }
                for row in rows
            ],
        )
    if document_type == DocumentType.SIM_CHANGE_FORM:
        return replace(
            base,
            sim_serial=rows[0].get("sim_serial", ""),
            sim_current_serial=data.sim_current_serial or rows[0].get("sim_serial", ""),
            activation_date=_row_activation_date(rows[0]),
        )
    return base


def generate_service_template(
    template: ServiceTemplate,
    data: ReportData,
    output_dir: Path,
    document_types: list[DocumentType] | None = None,
) -> tuple[list[Path], list[FieldError]]:
    """Generate every document a mẫu needs, into one folder.

    Validates every document FIRST and only starts writing once all of them
    pass -- a half-written folder (2 of 3 documents, one silently missing
    because a field further down the list was blank) would be worse than
    one clean "fix this field" error before anything touched disk.

    `document_types` overrides the template's default document set (see
    `document_set_settings.py`) -- the shop can turn individual documents
    off per service if their own workflow doesn't need one of them, without
    touching this function's own defaults.
    """
    registry = DocumentRegistry()
    variants = [
        _variant_for(document_type, data, template)
        for document_type in (document_types if document_types is not None else SERVICE_TEMPLATE_DOCUMENTS[template])
    ]

    errors: list[FieldError] = []
    for variant in variants:
        errors.extend(registry.for_data(variant).check(variant))
    if errors:
        return [], errors

    outputs = [registry.for_data(variant).generate(variant, output_dir) for variant in variants]
    return outputs, []
