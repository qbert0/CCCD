from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop_app.frontend.field_meta import FieldWidth, pack_fields

from .base import BaseDocumentForm


class AftersaleForm(BaseDocumentForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Packed into primary_grid below, alongside attachments_group and
        # backup_phone_1, instead of each sitting alone on its own row.
        self.action_group = QWidget()
        action_layout = QVBoxLayout(self.action_group)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(4)
        label = QLabel("Dịch vụ yêu cầu")
        label.setObjectName("fieldLabel")
        self.action = QComboBox()
        self.action.addItems(["Cập nhật thông tin", "Thay SIM", "Chuyển chủ quyền"])
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

        self.add_field("Số điện thoại phối hợp 1", "backup_phone_1", required=True, input_kind="number")
        self.add_field("Giấy tờ khác (nêu rõ)", "other_attachment")
        self.add_field("Số điện thoại phối hợp 2", "backup_phone_2", input_kind="number")

        # Re-pack the primary row: action + attachments + phone together
        # (3 SHORT slots, exact fit) instead of 3 separate almost-empty rows.
        pack_fields(self.primary_grid, [
            (self.action_group, FieldWidth.SHORT),
            (self.attachments_group, FieldWidth.SHORT),
            (self.fields["backup_phone_1"], FieldWidth.SHORT),
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
