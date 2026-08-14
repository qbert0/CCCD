from __future__ import annotations

from PyQt5.QtCore import QSettings, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop_app.backend.config import load_company_profile, save_company_profile
from desktop_app.backend.domain.models import DocumentType, PersonData, ReportData
from desktop_app.backend.validation.rules import party_required, person_errors, required_errors
from desktop_app.frontend.components import PersonForm


class CompanyProfilePage(QDialog):
    """Editable, explicit-save-only company profile — fixed info reused as
    the default for every document (shop name/address/phone, and the "Bên A"
    / signing-representative identity where a document needs the company as
    a party). Saving here is the only way this default changes; per-document
    overrides on the review screen never write back to it."""

    profile_saved = pyqtSignal(object)

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Thông tin công ty")
        # The form's natural content is ~550px tall; the old 760px left a
        # large dead gap between the fields and the Lưu/Hủy buttons below.
        self.resize(900, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)

        heading = QLabel("Thông tin công ty")
        heading.setObjectName("dialogTitle")
        layout.addWidget(heading)
        note = QLabel(
            "Thông tin cố định của công ty, ít thay đổi — tự áp dụng làm mặc định cho mọi "
            "tài liệu (Bên A, người đại diện ký...). Sửa riêng cho một tài liệu cụ thể ở màn "
            "hình kiểm tra thông tin sẽ không ghi đè lên hồ sơ mặc định này."
        )
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.form = PersonForm("customer")
        self.form.configure(DocumentType.TRANSFER, "customer")
        self.form.entity_type.setCurrentText("Tổ chức")
        self.form.entity_type.setEnabled(False)
        self.form.set_person(load_company_profile(settings))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.form)
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox()
        save_button = buttons.addButton("Lưu thông tin công ty", QDialogButtonBox.AcceptRole)
        cancel_button = buttons.addButton("Hủy", QDialogButtonBox.RejectRole)
        save_button.setObjectName("primaryButton")
        cancel_button.setObjectName("secondaryButton")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.form.clear_errors()
        person = self.form.data()
        person.entity_type = "Tổ chức"
        report = ReportData(document_type=DocumentType.TRANSFER, customer=person)
        required = party_required("customer", person) + [
            "customer.date_of_birth",
            "customer.address",
            "customer.nationality",
        ]
        errors = required_errors(report, required)
        errors += person_errors(
            "customer",
            person,
            {"id_number", "date_of_birth", "issue_date", "authorization_date"},
        )
        fields = self.form.field_map()
        for error in errors:
            field = fields.get(error.path)
            if field:
                field.set_error(error.message)
        if errors:
            return
        save_company_profile(self.settings, person)
        self.profile_saved.emit(person)
        self.accept()
