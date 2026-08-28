from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop_app.frontend.field_meta import FieldWidth, pack_fields, resolve_rows

from .base import BaseDocumentForm

ACTION_OPTIONS = ["Cập nhật thông tin", "Thay SIM", "Chuyển chủ quyền"]
ATTACHMENT_ITEMS = [("has_id_attachment", "CCCD/CMND"), ("has_original_sim", "SIM gốc")]

# Sentinel items for the 2 compound widgets, packed into this form's own
# rows below -- not FIELDS entries, same pattern as PAYMENT_METHOD_ITEM.
ACTION_ITEM = "action"
ATTACHMENTS_ITEM = "attachments"

# Only the free-text companion for the attachment choices is a plain field;
# action and attachments are the two compound controls above.
FIELDS = [
    ("Giấy tờ khác (nêu rõ)", "other_attachment", False, "text"),
]


def resolve_aftersale_form_rows() -> dict:
    """One compact row: requested service, supplied papers, optional other
    paper description. Company and customer identities live in their tabs."""
    items: list[tuple[object, FieldWidth]] = [
        (ACTION_ITEM, FieldWidth.SHORT),
        (ATTACHMENTS_ITEM, FieldWidth.SHORT),
        ("other_attachment", FieldWidth.SHORT),
    ]
    return {"primary_rows": resolve_rows(items), "detail_rows": [], "has_detail": False}


class AftersaleForm(BaseDocumentForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Packed into primary_grid below, alongside attachments_group,
        # instead of each sitting alone on its own row.
        self.action_group = QWidget()
        action_layout = QVBoxLayout(self.action_group)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(4)
        label = QLabel("Dịch vụ yêu cầu")
        label.setObjectName("fieldLabel")
        self.action = QComboBox()
        self.action.addItems(ACTION_OPTIONS)
        self.action.setCursor(Qt.PointingHandCursor)
        action_layout.addWidget(label)
        action_layout.addWidget(self.action)

        self.attachments_group = QWidget()
        attachments_layout = QVBoxLayout(self.attachments_group)
        attachments_layout.setContentsMargins(0, 0, 0, 0)
        attachments_layout.setSpacing(4)
        attachments_label = QLabel("Giấy tờ kèm theo")
        attachments_label.setObjectName("fieldLabel")
        attachments_layout.addWidget(attachments_label)
        checks = QHBoxLayout()
        checks.setSpacing(10)
        self.has_id = QCheckBox("CCCD/CMND")
        self.has_id.setChecked(True)
        self.has_id.setCursor(Qt.PointingHandCursor)
        self.has_sim = QCheckBox("SIM gốc")
        self.has_sim.setCursor(Qt.PointingHandCursor)
        checks.addWidget(self.has_id)
        checks.addWidget(self.has_sim)
        attachments_layout.addLayout(checks)

        for label_text, name, required, input_kind in FIELDS:
            self.add_field(label_text, name, required=required, input_kind=input_kind)

        # One compact row, identical to the web layout.
        pack_fields(self.primary_grid, [
            (self.action_group, FieldWidth.SHORT),
            (self.attachments_group, FieldWidth.SHORT),
            (self.fields["other_attachment"], FieldWidth.SHORT),
        ])

    def values(self) -> dict[str, str | bool]:
        return {
            **super().values(),
            "service_action": self.action.currentText(),
            "has_id_attachment": self.has_id.isChecked(),
            "has_original_sim": self.has_sim.isChecked(),
        }

    def reset_values(self) -> None:
        super().reset_values()
        self.action.setCurrentIndex(0)
        self.has_id.setChecked(True)
        self.has_sim.setChecked(False)
