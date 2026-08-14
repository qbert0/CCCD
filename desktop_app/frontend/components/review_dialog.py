from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from desktop_app.backend.domain.models import ReportData


class ReviewDialog(QDialog):
    def __init__(self, data: ReportData, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Xác nhận thông tin")
        self.resize(660, 570)
        layout = QVBoxLayout(self)
        heading = QLabel("Kiểm tra lần cuối trước khi tạo tài liệu")
        heading.setObjectName("dialogTitle")
        layout.addWidget(heading)
        guide = QLabel("Đối chiếu các thông tin dưới đây với hai mặt CCCD. Quay lại nếu có bất kỳ sai lệch nào.")
        guide.setWordWrap(True)
        guide.setObjectName("mutedText")
        layout.addWidget(guide)
        summary = QTextEdit()
        summary.setReadOnly(True)
        summary.setPlainText(data.summary())
        layout.addWidget(summary)
        buttons = QDialogButtonBox()
        accept_button = buttons.addButton("Thông tin chính xác", QDialogButtonBox.AcceptRole)
        reject_button = buttons.addButton("Quay lại chỉnh sửa", QDialogButtonBox.RejectRole)
        accept_button.setObjectName("primaryButton")
        reject_button.setObjectName("secondaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
