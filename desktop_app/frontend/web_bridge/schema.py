"""JSON-serializable schema resolution for the web bridge.

Turns the pure Python field/layout functions extracted across field_meta.py,
person_form.py, documents/*.py, and tabs/document_tab.py into plain dicts
ready for json.dumps() -- the HTML/JS view layer renders generically from
this and never reimplements a field list, a visibility rule, or the packing
algorithm itself. Every function here is pure (no QWidget, no Qt import) so
it's callable and testable with no QApplication/display at all.
"""

from __future__ import annotations

from desktop_app.backend.domain.models import DocumentType
from desktop_app.frontend.components.person_form import (
    ENTITY_TYPE_ITEM,
    ENTITY_TYPE_OPTIONS,
    PERSON_FIELD_HELPERS,
    PERSON_FIELDS,
    resolve_person_form,
)
from desktop_app.frontend.documents.aftersale_form import ACTION_OPTIONS as AFTERSALE_ACTION_OPTIONS
from desktop_app.frontend.documents.aftersale_form import ATTACHMENT_ITEMS as AFTERSALE_ATTACHMENT_ITEMS
from desktop_app.frontend.documents.aftersale_form import FIELDS as AFTERSALE_FIELDS
from desktop_app.frontend.documents.base import resolve_document_form_rows
from desktop_app.frontend.documents.beautiful_number_form import FIELDS as BEAUTIFUL_NUMBER_FIELDS
from desktop_app.frontend.documents.prepaid_contract_form import FIELDS as PREPAID_CONTRACT_FIELDS
from desktop_app.frontend.documents.transfer_form import FIELDS as TRANSFER_FIELDS
from desktop_app.frontend.documents.transfer_form import PAYMENT_METHOD_OPTIONS
from desktop_app.frontend.field_meta import FieldTier, FieldWidth, document_field_meta, resolve_rows
from desktop_app.frontend.tabs.document_tab import COMMON_FIELDS, PAYMENT_METHOD_ITEM, resolve_common_rows

Row = list[list[tuple[object, int]]]

# ---------------------------------------------------------------------------
# Person forms (customer / new_owner tabs)
# ---------------------------------------------------------------------------

_PERSON_FIELD_BY_NAME = {name: (label, kind) for label, name, kind in PERSON_FIELDS}


def _person_field_descriptor(prefix: str, name: str, required: bool) -> dict:
    label, kind = _PERSON_FIELD_BY_NAME[name]
    return {
        "path": f"{prefix}.{name}",
        "name": name,
        "label": label,
        "kind": kind,
        "required": required,
        "helper": PERSON_FIELD_HELPERS.get(name, ""),
    }


def _entity_type_descriptor(prefix: str) -> dict:
    return {
        "path": f"{prefix}.entity_type",
        "name": "entity_type",
        "label": "Loại khách hàng",
        "kind": "select",
        "required": False,
        "helper": "",
        "options": ENTITY_TYPE_OPTIONS,
    }


def _person_rows_to_descriptors(prefix: str, rows: Row, required_map: dict[str, bool]) -> list[list[dict]]:
    out: list[list[dict]] = []
    for row in rows:
        cells = []
        for item, span in row:
            field = (
                _entity_type_descriptor(prefix)
                if item is ENTITY_TYPE_ITEM
                else _person_field_descriptor(prefix, item, required_map.get(item, False))
            )
            cells.append({"span": span, "field": field})
        out.append(cells)
    return out


def resolve_person_layout(prefix: str, document_type: DocumentType, role: str, entity_type: str) -> dict:
    """Full resolved layout (ready for json.dumps) for one PersonForm
    instance (customer or new_owner), driven entirely by
    resolve_person_form() -- the same function the QWidget PersonForm uses."""
    resolved = resolve_person_form(document_type, role, entity_type)
    return {
        "effective_entity_type": resolved["effective_entity_type"],
        "allow_entity": resolved["allow_entity"],
        "primary_rows": _person_rows_to_descriptors(prefix, resolved["primary_rows"], resolved["required"]),
        "detail_rows": _person_rows_to_descriptors(prefix, resolved["detail_rows"], resolved["required"]),
        "has_detail": resolved["has_detail"],
    }


# ---------------------------------------------------------------------------
# Document tab (common fields + the 4 per-document-type forms)
# ---------------------------------------------------------------------------

_DOCUMENT_FIELD_SPECS: dict[str, tuple[str, bool, str]] = {}
for _label, _name, _required, _kind in COMMON_FIELDS + TRANSFER_FIELDS + AFTERSALE_FIELDS + BEAUTIFUL_NUMBER_FIELDS + PREPAID_CONTRACT_FIELDS:
    _DOCUMENT_FIELD_SPECS[_name] = (_label, _required, _kind)

_FORM_FIELD_NAMES_BY_TYPE = {
    DocumentType.TRANSFER: [name for _label, name, _required, _kind in TRANSFER_FIELDS],
    DocumentType.AFTERSALE: [name for _label, name, _required, _kind in AFTERSALE_FIELDS],
    DocumentType.BEAUTIFUL_NUMBER: [name for _label, name, _required, _kind in BEAUTIFUL_NUMBER_FIELDS],
    DocumentType.PREPAID_CONTRACT: [name for _label, name, _required, _kind in PREPAID_CONTRACT_FIELDS],
}

# Aftersale's primary row is a manual override in AftersaleForm.__init__
# (action + attachments + backup_phone_1 packed together as 3 SHORT slots)
# rather than plain insertion-order packing -- mirrored here verbatim.
_AFTERSALE_PRIMARY_OVERRIDE = ["action", "attachments", "backup_phone_1"]


def _document_field_descriptor(name: str) -> dict:
    label, required, kind = _DOCUMENT_FIELD_SPECS[name]
    return {"path": name, "name": name, "label": label, "kind": kind, "required": required, "helper": ""}


def _compound_document_descriptor(item: str) -> dict:
    if item == PAYMENT_METHOD_ITEM:
        return {
            "path": "payment_method", "name": "payment_method", "label": "Hình thức thanh toán",
            "kind": "select", "required": True, "helper": "", "options": PAYMENT_METHOD_OPTIONS,
        }
    if item == "action":
        return {
            "path": "service_action", "name": "service_action", "label": "Dịch vụ yêu cầu",
            "kind": "select", "required": False, "helper": "", "options": AFTERSALE_ACTION_OPTIONS,
        }
    if item == "attachments":
        return {
            "path": "attachments", "name": "attachments", "label": "Giấy tờ kèm theo",
            "kind": "checkbox_group", "required": False, "helper": "",
            "items": [{"path": path, "label": label} for path, label in AFTERSALE_ATTACHMENT_ITEMS],
        }
    raise KeyError(item)  # pragma: no cover -- new compound widgets must be added here explicitly


_COMPOUND_DOCUMENT_ITEMS = {PAYMENT_METHOD_ITEM, "action", "attachments"}


def _document_rows_to_descriptors(rows: Row) -> list[list[dict]]:
    out: list[list[dict]] = []
    for row in rows:
        cells = []
        for item, span in row:
            field = _compound_document_descriptor(item) if item in _COMPOUND_DOCUMENT_ITEMS else _document_field_descriptor(item)
            cells.append({"span": span, "field": field})
        out.append(cells)
    return out


def resolve_document_form_layout(document_type: DocumentType) -> dict:
    """Full resolved layout (ready for json.dumps) for one document-type
    form's OWN fields (not DocumentTab's common fields -- see
    resolve_document_tab_layout below)."""
    field_names = _FORM_FIELD_NAMES_BY_TYPE[document_type]
    if document_type == DocumentType.AFTERSALE:
        # Mirror AftersaleForm.__init__'s explicit repack: backup_phone_1
        # joins the two compound widgets on one primary row; the remaining
        # plain fields (other_attachment, backup_phone_2 -- both DETAIL
        # tier today) fall through to the normal tier-based split.
        primary_rows = resolve_rows([(item, FieldWidth.SHORT) for item in _AFTERSALE_PRIMARY_OVERRIDE])
        remaining = [n for n in field_names if n not in _AFTERSALE_PRIMARY_OVERRIDE]
        detail_names = [n for n in remaining if document_field_meta(n).tier == FieldTier.DETAIL]
        detail_rows = resolve_rows([(n, document_field_meta(n).width) for n in detail_names])
        has_detail = bool(detail_names)
    else:
        resolved = resolve_document_form_rows(field_names)
        primary_rows, detail_rows, has_detail = resolved["primary_rows"], resolved["detail_rows"], resolved["has_detail"]

    return {
        "primary_rows": _document_rows_to_descriptors(primary_rows),
        "detail_rows": _document_rows_to_descriptors(detail_rows),
        "has_detail": has_detail,
    }


NOTES_FIELD = {
    "path": "notes", "name": "notes", "label": "Ghi chú",
    "kind": "textarea", "required": False, "helper": "",
    "placeholder": "Ghi chú nội bộ hoặc nội dung cần kiểm tra thêm",
}


def resolve_document_tab_layout(document_type: DocumentType) -> dict:
    """Full resolved layout for the whole "Thông tin tài liệu" tab: common
    fields (+ Transfer's payment_method sentinel) plus the active
    per-document-type form, plus the always-present notes field."""
    common = resolve_common_rows(document_type)
    form = resolve_document_form_layout(document_type)
    return {
        "common_rows": _document_rows_to_descriptors(common["rows"]),
        "notes_field": NOTES_FIELD,
        **form,
    }


SUBSCRIBER_NUMBER_FIELD = {
    "path": "subscriber_number", "name": "subscriber_number", "label": "Số thuê bao",
    "kind": "text", "required": True, "helper": "",
}
