from __future__ import annotations

from dataclasses import asdict

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QComboBox, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from desktop_app.backend.domain.models import DocumentType, PersonData
from desktop_app.frontend.field_meta import (
    GRID_COLUMNS,
    ROW_BREAK,
    FieldTier,
    FieldWidth,
    person_field_meta,
    place_rows,
    resolve_rows,
)

from .field_input import FieldInput


PERSON_FIELDS = [
    ("Họ và tên", "full_name", "text"),
    # id_number/old_id_number stay free-text: this field also covers hộ
    # chiếu (passport) numbers, which can start with a letter.
    ("Số CCCD/CMND/Hộ chiếu", "id_number", "text"),
    ("Số CMND cũ", "old_id_number", "text"),
    ("Ngày sinh", "date_of_birth", "date"),
    ("Giới tính", "gender", "text"),
    ("Quốc tịch", "nationality", "text"),
    ("Quê quán", "hometown", "text"),
    ("Địa chỉ theo giấy tờ", "address", "text"),
    ("Ngày cấp", "issue_date", "date"),
    ("Nơi cấp/Đơn vị cấp", "issue_place", "text"),
    ("Ngày hết hạn", "expiry_date", "date"),
    ("Điện thoại liên hệ", "phone", "number"),
    ("Email", "email", "text"),
    ("Liên hệ khác", "other_contact", "text"),
    ("Quốc gia cấp hộ chiếu", "foreign_country", "text"),
    ("Tên cơ quan/tổ chức", "organization_name", "text"),
    ("Địa chỉ trụ sở chính", "headquarters_address", "text"),
    ("Số ĐKKD/QĐTL/GPĐT", "business_registration_number", "number"),
    ("Nơi cấp giấy ĐKKD/QĐTL/GPĐT", "business_registration_issue_place", "text"),
    ("Ngày cấp giấy ĐKKD/QĐTL/GPĐT", "business_registration_issue_date", "date"),
    ("Người đại diện/ủy quyền", "representative_name", "text"),
    ("Chức vụ", "representative_position", "text"),
    ("Số giấy ủy quyền", "authorization_number", "number"),
    ("Ngày giấy ủy quyền", "authorization_date", "date"),
]

PERSON_FIELD_HELPERS = {
    "id_number": "CCCD: 12 số · CMND: 9-12 số · Hộ chiếu: chữ và số",
}


# Packing order for the primary grid -- deliberately NOT PERSON_FIELDS order:
# groups fields that logically belong together onto the same row. Organization
# and individual fields are never visible at once, so interleaving them here
# lets the same slot serve both: id_number+representative_name+
# business_registration_number for an organization, id_number+full_name (both
# MEDIUM/SHORT summing to 3) for an individual.
# self.entity_group (the "Loại khách hàng" selector) is prepended ahead of
# this in _refresh_visibility -- sharing organization_name's row (MEDIUM, 2
# cols, exact fit) for the organization case, or alone on its own row for
# the individual case, since full_name belongs with id_number instead.
PRIMARY_PACK_ORDER = [
    "organization_name",
    "id_number", "representative_name", "business_registration_number", "full_name",
    "date_of_birth", "issue_date", "issue_place",
    "phone",
    "address",
]

DETAIL_PACK_ORDER = [
    "nationality", "headquarters_address", ROW_BREAK,
    "representative_position", "authorization_number", "authorization_date", ROW_BREAK,
    "old_id_number", "gender", ROW_BREAK,
    "hometown",
    "expiry_date", "email", ROW_BREAK,
    "other_contact", "foreign_country", ROW_BREAK,
    "business_registration_issue_place", "business_registration_issue_date",
]


ENTITY_TYPE_OPTIONS = ["Cá nhân", "Tổ chức"]
ORGANIZATION_ONLY_FIELDS = {
    "organization_name", "headquarters_address", "business_registration_number",
    "business_registration_issue_place", "business_registration_issue_date",
    "representative_name", "representative_position", "authorization_number", "authorization_date",
}
PERSONAL_ONLY_FIELDS = {"full_name"}
# Sentinel item name standing in for the compound entity_type selector in a
# resolved row -- not a PERSON_FIELDS entry, so callers must special-case it
# rather than looking it up in person_field_meta().
ENTITY_TYPE_ITEM = "entity_type"


def resolve_person_form(document_type: DocumentType, role: str, entity_type: str) -> dict:
    """Pure computation of a PersonForm's visible/required fields and packed
    row layout for (document_type, role, entity_type) -- no live field VALUES
    involved. This is the single source of truth for PersonForm.configure()/
    _refresh_visibility()'s branching: both the QWidget PersonForm below and
    the web bridge's schema resolver call this directly, so the PyQt UI and
    the web UI can never disagree on which fields show, which are required,
    or how they pack into rows.

    Returns {"allow_entity", "effective_entity_type", "visible": set[str],
    "required": dict[str, bool], "primary_rows", "detail_rows", "has_detail"}.
    """
    allow_entity = document_type in {DocumentType.TRANSFER, DocumentType.PREPAID_CONTRACT}
    effective_entity_type = entity_type if allow_entity else "Cá nhân"

    if document_type == DocumentType.BEAUTIFUL_NUMBER:
        base_visible = {"full_name", "id_number"}
        base_required = set(base_visible)
    elif document_type == DocumentType.AFTERSALE:
        if role == "new_owner":
            base_visible = {"full_name", "id_number", "issue_date", "issue_place"}
        else:
            base_visible = {"full_name", "id_number", "issue_date", "issue_place", "address", "phone"}
        base_required = set(base_visible)
    elif document_type == DocumentType.PREPAID_CONTRACT:
        base_visible = {
            "full_name", "id_number", "issue_date", "issue_place", "date_of_birth",
            "address", "phone", "email", "other_contact", "nationality", "foreign_country",
            "organization_name", "headquarters_address", "business_registration_number",
            "business_registration_issue_place", "business_registration_issue_date",
            "representative_name", "representative_position", "authorization_number",
            "authorization_date",
        }
        base_required = {
            "id_number", "issue_date", "issue_place", "date_of_birth",
            "address", "nationality", "phone",
        }
    else:
        base_visible = {
            "full_name", "id_number", "issue_date", "issue_place", "date_of_birth",
            "address", "nationality", "organization_name", "headquarters_address",
            "business_registration_number", "representative_name", "representative_position",
            "authorization_number", "authorization_date",
        }
        base_required = {
            "id_number", "issue_date", "issue_place", "date_of_birth",
            "address", "nationality",
        }

    organization = effective_entity_type == "Tổ chức"
    visible_names: set[str] = set()
    required_map: dict[str, bool] = {}
    for label, name, _kind in PERSON_FIELDS:
        visible = name in base_visible
        if organization and name in PERSONAL_ONLY_FIELDS:
            visible = False
        if not organization and name in ORGANIZATION_ONLY_FIELDS:
            visible = False
        if organization:
            organization_required = {
                "organization_name", "headquarters_address", "business_registration_number", "representative_name"
            }
            organization_required |= {"id_number", "issue_date", "issue_place", "date_of_birth"}
            if document_type == DocumentType.TRANSFER:
                organization_required |= {"address", "nationality"}
            if document_type == DocumentType.PREPAID_CONTRACT:
                organization_required |= {
                    "business_registration_issue_place", "business_registration_issue_date",
                    "phone", "representative_position",
                }
            required = name in organization_required
        else:
            required = name in base_required or name == "full_name"
        required_map[name] = required and visible
        if visible:
            visible_names.add(name)

    primary_items: list[tuple[object, FieldWidth]] = []
    if allow_entity:
        primary_items.append((ENTITY_TYPE_ITEM, FieldWidth.SHORT))
        if "organization_name" not in visible_names:
            primary_items.append((ROW_BREAK, FieldWidth.SHORT))
    for name in PRIMARY_PACK_ORDER:
        if name is ROW_BREAK:
            primary_items.append((ROW_BREAK, FieldWidth.SHORT))
        elif name in visible_names:
            primary_items.append((name, person_field_meta(name).width))

    detail_items: list[tuple[object, FieldWidth]] = []
    has_detail = False
    for name in DETAIL_PACK_ORDER:
        if name is ROW_BREAK:
            detail_items.append((ROW_BREAK, FieldWidth.SHORT))
        elif name in visible_names:
            detail_items.append((name, person_field_meta(name).width))
            has_detail = True

    return {
        "allow_entity": allow_entity,
        "effective_entity_type": effective_entity_type,
        "visible": visible_names,
        "required": required_map,
        "primary_rows": resolve_rows(primary_items),
        "detail_rows": resolve_rows(detail_items),
        "has_detail": has_detail,
    }


def _grid(spacing_v: int = 11) -> QGridLayout:
    grid = QGridLayout()
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(spacing_v)
    for column in range(GRID_COLUMNS):
        grid.setColumnStretch(column, 1)
    return grid


class PersonForm(QWidget):
    entity_changed = pyqtSignal()

    def __init__(self, path_prefix: str, required: bool = True, parent=None):
        super().__init__(parent)
        self.path_prefix = path_prefix
        self._document_type = DocumentType.TRANSFER
        self._role = "customer"
        self._visible_names: set[str] = set()
        self._required_names: set[str] = set()
        # Tracks whether the entity-type selector should participate in
        # packing. Deliberately NOT self.entity_group.isVisible(): that
        # reflects the whole ancestor chain (false before the window is ever
        # shown), so the very first pack_fields() call during construction
        # would silently omit it and leave a stale, entity-less layout that
        # a later re-pack wouldn't fully overwrite.
        self._allow_entity = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 14, 4, 12)
        outer.setSpacing(10)

        self.entity_label = QLabel("Loại khách hàng")
        self.entity_label.setObjectName("fieldLabel")
        self.entity_type = QComboBox()
        self.entity_type.addItems(["Cá nhân", "Tổ chức"])
        self.entity_type.setCursor(Qt.PointingHandCursor)
        self.entity_type.currentTextChanged.connect(self._entity_type_changed)
        # Only two short words -- no need to stretch this across the whole
        # form width like the text fields below it.
        self.entity_type.setMinimumWidth(200)
        self.entity_group = QWidget()
        entity_layout = QVBoxLayout(self.entity_group)
        entity_layout.setContentsMargins(0, 0, 0, 0)
        entity_layout.setSpacing(4)
        entity_layout.addWidget(self.entity_label)
        entity_layout.addWidget(self.entity_type)
        # Placed inside primary_grid itself (see _refresh_visibility) so it
        # can share a row with other short fields instead of always sitting
        # alone on its own line.

        self.primary_grid = _grid()
        outer.addLayout(self.primary_grid)

        self.detail_toggle = QPushButton("▸ Thông tin chi tiết")
        self.detail_toggle.setObjectName("disclosureButton")
        self.detail_toggle.setCheckable(True)
        self.detail_toggle.setCursor(Qt.PointingHandCursor)
        self.detail_toggle.toggled.connect(self._toggle_detail)
        self.detail_toggle.hide()
        outer.addWidget(self.detail_toggle)

        self.detail_grid = _grid()
        self._detail_container = QWidget()
        self._detail_container.setLayout(self.detail_grid)
        self._detail_container.setVisible(False)
        outer.addWidget(self._detail_container)
        # Without this, any extra height this form gets handed by its
        # scroll area/tab page (most visibly right after collapsing the
        # detail section back down) gets distributed into primary_grid's own
        # rows instead, stretching every field tall and ugly. This stretch
        # claims that leftover space so the grid always sits at its natural
        # height.
        outer.addStretch(1)

        self.fields: dict[str, FieldInput] = {}
        for label, name, input_kind in PERSON_FIELDS:
            field = FieldInput(
                label, f"{path_prefix}.{name}", input_kind=input_kind, helper=PERSON_FIELD_HELPERS.get(name, "")
            )
            self.fields[name] = field
        self.fields["nationality"].set_value("Việt Nam")
        self.fields["issue_place"].set_value("Cục Cảnh sát QLHC về TTXH")
        self.configure(DocumentType.TRANSFER, "customer")

    def configure(self, document_type: DocumentType, role: str) -> None:
        self._document_type = document_type
        self._role = role
        resolved = resolve_person_form(document_type, role, self.entity_type.currentText())
        self._allow_entity = resolved["allow_entity"]
        self.entity_label.setVisible(self._allow_entity)
        self.entity_type.setVisible(self._allow_entity)
        self.entity_group.setVisible(self._allow_entity)
        if self.entity_type.currentText() != resolved["effective_entity_type"]:
            self.entity_type.setCurrentText(resolved["effective_entity_type"])
            return  # setCurrentText triggers _entity_type_changed -> _refresh_visibility
        self._refresh_visibility(resolved)

    def _entity_type_changed(self) -> None:
        self._refresh_visibility()
        self.entity_changed.emit()

    def _toggle_detail(self, expanded: bool) -> None:
        self._detail_container.setVisible(expanded)
        self.detail_toggle.setText(("▾ " if expanded else "▸ ") + "Thông tin chi tiết")

    def _refresh_visibility(self, resolved: dict | None = None) -> None:
        if resolved is None:
            resolved = resolve_person_form(self._document_type, self._role, self.entity_type.currentText())
        visible_names = resolved["visible"]
        for name, field in self.fields.items():
            visible = name in visible_names
            field.setVisible(visible)
            field.set_required(resolved["required"].get(name, False))

        def _as_widget_rows(rows: list[list[tuple[object, int]]]) -> list[list[tuple[QWidget, int]]]:
            widget = lambda item: self.entity_group if item is ENTITY_TYPE_ITEM else self.fields[item]
            return [[(widget(item), span) for item, span in row] for row in rows]

        place_rows(self.primary_grid, _as_widget_rows(resolved["primary_rows"]))
        place_rows(self.detail_grid, _as_widget_rows(resolved["detail_rows"]))
        self.detail_toggle.setVisible(resolved["has_detail"])
        if not resolved["has_detail"]:
            self.detail_toggle.setChecked(False)
        self.expand_detail_if_has_content()

    def expand_detail_if_has_content(self) -> None:
        """Auto-open the detail block if a hidden field already carries data
        (e.g. filled by OCR) or is flagged with a validation error."""
        has_content = any(
            field.isVisible() and (field.value() or field.error.isVisible() or field.is_required())
            for name, field in self.fields.items()
            if person_field_meta(name).tier == FieldTier.DETAIL
        )
        if has_content and self.detail_toggle.isVisible():
            self.detail_toggle.setChecked(True)

    def set_identity_required(self, required: bool) -> None:
        # Kept for the page API; visibility/context now determines required fields.
        if not required:
            for field in self.fields.values():
                field.set_required(False)
        else:
            self._refresh_visibility()

    def set_values(self, values: dict[str, str]) -> None:
        for name, value in values.items():
            if name in self.fields and str(value or "").strip():
                self.fields[name].set_value(value)
        self.expand_detail_if_has_content()

    def set_person(self, person: PersonData) -> None:
        """Replace the complete form while preserving the person's entity type."""
        self.reset_values()
        self.entity_type.setCurrentText(person.entity_type or "Cá nhân")
        self.set_values(asdict(person))

    def reset_values(self) -> None:
        self.entity_type.setCurrentText("Cá nhân")
        for field in self.fields.values():
            field.set_value("")
            field.clear_error()
        self.fields["nationality"].set_value("Việt Nam")
        self.fields["issue_place"].set_value("Cục Cảnh sát QLHC về TTXH")
        self._refresh_visibility()

    def data(self) -> PersonData:
        values = {name: field.value() for name, field in self.fields.items()}
        return PersonData(entity_type=self.entity_type.currentText(), **values)

    def field_map(self) -> dict[str, FieldInput]:
        return {field.path: field for field in self.fields.values()}

    def clear_errors(self) -> None:
        for field in self.fields.values():
            field.clear_error()
