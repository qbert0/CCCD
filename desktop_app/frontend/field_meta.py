"""Field taxonomy driving what gets remembered across cases and what stays
tucked away under "Thông tin chi tiết" until it's actually needed.

Every PersonData/ReportData field name is tagged along two independent axes:

- source: where the value comes from, and therefore whether it should be
  remembered across cases (SHOP/OPERATOR) or wiped on every new case (CCCD/
  DOCUMENT), or computed automatically (AUTO).
- tier: PRIMARY fields render directly in the form grid; DETAIL fields are
  grouped under a collapsible disclosure so the common case stays short
  without losing access to the rest.

Fields not listed default to DOCUMENT/PRIMARY — safer to over-show an
unclassified field than to silently hide it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PyQt5.QtWidgets import QGridLayout, QWidget

GRID_COLUMNS = 3


class FieldSource(str, Enum):
    CCCD = "cccd"
    SHOP = "shop"
    OPERATOR = "operator"
    DOCUMENT = "document"
    AUTO = "auto"


class FieldTier(str, Enum):
    PRIMARY = "primary"
    DETAIL = "detail"


class FieldWidth(str, Enum):
    """How many columns (out of a 3-column grid) a field's input should span."""

    SHORT = "short"  # 1 column — dates, short codes, gender, phone-style numbers
    MEDIUM = "medium"  # 2 columns — text a bit too long for 1 column, paired with a SHORT neighbor
    LONG = "long"  # full row — addresses, names, notes


ROW_BREAK = None  # sentinel: use as the widget in pack_fields() to force a new row


@dataclass(frozen=True)
class FieldMeta:
    source: FieldSource
    tier: FieldTier
    width: FieldWidth = FieldWidth.SHORT


_DEFAULT = FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT)

PERSON_FIELD_META: dict[str, FieldMeta] = {
    "full_name": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.MEDIUM),
    "id_number": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.SHORT),
    "date_of_birth": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.SHORT),
    "address": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.LONG),
    "issue_date": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.SHORT),
    "issue_place": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.SHORT),
    "organization_name": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.MEDIUM),
    "business_registration_number": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.SHORT),
    "representative_name": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.SHORT),
    "old_id_number": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "gender": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "nationality": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "hometown": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.LONG),
    "expiry_date": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "phone": FieldMeta(FieldSource.CCCD, FieldTier.PRIMARY, FieldWidth.SHORT),
    "email": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "other_contact": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "foreign_country": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "headquarters_address": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.MEDIUM),
    "business_registration_issue_place": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "business_registration_issue_date": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "representative_position": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "authorization_number": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
    "authorization_date": FieldMeta(FieldSource.CCCD, FieldTier.DETAIL, FieldWidth.SHORT),
}

DOCUMENT_FIELD_META: dict[str, FieldMeta] = {
    "document_date": FieldMeta(FieldSource.AUTO, FieldTier.PRIMARY, FieldWidth.SHORT),
    "shop_name": FieldMeta(FieldSource.SHOP, FieldTier.PRIMARY, FieldWidth.LONG),
    "shop_address": FieldMeta(FieldSource.SHOP, FieldTier.PRIMARY, FieldWidth.LONG),
    # Not FieldSource.SHOP: unlike shop_name/shop_address it isn't shown on
    # every document (only Aftersale/Prepaid), and the Company Profile
    # dialog's own form doesn't surface a phone field to set a shared
    # default from anyway. OPERATOR keeps it a plain in-form field that's
    # simply remembered for the current session, like staff_name.
    "shop_phone": FieldMeta(FieldSource.OPERATOR, FieldTier.PRIMARY, FieldWidth.SHORT),
    "shop_phone_2": FieldMeta(FieldSource.OPERATOR, FieldTier.DETAIL, FieldWidth.SHORT),
    "shop_phone_3": FieldMeta(FieldSource.OPERATOR, FieldTier.DETAIL, FieldWidth.SHORT),
    "staff_name": FieldMeta(FieldSource.OPERATOR, FieldTier.PRIMARY, FieldWidth.SHORT),
    "provider_representative": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "provider_position": FieldMeta(FieldSource.DOCUMENT, FieldTier.DETAIL, FieldWidth.SHORT),
    "provider_phone": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "provider_email": FieldMeta(FieldSource.DOCUMENT, FieldTier.DETAIL, FieldWidth.SHORT),
    "provider_unit_address": FieldMeta(FieldSource.SHOP, FieldTier.PRIMARY, FieldWidth.MEDIUM),
    "service_point_address": FieldMeta(FieldSource.OPERATOR, FieldTier.PRIMARY, FieldWidth.LONG),
    "service_point_phone": FieldMeta(FieldSource.OPERATOR, FieldTier.PRIMARY, FieldWidth.SHORT),
    "sim_serial": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "activation_date": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "contract_number": FieldMeta(FieldSource.DOCUMENT, FieldTier.DETAIL, FieldWidth.SHORT),
    "subscriber_code": FieldMeta(FieldSource.DOCUMENT, FieldTier.DETAIL, FieldWidth.SHORT),
    "service_point_name": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.MEDIUM),
    "registration_time": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "commitment_months": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "monthly_fee": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    # No more "Thông tin chi tiết" section for Beautiful Number -- its own
    # fields now live entirely inside the subscriber-number table (see
    # web_bridge/schema.py's resolve_document_form_layout()), so commitment_note
    # moved from DETAIL to PRIMARY alongside its row-mates.
    "commitment_note": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.LONG),
    "subscriber_number_1": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "subscriber_number_2": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "commitment_months_2": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "monthly_fee_2": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "commitment_note_2": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.LONG),
    "service_action": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "payment_method": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "source_contract_number": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "source_contract_date": FieldMeta(FieldSource.DOCUMENT, FieldTier.DETAIL, FieldWidth.SHORT),
    "registration_form_date": FieldMeta(FieldSource.DOCUMENT, FieldTier.DETAIL, FieldWidth.SHORT),
    "transfer_time": FieldMeta(FieldSource.DOCUMENT, FieldTier.DETAIL, FieldWidth.SHORT),
    "transfer_effective_date": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "has_id_attachment": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "has_original_sim": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    # No more "Thông tin chi tiết" disclosure for Aftersale either -- its
    # identity block (shop_id_number/issue_date/issue_place, below) and these
    # 2 fields all now live directly in resolve_aftersale_form_rows()'s fixed
    # row order.
    "other_attachment": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.LONG),
    "backup_phone_1": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "backup_phone_2": FieldMeta(FieldSource.DOCUMENT, FieldTier.PRIMARY, FieldWidth.SHORT),
    "shop_id_number": FieldMeta(FieldSource.SHOP, FieldTier.PRIMARY, FieldWidth.SHORT),
    "shop_issue_date": FieldMeta(FieldSource.SHOP, FieldTier.PRIMARY, FieldWidth.SHORT),
    "shop_issue_place": FieldMeta(FieldSource.SHOP, FieldTier.PRIMARY, FieldWidth.SHORT),
    "notes": FieldMeta(FieldSource.DOCUMENT, FieldTier.DETAIL, FieldWidth.LONG),
}


def person_field_meta(name: str) -> FieldMeta:
    return PERSON_FIELD_META.get(name, _DEFAULT)


def document_field_meta(name: str) -> FieldMeta:
    return DOCUMENT_FIELD_META.get(name, _DEFAULT)


def persistent_document_field_names() -> list[str]:
    """Field names remembered across cases as a session convenience
    (OPERATOR sourced only — SHOP fields now come from the explicit-save
    Company Profile instead of an implicit auto-save-on-close)."""
    return [
        name
        for name, meta in DOCUMENT_FIELD_META.items()
        if meta.source == FieldSource.OPERATOR
    ]


_SPAN = {FieldWidth.SHORT: 1, FieldWidth.MEDIUM: 2, FieldWidth.LONG: GRID_COLUMNS}


def resolve_rows(items: list[tuple[object, FieldWidth]]) -> list[list[tuple[object, int]]]:
    """Pure packing algorithm, with no QGridLayout/QWidget involved: lay items
    left-to-right, top-to-bottom on a GRID_COLUMNS-wide grid, each spanning 1
    column (SHORT), 2 (MEDIUM) or the full row (LONG), wrapping whenever an
    item would overflow the current row. An item equal to ROW_BREAK (None)
    renders nothing and just forces the rest of the current row to stay empty
    — for grouping fields that would otherwise get greedily packed with an
    unrelated neighbor.

    Returns rows of (item, span) pairs. This is the single source of truth
    for the packing rules — both `pack_fields()` below (the PyQt QGridLayout
    adapter) and the web bridge's schema resolver call this directly, so the
    two view layers can never disagree on how fields wrap into rows."""
    rows: list[list[tuple[object, int]]] = []
    row: list[tuple[object, int]] = []
    col = 0
    for item, width in items:
        if item is ROW_BREAK:
            if col != 0:
                rows.append(row)
                row = []
                col = 0
            continue
        span = _SPAN[width]
        if col + span > GRID_COLUMNS:
            rows.append(row)
            row = []
            col = 0
        row.append((item, span))
        col += span
        if col >= GRID_COLUMNS:
            rows.append(row)
            row = []
            col = 0
    if row:
        rows.append(row)
    return rows


def place_rows(grid: QGridLayout, rows: list[list[tuple[QWidget, int]]]) -> None:
    """Place already-resolved rows (as returned by `resolve_rows()`) onto
    `grid` directly, with no re-resolution -- for callers that resolved rows
    once (e.g. against field-path strings) and now have the real QWidgets to
    drop into those same cells, without running the packing algorithm twice.

    Always clears every previous placement first, same reasoning as
    `pack_fields()` below."""
    while grid.count():
        grid.takeAt(0)
    for row_index, row in enumerate(rows):
        col = 0
        for widget, span in row:
            grid.addWidget(widget, row_index, col, 1, span)
            col += span


def pack_fields(grid: QGridLayout, items: list[tuple[QWidget | None, FieldWidth]]) -> None:
    """Lay widgets on `grid` following `resolve_rows()`'s packing rules.

    Called repeatedly on the same grid as visibility changes (entity type,
    document type, ...), so it always clears every previous placement first
    — otherwise a widget dropped from `items` this time around leaves its
    old cell reservation behind, and a *different* widget assigned that same
    cell later ends up visually overlapping it."""
    while grid.count():
        grid.takeAt(0)
    for row_index, row in enumerate(resolve_rows(items)):
        col = 0
        for widget, span in row:
            grid.addWidget(widget, row_index, col, 1, span)
            col += span
