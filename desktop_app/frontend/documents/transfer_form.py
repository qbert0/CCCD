from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from desktop_app.frontend.field_meta import ROW_BREAK, FieldWidth, place_rows, resolve_rows

from .base import BaseDocumentForm

PAYMENT_METHOD_OPTIONS = ["Trả trước", "Trả sau"]
# Sentinel item name for the payment-method selector, packed into this
# form's own row 1 -- not a FIELDS entry, same pattern as
# person_form.ENTITY_TYPE_ITEM.
PAYMENT_METHOD_ITEM = "payment_method"

# (label, name, required, input_kind) -- shared with the web bridge's schema
# resolver, same pattern as PERSON_FIELDS. Row order/grouping is fixed by
# explicit request (see resolve_transfer_form_rows()), not derived from
# FieldTier the way other document types' forms are.
FIELDS = [
    ("Số hợp đồng", "source_contract_number", False, "number"),
    ("Ngày hợp đồng", "source_contract_date", False, "date"),
    ("Ngày Phiếu đăng ký dịch vụ", "registration_form_date", False, "date"),
    ("Giờ chuyển quyền", "transfer_time", False, "text"),
    ("Ngày chuyển quyền có hiệu lực", "transfer_effective_date", True, "date"),
    ("Người đại diện Bên B ký", "provider_representative", False, "text"),
]


def resolve_transfer_form_rows() -> dict:
    """Bespoke, fixed layout for Transfer's own document fields -- by
    explicit request, no "Thông tin chi tiết" disclosure here either.

    Row 1: Hình thức thanh toán, Số hợp đồng, Ngày hợp đồng (payment method
    alongside the pre-existing service contract's own number + date -- a
    date the shop must look up, never auto-filled). Row 2: Ngày Phiếu đăng
    ký dịch vụ trả trước (also never auto-filled). Row 3: Giờ + Ngày chuyển
    quyền -- the moment THIS transfer itself takes effect, which really is
    "now" (see ReportData.transfer_time/transfer_effective_date defaults).
    Row 4: Người đại diện Bên B ký.
    """
    items: list[tuple[object, FieldWidth]] = [
        (PAYMENT_METHOD_ITEM, FieldWidth.SHORT),
        ("source_contract_number", FieldWidth.SHORT),
        ("source_contract_date", FieldWidth.SHORT),
        (ROW_BREAK, FieldWidth.SHORT),
        ("registration_form_date", FieldWidth.SHORT),
        (ROW_BREAK, FieldWidth.SHORT),
        ("transfer_time", FieldWidth.SHORT),
        ("transfer_effective_date", FieldWidth.SHORT),
        (ROW_BREAK, FieldWidth.SHORT),
        ("provider_representative", FieldWidth.SHORT),
    ]
    return {"primary_rows": resolve_rows(items), "detail_rows": [], "has_detail": False}


class TransferForm(BaseDocumentForm):
    """Fields printed in the ownership transfer and liquidation record."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.payment_group = QWidget()
        payment_layout = QVBoxLayout(self.payment_group)
        payment_layout.setContentsMargins(0, 0, 0, 0)
        payment_layout.setSpacing(4)
        label = QLabel('Hình thức thanh toán <span style="color:#cf2d56">*</span>')
        label.setObjectName("fieldLabel")
        self.payment_method = QComboBox()
        self.payment_method.addItems(PAYMENT_METHOD_OPTIONS)
        self.payment_method.setCursor(Qt.PointingHandCursor)
        payment_layout.addWidget(label)
        payment_layout.addWidget(self.payment_method)

        for label_text, name, required, input_kind in FIELDS:
            self.add_field(label_text, name, required=required, input_kind=input_kind)

        self.fields["source_contract_number"].changed.connect(self._refresh_contract_requirement)
        self._refresh_contract_requirement()
        self._pack_rows()

    def _pack_rows(self) -> None:
        rows = resolve_transfer_form_rows()["primary_rows"]
        widget = lambda item: self.payment_group if item is PAYMENT_METHOD_ITEM else self.fields[item]
        place_rows(self.primary_grid, [[(widget(item), span) for item, span in row] for row in rows])
        self.detail_toggle.hide()

    def _refresh_contract_requirement(self) -> None:
        self.fields["source_contract_date"].set_required(
            bool(self.fields["source_contract_number"].value())
        )

    def values(self) -> dict[str, str]:
        return {
            **super().values(),
            "service_action": "Chuyển chủ quyền",
            "payment_method": self.payment_method.currentText(),
        }

    def reset_values(self) -> None:
        super().reset_values()
        self.payment_method.setCurrentIndex(0)
        self._refresh_contract_requirement()
