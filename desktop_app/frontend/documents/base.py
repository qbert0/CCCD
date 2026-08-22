from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget

from desktop_app.frontend.components.field_input import FieldInput
from desktop_app.frontend.field_meta import (
    GRID_COLUMNS,
    FieldTier,
    document_field_meta,
    pack_fields,
    resolve_rows,
)


def _grid() -> QGridLayout:
    grid = QGridLayout()
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(11)
    for column in range(GRID_COLUMNS):
        grid.setColumnStretch(column, 1)
    return grid


def resolve_document_form_rows(field_names: list[str]) -> dict:
    """Pure split of `field_names` (in insertion order, as `add_field()` was/
    would be called) into primary/detail row layouts, purely from each
    name's `document_field_meta().tier`/`.width` -- no QWidget involved.
    Single source of truth for how a document form's fields pack, shared by
    `BaseDocumentForm.add_field()` below and the web bridge's schema
    resolver."""
    primary_names = [n for n in field_names if document_field_meta(n).tier != FieldTier.DETAIL]
    detail_names = [n for n in field_names if document_field_meta(n).tier == FieldTier.DETAIL]
    return {
        "primary_rows": resolve_rows([(n, document_field_meta(n).width) for n in primary_names]),
        "detail_rows": resolve_rows([(n, document_field_meta(n).width) for n in detail_names]),
        "has_detail": bool(detail_names),
    }


class BaseDocumentForm(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        # No top margin: nothing sits above primary_grid here anymore (no
        # form uses a header block), so any top inset would just be dead
        # space stacking on top of DocumentTab's own row spacing above it.
        outer.setContentsMargins(0, 0, 0, 8)
        outer.setSpacing(10)

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
        # Sitting inside a QStackedWidget/QScrollArea, this form sometimes
        # gets allocated more height than its content currently needs (most
        # visibly right after the detail section collapses back down). With
        # nothing here to claim that leftover space, Qt distributed it into
        # primary_grid's own rows instead, stretching every field tall and
        # ugly. This stretch claims it instead, so the grid rows always stay
        # at their natural height regardless of how much extra room the form
        # itself is handed.
        outer.addStretch(1)

        self.fields: dict[str, FieldInput] = {}
        self._primary_fields: list[FieldInput] = []
        self._detail_fields: list[FieldInput] = []

    def _toggle_detail(self, expanded: bool) -> None:
        self._detail_container.setVisible(expanded)
        self.detail_toggle.setText(("▾ " if expanded else "▸ ") + "Thông tin chi tiết")
        self.detail_toggle.setVisible(True)

    def add_field(self, label: str, name: str, required: bool = False, input_kind: str = "text") -> FieldInput:
        field = FieldInput(label, name, required, input_kind=input_kind)
        self.fields[name] = field
        meta = document_field_meta(name)
        if meta.tier == FieldTier.DETAIL:
            self._detail_fields.append(field)
            pack_fields(self.detail_grid, [(f, document_field_meta(f.path).width) for f in self._detail_fields])
            self.detail_toggle.show()
        else:
            self._primary_fields.append(field)
            pack_fields(self.primary_grid, [(f, document_field_meta(f.path).width) for f in self._primary_fields])
        return field

    def expand_detail_if_has_content(self) -> None:
        has_content = any(
            document_field_meta(name).tier == FieldTier.DETAIL
            and (field.value() or field.error.isVisible() or field.is_required())
            for name, field in self.fields.items()
        )
        if has_content and self.detail_toggle.isVisible():
            self.detail_toggle.setChecked(True)

    def values(self) -> dict[str, str]:
        return {name: field.value() for name, field in self.fields.items()}

    def field_map(self) -> dict[str, FieldInput]:
        return dict(self.fields)

    def clear_errors(self) -> None:
        for field in self.fields.values():
            field.clear_error()

    def reset_values(self) -> None:
        for field in self.fields.values():
            field.set_value("")
            field.clear_error()
