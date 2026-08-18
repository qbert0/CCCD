from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from .base import BaseDocumentForm


PAYMENT_METHOD_OPTIONS = ["Trả trước", "Trả sau"]

# (label, name, required, input_kind) -- shared with the web bridge's schema
# resolver, same pattern as PERSON_FIELDS in person_form.py. Order is the
# packing order (see BaseDocumentForm.add_field()/resolve_document_form_rows()).
FIELDS = [
    ("Số hợp đồng", "source_contract_number", False, "number"),
    ("Ngày chuyển quyền có hiệu lực", "transfer_effective_date", True, "date"),
    ("Người đại diện Bên B ký", "provider_representative", False, "text"),
    ("Ngày hợp đồng", "source_contract_date", False, "date"),
    ("Ngày Phiếu đăng ký dịch vụ", "registration_form_date", False, "date"),
    ("Giờ chuyển quyền", "transfer_time", False, "text"),
]


class TransferForm(BaseDocumentForm):
    """Fields printed in the ownership transfer and liquidation record."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # DocumentTab packs this alongside its own "Ngày lập tài liệu" field
        # on the same row (see DocumentTab.set_document_type), so this stays
        # a plain, unparented widget until pack_fields places it there.
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

    def _refresh_contract_requirement(self) -> None:
        self.fields["source_contract_date"].set_required(
            bool(self.fields["source_contract_number"].value())
        )
        self.expand_detail_if_has_content()

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
