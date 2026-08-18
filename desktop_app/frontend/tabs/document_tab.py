from __future__ import annotations

from datetime import date

from PyQt5.QtCore import QEvent, QTimer
from PyQt5.QtWidgets import QGridLayout, QStackedWidget, QTextEdit, QVBoxLayout, QWidget

from desktop_app.backend.domain.models import DocumentType
from desktop_app.frontend.components.field_input import FieldInput
from desktop_app.frontend.documents import (
    AftersaleForm,
    BeautifulNumberForm,
    PrepaidContractForm,
    TransferForm,
)
from desktop_app.frontend.field_meta import (
    GRID_COLUMNS,
    FieldWidth,
    document_field_meta,
    pack_fields,
    persistent_document_field_names,
    place_rows,
    resolve_rows,
)


def _grid() -> QGridLayout:
    grid = QGridLayout()
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(11)
    for column in range(GRID_COLUMNS):
        grid.setColumnStretch(column, 1)
    return grid


class _CurrentPageStackedWidget(QStackedWidget):
    """QStackedWidget's default sizeHint is the largest of ALL its pages, not
    just the visible one — so every shorter document form got padded out
    with dead space to match the tallest one, which defeats the point of
    packing each form's own rows tightly.

    sizeHint()/minimumSizeHint() overrides alone turned out not to be
    enough: relying on that value actually propagating back up through
    QStackedWidget -> DocumentTab's QVBoxLayout -> its QScrollArea proved
    unreliable in practice (stale cached heights survived both a page
    switch and an internal resize, like toggling "Thông tin chi tiết").
    So skip the sizeHint negotiation entirely and pin this widget's actual
    height to the current page's need directly, on every page switch and
    every internal layout change of that page."""

    def addWidget(self, widget):
        widget.installEventFilter(self)
        return super().addWidget(widget)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.LayoutRequest and obj is self.currentWidget():
            # Deferred, not called directly here: forcing setFixedHeight()
            # synchronously, re-entrantly, from inside Qt's own handling of
            # this very LayoutRequest event left stale pixels on screen (the
            # widget's geometry/visibility were already correct, but nothing
            # had actually repainted) -- e.g. toggling "Thông tin chi tiết"
            # open left it looking collapsed until some unrelated later
            # interaction forced a repaint. Letting Qt finish the current
            # layout pass first, then syncing on the next event loop tick,
            # avoids that.
            QTimer.singleShot(0, self.sync_height)
        return super().eventFilter(obj, event)

    def sync_height(self):
        current = self.currentWidget()
        if current is not None:
            self.setFixedHeight(current.sizeHint().height())


COMMON_FIELDS = [
    ("Ngày lập tài liệu", "document_date", True, "date"),
    # Up to 3 ordered organization contact numbers, filled once and
    # persisted (OPERATOR-tier, see field_meta.py) instead of retyped per
    # document -- shop_phone is number 1 (kept required where it already
    # was), shop_phone_2/3 are optional extras.
    ("Điện thoại liên hệ 1", "shop_phone", False, "number"),
    ("Điện thoại liên hệ 2", "shop_phone_2", False, "number"),
    ("Điện thoại liên hệ 3", "shop_phone_3", False, "number"),
    ("Nhân viên giao dịch", "staff_name", False, "text"),
    ("Tên cửa hàng/điểm giao dịch", "shop_name", False, "text"),
    ("Địa chỉ cửa hàng", "shop_address", False, "text"),
]
COMMON_VISIBLE_BY_TYPE = {
    DocumentType.TRANSFER: {"document_date"},
    DocumentType.BEAUTIFUL_NUMBER: {"document_date"},
    DocumentType.AFTERSALE: {
        "document_date", "shop_name", "shop_address", "shop_phone", "shop_phone_2", "shop_phone_3", "staff_name",
    },
    DocumentType.PREPAID_CONTRACT: {
        "document_date", "shop_address", "shop_phone", "shop_phone_2", "shop_phone_3", "staff_name",
    },
}
# shop_phone_2/shop_phone_3 are visible wherever shop_phone is, but never
# required -- "tối đa 3 số, các số còn lại có thể bỏ" (up to 3 numbers, the
# rest are optional). Every other visible common field is also required,
# same as before.
COMMON_REQUIRED_BY_TYPE = {
    document_type: names - {"shop_phone_2", "shop_phone_3"}
    for document_type, names in COMMON_VISIBLE_BY_TYPE.items()
}


def resolve_common_rows(document_type: DocumentType) -> dict:
    """Pure equivalent of DocumentTab.set_document_type()'s common-row
    packing -- single source of truth shared with the web bridge's schema
    resolver. Transfer's payment_method now packs into TransferForm's own
    row 1 (alongside source_contract_number/source_contract_date) instead
    of sharing this common row with "Ngày lập tài liệu" -- see
    documents/transfer_form.py's resolve_transfer_form_rows()."""
    visible = COMMON_VISIBLE_BY_TYPE[document_type]
    items: list[tuple[object, FieldWidth]] = [
        (name, document_field_meta(name).width) for _label, name, _required, _kind in COMMON_FIELDS if name in visible
    ]
    return {"rows": resolve_rows(items)}


class DocumentTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 14, 4, 10)
        root.setSpacing(14)
        self.common_grid = _grid()
        self.common: dict[str, FieldInput] = {}
        for label, name, required, input_kind in COMMON_FIELDS:
            field = FieldInput(label, name, required, input_kind=input_kind)
            self.common[name] = field
        pack_fields(self.common_grid, [(f, document_field_meta(name).width) for name, f in self.common.items()])
        self.common["document_date"].set_value(date.today().strftime("%d/%m/%Y"))
        self.common["shop_name"].set_value("Vietnamobile")
        root.addLayout(self.common_grid)
        self.stack = _CurrentPageStackedWidget()
        self.forms = {
            DocumentType.TRANSFER: TransferForm(),
            DocumentType.AFTERSALE: AftersaleForm(),
            DocumentType.BEAUTIFUL_NUMBER: BeautifulNumberForm(),
            DocumentType.PREPAID_CONTRACT: PrepaidContractForm(),
        }
        for form in self.forms.values():
            self.stack.addWidget(form)
        self.stack.sync_height()
        root.addWidget(self.stack)
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Ghi chú nội bộ hoặc nội dung cần kiểm tra thêm")
        self.notes.setMaximumHeight(76)
        root.addWidget(self.notes)
        root.addStretch()

    def set_document_type(self, document_type: DocumentType) -> None:
        self.stack.setCurrentWidget(self.forms[document_type])
        self.stack.sync_height()
        visible = COMMON_VISIBLE_BY_TYPE[document_type]
        required = COMMON_REQUIRED_BY_TYPE[document_type]
        for name, field in self.common.items():
            field.setVisible(name in visible)
            field.set_required(name in required)
        # Transfer's payment_method now packs into TransferForm's own row 1
        # instead of sharing this common row with "Ngày lập tài liệu".
        self.forms[DocumentType.TRANSFER].payment_group.setVisible(document_type == DocumentType.TRANSFER)

        def _widgets(rows: list[list[tuple[object, int]]]) -> list[list[tuple[QWidget, int]]]:
            return [[(self.common[item], span) for item, span in row] for row in rows]

        place_rows(self.common_grid, _widgets(resolve_common_rows(document_type)["rows"]))
        # Transfer's form has no free-text notes concept in its own template.
        self.notes.setVisible(document_type != DocumentType.TRANSFER)

    def active_form(self) -> QWidget:
        return self.stack.currentWidget()

    def values(self) -> dict[str, str]:
        values = {name: field.value() for name, field in self.common.items()}
        values.update(self.active_form().values())
        values["notes"] = self.notes.toPlainText().strip()
        return values

    def field_map(self) -> dict[str, FieldInput]:
        fields = dict(self.common)
        fields.update(self.active_form().field_map())
        return fields

    def all_fields(self) -> dict[str, FieldInput]:
        """Common fields plus every per-document-type field, regardless of
        which form is currently active — used to locate shop/operator
        fields (e.g. prepaid's provider_representative) for persistence."""
        fields = dict(self.common)
        for form in self.forms.values():
            fields.update(form.field_map())
        return fields

    def clear_errors(self) -> None:
        for field in self.common.values():
            field.clear_error()
        for form in self.forms.values():
            form.clear_errors()

    def reset_case(self) -> None:
        persistent_names = set(persistent_document_field_names())
        preserved = {
            name: field.value()
            for name, field in self.all_fields().items()
            if name in persistent_names
        }
        for field in self.common.values():
            field.set_value("")
            field.clear_error()
        self.common["document_date"].set_value(date.today().strftime("%d/%m/%Y"))
        for form in self.forms.values():
            form.reset_values()
        for name, value in preserved.items():
            if value:
                self.all_fields()[name].set_value(value)
        self.notes.clear()
