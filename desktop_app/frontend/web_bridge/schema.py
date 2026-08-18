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
    resolve_organization_information_form,
    resolve_person_information_form,
    resolve_person_form,
)
from desktop_app.frontend.documents.aftersale_form import ACTION_OPTIONS as AFTERSALE_ACTION_OPTIONS
from desktop_app.frontend.documents.aftersale_form import ATTACHMENT_ITEMS as AFTERSALE_ATTACHMENT_ITEMS
from desktop_app.frontend.documents.aftersale_form import FIELDS as AFTERSALE_FIELDS
from desktop_app.frontend.documents.aftersale_form import resolve_aftersale_form_rows
from desktop_app.frontend.documents.base import resolve_document_form_rows
from desktop_app.frontend.documents.beautiful_number_form import FIELDS as BEAUTIFUL_NUMBER_FIELDS
from desktop_app.frontend.documents.prepaid_contract_form import FIELDS as PREPAID_CONTRACT_FIELDS
from desktop_app.frontend.documents.transfer_form import FIELDS as TRANSFER_FIELDS
from desktop_app.frontend.documents.transfer_form import (
    PAYMENT_METHOD_ITEM,
    PAYMENT_METHOD_OPTIONS,
    resolve_transfer_form_rows,
)
from desktop_app.frontend.field_meta import ROW_BREAK, FieldWidth, resolve_rows
from desktop_app.frontend.tabs.document_tab import COMMON_FIELDS, resolve_common_rows

Row = list[list[tuple[object, int]]]

# ---------------------------------------------------------------------------
# Person forms (customer / new_owner tabs)
# ---------------------------------------------------------------------------

_PERSON_FIELD_BY_NAME = {name: (label, kind) for label, name, kind in PERSON_FIELDS}


def _person_field_descriptor(prefix: str, name: str, required: bool) -> dict:
    label, kind = _PERSON_FIELD_BY_NAME[name]
    descriptor = {
        "path": f"{prefix}.{name}",
        "name": name,
        "label": label,
        "kind": kind,
        "required": required,
        "helper": PERSON_FIELD_HELPERS.get(name, ""),
    }
    if prefix == "representative" and name == "representative_position":
        descriptor.update({"kind": "select", "options": ["Giám đốc", "Nhân viên"]})
    return descriptor


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
# Company Profile dialog -- 2 sub-tabs, each its own separate persisted
# PersonData record (see WebBridge.company_profile / .representative_profile):
# "Thông tin công ty" (the shop's own registration identity, always
# entity_type "Tổ chức") and "Người đại diện" (an actual person, with its own
# CCCD/OCR intake -- see UploadCard target "representative" in app.js).
# ---------------------------------------------------------------------------


def resolve_company_profile_layout() -> dict:
    """Reusable organization form for the persisted company profile."""
    resolved = resolve_organization_information_form()
    rows = _person_rows_to_descriptors("profile", resolved["primary_rows"], resolved["required"])
    return {"primary_rows": rows, "detail_rows": [], "has_detail": False}


def resolve_representative_profile_layout() -> dict:
    """Reusable 3-row personal form for the persisted representative."""
    resolved = resolve_person_information_form()
    rows = _person_rows_to_descriptors("representative", resolved["primary_rows"], resolved["required"])
    return {"primary_rows": rows, "detail_rows": [], "has_detail": False}


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



def _document_field_descriptor(name: str) -> dict:
    label, required, kind = _DOCUMENT_FIELD_SPECS[name]
    descriptor = {
        "path": name, "name": name, "label": label, "kind": kind,
        "required": required, "helper": "",
    }
    if name == "transfer_time":
        descriptor.update({"max_length": 2, "helper": "Chỉ nhập giờ từ 0 đến 23"})
    return descriptor


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
    if item == BEAUTIFUL_NUMBER_TABLE_ITEM:
        columns = [
            ("Số thuê bao", "subscriber_number", "number"),
            ("Thời gian cam kết", "commitment_months", "number"),
            ("Cước cam kết tối thiểu/tháng (nghìn đồng)", "monthly_fee", "number"),
            ("Ghi chú", "commitment_note", "text"),
        ]
        return {
            "path": "subscriber_table", "name": "subscriber_table", "label": "Số thuê bao đăng ký",
            "kind": "subscriber_table", "required": False, "helper": "",
            "list_path": "beautiful_subscribers",
            "add_label": "+ Thêm số",
            "columns": [
                {"label": label, "name": name, "kind": kind, "required": name != "commitment_note"}
                for label, name, kind in columns
            ],
        }
    raise KeyError(item)  # pragma: no cover -- new compound widgets must be added here explicitly


BEAUTIFUL_NUMBER_TABLE_ITEM = "subscriber_table"
_COMPOUND_DOCUMENT_ITEMS = {PAYMENT_METHOD_ITEM, "action", "attachments", BEAUTIFUL_NUMBER_TABLE_ITEM}


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
    if document_type == DocumentType.TRANSFER:
        resolved = resolve_transfer_form_rows()
        primary_rows, detail_rows, has_detail = resolved["primary_rows"], resolved["detail_rows"], resolved["has_detail"]
    elif document_type == DocumentType.BEAUTIFUL_NUMBER:
        # Bespoke, by explicit request: no "Thông tin chi tiết" disclosure --
        # every one of this document's own fields lives inside the single
        # repeating subscriber-number table instead (see
        # _compound_document_descriptor's BEAUTIFUL_NUMBER_TABLE_ITEM branch).
        primary_rows = resolve_rows([(BEAUTIFUL_NUMBER_TABLE_ITEM, FieldWidth.LONG)])
        detail_rows, has_detail = [], False
    elif document_type == DocumentType.AFTERSALE:
        resolved = resolve_aftersale_form_rows()
        primary_rows, detail_rows, has_detail = resolved["primary_rows"], resolved["detail_rows"], resolved["has_detail"]
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
    if document_type == DocumentType.TRANSFER:
        # Transfer deliberately combines one shared field and its own fields
        # into a single 3-row grid:
        # 1) document date + payment method
        # 2) contract number + contract date + registration-form date
        # 3) transfer time + effective date.
        transfer_items: list[tuple[object, FieldWidth]] = [
            ("document_date", FieldWidth.SHORT), (PAYMENT_METHOD_ITEM, FieldWidth.SHORT),
            (ROW_BREAK, FieldWidth.SHORT),
            ("source_contract_number", FieldWidth.SHORT),
            ("source_contract_date", FieldWidth.SHORT),
            ("registration_form_date", FieldWidth.SHORT),
            (ROW_BREAK, FieldWidth.SHORT),
            ("transfer_time", FieldWidth.SHORT),
            ("transfer_effective_date", FieldWidth.SHORT),
        ]
        return {
            "common_rows": [],
            "primary_rows": _document_rows_to_descriptors(resolve_rows(transfer_items)),
            "detail_rows": [],
            "has_detail": False,
            "notes_field": None,
        }
    if document_type == DocumentType.AFTERSALE:
        return {
            "common_rows": [],
            "notes_field": None,
            **form,
        }
    if document_type == DocumentType.PREPAID_CONTRACT:
        provider_sections = [
            {
                "title": "Đơn vị cung cấp",
                "description": "Thông tin của bên cung cấp dịch vụ viễn thông",
                "rows": _document_rows_to_descriptors(resolve_rows([
                    ("provider_unit_address", FieldWidth.MEDIUM),
                    ("provider_representative", FieldWidth.SHORT),
                ])),
            },
            {
                "title": "Điểm cung cấp",
                "description": "Nơi trực tiếp tiếp nhận và thực hiện giao dịch",
                "rows": _document_rows_to_descriptors(resolve_rows([
                    ("service_point_name", FieldWidth.MEDIUM), ("staff_name", FieldWidth.SHORT),
                    (ROW_BREAK, FieldWidth.SHORT),
                    ("service_point_address", FieldWidth.LONG),
                    (ROW_BREAK, FieldWidth.SHORT),
                    ("service_point_phone", FieldWidth.SHORT), ("registration_time", FieldWidth.MEDIUM),
                ])),
            },
        ]
        return {
            "common_rows": [], "primary_rows": [], "detail_rows": [],
            "has_detail": False, "notes_field": None, "sections": provider_sections,
        }
    return {
        "common_rows": _document_rows_to_descriptors(common["rows"]),
        "notes_field": None if document_type in {
            DocumentType.TRANSFER, DocumentType.AFTERSALE, DocumentType.BEAUTIFUL_NUMBER,
        } else NOTES_FIELD,
        **form,
    }


def resolve_prepaid_sim_layout() -> dict:
    """Descriptor for the five printed subscriber rows in the prepaid PDF."""
    return {
        "title": "Danh sách số SIM và ngày hòa mạng",
        "hint": "Tối đa 5 số, tương ứng 5 dòng có sẵn trong tài liệu",
        "max_rows": 5,
        "columns": [
            {"name": "subscriber_number", "label": "Số thuê bao", "kind": "number", "required": True},
            {"name": "sim_serial", "label": "Số sê-ri SIM", "kind": "number", "required": True},
            {"name": "activation_date", "label": "Ngày hòa mạng", "kind": "date", "required": True},
        ],
    }


SUBSCRIBER_NUMBER_FIELD = {
    "path": "subscriber_number", "name": "subscriber_number", "label": "Số thuê bao",
    "kind": "text", "required": True, "helper": "",
}
