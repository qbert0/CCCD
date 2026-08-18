from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt5.QtCore import QSettings, QThread, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop_app.backend.config import load_company_profile
from desktop_app.backend.documents import DocumentRegistry
from desktop_app.backend.domain.models import (
    DOCUMENT_NAMES,
    DOCUMENT_SHORT_NAMES,
    DocumentType,
    PersonData,
    ReportData,
)
from desktop_app.backend.ocr import CardSide, OCRFileResult, OCRService, combine_file_results
from desktop_app.backend.paths import default_output_dir
from desktop_app.frontend.components import FieldInput, ImageUploadCard, ReviewDialog
from desktop_app.frontend.field_meta import persistent_document_field_names
from desktop_app.frontend.tabs import DocumentTab, IdentityTab

from .company_profile_page import CompanyProfilePage


class OCRWorker(QThread):
    """Scans exactly one image on its own OS thread. A card that receives
    front+back together gets one OCRWorker per image, started together, so
    whichever image finishes first (front usually resolves almost instantly
    via its QR code; back needs full PaddleOCR text recognition and is much
    slower) shows up first — instead of both waiting on a single queue.
    OCRService.scan_one() never raises, so there's no separate failure signal."""

    completed = pyqtSignal(str, object)

    def __init__(self, target: str, path: Path, parent=None):
        super().__init__(parent)
        self.target = target
        self.path = path

    def run(self) -> None:
        self.completed.emit(self.target, OCRService().scan_one(self.path))


class HomePage(QMainWindow):
    """The application's only page; composed from reusable tabs/components."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CCCD Report · Đọc căn cước và tạo tài liệu")
        self.resize(1400, 900)
        self.registry = DocumentRegistry()
        self.settings = QSettings("CCCDReport", "DesktopApp")
        self.company_profile = load_company_profile(self.settings)
        self._active_document_type: DocumentType | None = None
        self.workers: list[OCRWorker] = []
        self.ocr_text_by_target: dict[str, str] = {}
        self.ocr_side_errors_by_target: dict[str, list[str]] = {}
        self.ocr_identity_warnings_by_target: dict[str, list[str]] = {}
        self._ocr_done_count: dict[str, int] = {}
        self._ocr_total_count: dict[str, int] = {}
        self._ocr_batch_results: dict[str, list[OCRFileResult]] = {}
        self._build_ui()
        self._connect_events()
        self._load_settings()
        self._document_changed()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("pageRoot")
        self.setCentralWidget(root)
        page = QVBoxLayout(root)
        page.setContentsMargins(24, 14, 24, 16)
        page.setSpacing(18)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        # Left margin is 0 so the brand title lines up with the column
        # content below it (which has no extra left inset of its own).
        header_layout.setContentsMargins(0, 8, 8, 8)
        title = QLabel("CCCD Report")
        title.setObjectName("brandTitle")
        subtitle = QLabel("Nhận dạng căn cước và tạo tài liệu")
        subtitle.setObjectName("mutedText")
        brand = QHBoxLayout()
        brand.setSpacing(14)
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header_layout.addLayout(brand)
        header_layout.addStretch()
        self.company_profile_button = QPushButton("Thông tin công ty")
        self.company_profile_button.setObjectName("secondaryButton")
        self.company_profile_button.setCursor(Qt.PointingHandCursor)
        header_layout.addWidget(self.company_profile_button)
        page.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._scan_column())
        splitter.addWidget(self._form_column())
        splitter.setHandleWidth(14)
        splitter.setSizes([410, 970])
        page.addWidget(splitter, 1)
        self.statusBar().showMessage("Sẵn sàng")

    def _scan_column(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(14)

        intake_header = QHBoxLayout()
        intake_header.setSpacing(12)
        self.subscriber_number_field = FieldInput("Số thuê bao", "subscriber_number", required=True)
        self.subscriber_number_field.label.hide()
        # No label above it anymore, so drop the wrapper's own bottom margin
        # too -- otherwise its input sits a few px taller than the button
        # beside it and the row looks uneven.
        self.subscriber_number_field.layout().setContentsMargins(0, 0, 0, 0)
        intake_header.addWidget(self.subscriber_number_field, 1, Qt.AlignVCenter)
        self.refresh_button = QPushButton("↻  Hồ sơ mới")
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.setShortcut("Ctrl+N")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.setToolTip("Xóa dữ liệu hồ sơ hiện tại, giữ lại biểu mẫu và thông tin công ty")
        intake_header.addWidget(self.refresh_button, 0, Qt.AlignVCenter)
        layout.addLayout(intake_header)

        self.customer_upload = ImageUploadCard()
        self.new_owner_upload = ImageUploadCard()
        layout.addWidget(self.customer_upload)
        layout.addWidget(self.new_owner_upload)
        raw_card = QFrame()
        raw_card.setObjectName("ocrCard")
        raw_layout = QVBoxLayout(raw_card)
        raw_layout.setContentsMargins(16, 14, 16, 14)
        raw_layout.setSpacing(10)
        self.raw_toggle = QPushButton("▸ Kết quả OCR")
        self.raw_toggle.setObjectName("disclosureButton")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setCursor(Qt.PointingHandCursor)
        self.raw_toggle.toggled.connect(self._toggle_raw_ocr)
        raw_layout.addWidget(self.raw_toggle)
        self.raw_ocr = QTextEdit()
        self.raw_ocr.setReadOnly(True)
        self.raw_ocr.setPlaceholderText("Văn bản từ CCCD sẽ hiển thị tại đây")
        self.raw_ocr.setMinimumHeight(220)
        self.raw_ocr.setVisible(False)
        raw_layout.addWidget(self.raw_ocr, 1)
        layout.addWidget(raw_card)
        layout.addStretch(1)
        return self._scroll(content)

    def _toggle_raw_ocr(self, expanded: bool) -> None:
        self.raw_ocr.setVisible(expanded)
        self.raw_toggle.setText(("▾ " if expanded else "▸ ") + "Kết quả OCR")

    def _form_column(self) -> QWidget:
        card = QFrame()
        card.setObjectName("contentCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        self.document_combo = QComboBox()
        self.document_combo.setCursor(Qt.PointingHandCursor)
        self.document_combo.setMinimumWidth(420)
        self.document_combo.addItem("Chọn biểu mẫu", "")
        for document_type, name in DOCUMENT_SHORT_NAMES.items():
            self.document_combo.addItem(name, document_type.value)
        layout.addWidget(self.document_combo)
        self.document_full_title = QLabel()
        self.document_full_title.setWordWrap(True)
        self.document_full_title.setObjectName("documentTitle")
        layout.addWidget(self.document_full_title)

        self.tabs = QTabWidget()
        self.customer_tab = IdentityTab("customer", required=True)
        self.new_owner_tab = IdentityTab("new_owner", required=False)
        self.document_tab = DocumentTab()
        self.customer_index = self.tabs.addTab(self._scroll(self.customer_tab), "Khách hàng")
        self.new_owner_index = self.tabs.addTab(self._scroll(self.new_owner_tab), "Chủ thuê bao mới")
        self.document_index = self.tabs.addTab(self._scroll(self.document_tab), "Thông tin tài liệu")
        layout.addWidget(self.tabs, 1)

        # Two real labels, not one label with an inline-styled <div>: the
        # hint's color/size come from #emptyStateHint in theme.py, same as
        # every other muted-caption text -- an inline style here would drift
        # from that shared token the moment either one changes.
        self.document_empty_space = QWidget()
        empty_layout = QVBoxLayout(self.document_empty_space)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(6)
        empty_title = QLabel("Chưa chọn biểu mẫu")
        empty_title.setObjectName("emptyState")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_hint = QLabel("Chọn một loại tài liệu ở trên để bắt đầu điền thông tin")
        empty_hint.setObjectName("emptyStateHint")
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_hint)
        # Alignment (not just stretch) here: a bare stretch=1 would expand
        # this container to fill the whole space top-anchored, losing the
        # vertical centering the single old QLabel got for free from its own
        # AlignCenter -- Qt.AlignCenter keeps the container at its natural
        # size and centers it instead.
        layout.addWidget(self.document_empty_space, 1, Qt.AlignCenter)

        review_actions = QHBoxLayout()
        review_actions.setSpacing(10)
        review_actions.addStretch()
        self.preview_button = QPushButton("Xem trước")
        self.preview_button.setObjectName("secondaryButton")
        self.preview_button.setToolTip("Xem thử tài liệu với dữ liệu hiện có, kể cả khi chưa điền đủ")
        self.export_button = QPushButton("Tạo tài liệu")
        self.export_button.setObjectName("primaryButton")
        review_actions.addWidget(self.preview_button)
        review_actions.addWidget(self.export_button)
        layout.addLayout(review_actions)
        return card

    @staticmethod
    def _scroll(widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(widget)
        return area

    def _connect_events(self) -> None:
        self.document_combo.currentIndexChanged.connect(self._document_changed)
        self.customer_upload.image_requested.connect(lambda: self._select_image("primary"))
        self.new_owner_upload.image_requested.connect(lambda: self._select_image("new_owner"))
        self.customer_upload.files_submitted.connect(self._start_primary_ocr)
        self.new_owner_upload.files_submitted.connect(lambda paths: self._start_ocr("new_owner", paths))
        aftersale = self.document_tab.forms[DocumentType.AFTERSALE]
        aftersale.action.currentTextChanged.connect(self._document_changed)
        self.refresh_button.clicked.connect(self._new_case)
        self.preview_button.clicked.connect(self._preview)
        self.export_button.clicked.connect(self._export)
        self.company_profile_button.clicked.connect(self._open_company_profile_page)

    def _current_type(self) -> DocumentType:
        value = self.document_combo.currentData()
        if not value:
            raise ValueError("Vui lòng chọn loại tài liệu cần tạo")
        return DocumentType(value)

    def _document_changed(self, *_args) -> None:
        value = self.document_combo.currentData()
        ready = bool(value)
        self.tabs.setVisible(ready)
        self.document_full_title.setVisible(ready)
        self.document_empty_space.setVisible(not ready)
        for button in (self.preview_button, self.export_button):
            button.setEnabled(ready)
        if not ready:
            if self._active_document_type in {DocumentType.TRANSFER, DocumentType.AFTERSALE}:
                self._preserve_transfer_subject()
            self._active_document_type = None
            self.new_owner_upload.setVisible(False)
            return
        document_type = self._current_type()
        preserved_subject: PersonData | None = None
        organization_documents = {DocumentType.TRANSFER, DocumentType.AFTERSALE}
        if self._active_document_type in organization_documents and document_type not in organization_documents:
            preserved_subject = self.new_owner_tab.form.data()
        elif self._active_document_type not in organization_documents and document_type in organization_documents:
            preserved_subject = self.customer_tab.form.data()

        self.document_tab.set_document_type(document_type)
        self._apply_provider_defaults(document_type)
        self.document_full_title.setText(DOCUMENT_NAMES[document_type])
        if preserved_subject and self._has_identity(preserved_subject):
            target_form = (
                self.new_owner_tab.form
                if document_type in organization_documents
                else self.customer_tab.form
            )
            target_form.set_person(preserved_subject)
        self.customer_tab.form.configure(document_type, "customer")
        self.new_owner_tab.form.configure(document_type, "new_owner")
        if document_type in organization_documents:
            self._apply_company_profile()

        needs_new = document_type in organization_documents
        self.tabs.setTabVisible(self.new_owner_index, needs_new)
        self.new_owner_upload.setVisible(False if document_type in organization_documents else needs_new)
        self.new_owner_tab.form.set_identity_required(needs_new)
        if document_type == DocumentType.TRANSFER:
            # Transfer is the one document where "customer_tab" actually holds
            # our own company's profile (the party giving up the number) and
            # "new_owner_tab" holds the real, CCCD-scanned customer — so these
            # three tabs get names for that specific structure, not a
            # document-driven "Bên A/Bên C" relabeling of who the customer is.
            self.tabs.setTabText(self.customer_index, "Tổ chức")
            self.tabs.setTabText(self.new_owner_index, "Thuê bao")
            self.tabs.setTabText(self.document_index, "Hợp đồng")
        elif document_type == DocumentType.AFTERSALE:
            self.tabs.setTabText(self.customer_index, "Tổ chức")
            self.tabs.setTabText(self.new_owner_index, "Khách hàng")
            self.tabs.setTabText(self.document_index, "Thông tin tài liệu")
        else:
            self.tabs.setTabText(self.customer_index, "Khách hàng")
            self.tabs.setTabText(self.new_owner_index, "Chủ thuê bao mới")
            self.tabs.setTabText(self.document_index, "Thông tin tài liệu")
        self._active_document_type = document_type

    @staticmethod
    def _has_identity(person: PersonData) -> bool:
        return any(
            str(value or "").strip()
            for value in (
                person.full_name,
                person.organization_name,
                person.id_number,
                person.date_of_birth,
                person.address,
                person.phone,
            )
        )

    def _preserve_transfer_subject(self) -> None:
        subject = self.new_owner_tab.form.data()
        if self._has_identity(subject):
            self.customer_tab.form.set_person(subject)

    def _apply_company_profile(self) -> None:
        self.customer_tab.form.set_person(self.company_profile)
        self.customer_tab.form.configure(DocumentType.TRANSFER, "customer")

    def _apply_provider_defaults(self, document_type: DocumentType) -> None:
        """Pre-fill "who signs for us" (provider_representative/position) from
        the company profile — a per-document override, so it's deliberately
        NOT auto-persisted like the company profile itself (see field_meta:
        these fields are DOCUMENT-tier, not OPERATOR)."""
        if document_type not in (DocumentType.TRANSFER, DocumentType.PREPAID_CONTRACT):
            return
        form = self.document_tab.forms[document_type]
        if "provider_representative" in form.fields:
            form.fields["provider_representative"].set_value(self.company_profile.representative_name)
        if "provider_position" in form.fields:
            form.fields["provider_position"].set_value(self.company_profile.representative_position)

    def _open_company_profile_page(self) -> None:
        page = CompanyProfilePage(self.settings, self)
        page.profile_saved.connect(self._company_profile_saved)
        page.exec_()

    def _company_profile_saved(self, person: PersonData) -> None:
        self.company_profile = person
        self._apply_shop_defaults()
        if self.document_combo.currentData() in {
            DocumentType.TRANSFER.value, DocumentType.AFTERSALE.value,
        }:
            self._apply_company_profile()
        if self.document_combo.currentData():
            self._apply_provider_defaults(self._current_type())
        self.statusBar().showMessage("Đã lưu và cập nhật thông tin công ty")

    def _start_primary_ocr(self, paths: list[Path]) -> None:
        target = (
            "new_owner"
            if self.document_combo.currentData() in {
                DocumentType.TRANSFER.value, DocumentType.AFTERSALE.value,
            }
            else "customer"
        )
        self._start_ocr(target, paths)

    def _select_image(self, target: str) -> None:
        if self._ocr_busy():
            QMessageBox.information(self, "Đang nhận dạng", "Vui lòng chờ lần quét hiện tại hoàn tất.")
            return
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn ảnh CCCD (có thể chọn cả 2 mặt cùng lúc)",
            "",
            "Ảnh CCCD (*.jpg *.jpeg *.png *.bmp *.webp)",
        )
        if not selected:
            return
        card = self.customer_upload if target == "primary" else self.new_owner_upload
        card.submit_files([Path(item) for item in selected])

    def _upload_card_for_target(self, target: str) -> ImageUploadCard:
        if target == "customer":
            return self.customer_upload
        if self.document_combo.currentData() in {
            DocumentType.TRANSFER.value, DocumentType.AFTERSALE.value,
        }:
            return self.customer_upload
        return self.new_owner_upload

    def _ocr_busy(self) -> bool:
        return any(worker.isRunning() for worker in self.workers)

    def _start_ocr(self, target: str, paths: list[Path]) -> None:
        if not paths:
            return
        if self._ocr_busy():
            QMessageBox.information(self, "Đang nhận dạng", "Vui lòng chờ lần quét hiện tại hoàn tất.")
            return
        self._set_busy(True)
        card = self._upload_card_for_target(target)
        self._ocr_done_count[target] = 0
        self._ocr_total_count[target] = len(paths)
        self._ocr_batch_results[target] = []
        card.set_scan_progress(0, len(paths))
        self.statusBar().showMessage("Đang đọc song song tất cả các mặt CCCD…")
        for path in paths:
            worker = OCRWorker(target, path, self)
            worker.completed.connect(self._ocr_file_completed)
            self.workers.append(worker)
            worker.start()

    def _set_busy(self, busy: bool) -> None:
        self.customer_upload.set_busy(busy)
        self.new_owner_upload.set_busy(busy)
        self.document_combo.setEnabled(not busy)
        self.company_profile_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)

    def _ocr_file_completed(self, target: str, file_result: OCRFileResult) -> None:
        """React to a single image's OCR result the moment its own thread
        finishes — front (usually a near-instant QR decode) commonly beats
        back (full PaddleOCR text recognition) by a wide margin, so it shows
        up first regardless of submission order. Once every image from this
        batch has reported in, run the authoritative merge."""
        worker = self.sender()
        if worker in self.workers:
            self.workers.remove(worker)

        card = self._upload_card_for_target(target)
        form = self.customer_tab.form if target == "customer" else self.new_owner_tab.form
        if card.accept_result(file_result):
            form.set_values(file_result.fields)
        self._refresh_raw_ocr_panel(target, fallback_raw_text=file_result.raw_text)

        self._ocr_batch_results.setdefault(target, []).append(file_result)
        self._ocr_done_count[target] = self._ocr_done_count.get(target, 0) + 1
        done = self._ocr_done_count[target]
        total = self._ocr_total_count.get(target, done)
        card.set_scan_progress(done, total)
        if done >= total:
            self._finish_ocr_batch(target)

    def _refresh_raw_ocr_panel(self, target: str, fallback_raw_text: str = "") -> None:
        """Rebuild the "Kết quả OCR" text panel for `target` from whatever's
        been accepted onto the card so far. Called both per-image (so the
        panel updates the instant that image's OCR is ready) and once more
        after the whole batch settles (so warnings/merge corrections land)."""
        card = self._upload_card_for_target(target)
        accepted_files = card.file_results()
        current_raw = "\n\n".join(item.raw_text for item in accepted_files if item.raw_text) or fallback_raw_text
        section_title = "KHÁCH HÀNG" if target == "customer" else "CHỦ THUÊ BAO MỚI"
        section = f"===== {section_title} =====\n{current_raw}"
        self.ocr_text_by_target[target] = section
        self.raw_ocr.setPlainText("\n\n".join(self.ocr_text_by_target.values()))
        self.raw_toggle.setChecked(True)

    def _finish_ocr_batch(self, target: str) -> None:
        card = self._upload_card_for_target(target)
        form = self.customer_tab.form if target == "customer" else self.new_owner_tab.form
        batch_files = self._ocr_batch_results.pop(target, [])
        card.clear_scan_progress()

        try:
            result = combine_file_results(batch_files)
        except RuntimeError as exc:
            # Every image in this batch failed to recognize at all.
            self._ocr_batch_failed(target, str(exc))
            return

        accepted = any(not item.error and item.side != CardSide.UNKNOWN for item in batch_files)
        if accepted:
            # Per-file thumbnail/field updates already ran as each image
            # finished (_ocr_file_completed); re-derive the authoritative
            # merge from the card's current zones, since one side may have
            # been accepted in an earlier, separate scan.
            result = combine_file_results(card.file_results())
            # Rebuild from the two current preview slots, so replacing one side
            # cannot leave stale identity fields from the removed image.
            form.reset_values()
            form.set_values(result.fields)

        identity_warnings = [
            warning for warning in result.warnings or []
            if warning.startswith("Nguy cơ ảnh CCCD không hợp lệ")
        ]
        self.ocr_identity_warnings_by_target[target] = identity_warnings
        if accepted:
            card.set_identity_warning("\n".join(identity_warnings))
        self.ocr_side_errors_by_target[target] = []
        self._refresh_raw_ocr_panel(target, fallback_raw_text=result.raw_text)
        self._set_busy(False)
        self.tabs.setCurrentIndex(self.customer_index if target == "customer" else self.new_owner_index)
        if identity_warnings:
            # The inline note on the upload card (set above via
            # card.set_identity_warning) already carries this message —
            # no need to also block with a modal dialog.
            self.statusBar().showMessage("Hai mặt CCCD có nguy cơ không cùng người · cần kiểm tra lại")
        elif not accepted:
            self.statusBar().showMessage("Chưa nhận biết được mặt CCCD · ảnh hiện có vẫn được giữ")
        elif result.warnings:
            self.statusBar().showMessage(
                "Đã lấy được dữ liệu nhưng có ảnh đọc lỗi · kiểm tra trạng thái và văn bản đối chiếu"
            )
        else:
            self.statusBar().showMessage("Đã đọc xong các mặt CCCD · hãy đối chiếu những trường vừa điền")

    def _ocr_batch_failed(self, target: str, message: str) -> None:
        card = self._upload_card_for_target(target)
        card.status.setText("Không đọc được ảnh mới")
        card.status.setProperty("invalid", True)
        card.note.setText(message + "\nẢnh đã nhận diện trước đó vẫn được giữ nguyên.")
        card.note.setProperty("invalid", True)
        card.note.show()
        card._refresh_status_style()
        self._set_busy(False)
        self.statusBar().showMessage("Không đọc được CCCD")
        QMessageBox.critical(self, "Lỗi nhận dạng CCCD", message)

    def _collect_data(self) -> ReportData:
        return ReportData(
            document_type=self._current_type(),
            customer=self.customer_tab.form.data(),
            new_owner=self.new_owner_tab.form.data(),
            subscriber_number=self.subscriber_number_field.value(),
            **self.document_tab.values(),
        )

    def _field_map(self):
        return {
            **self.customer_tab.form.field_map(),
            **self.new_owner_tab.form.field_map(),
            **self.document_tab.field_map(),
            "subscriber_number": self.subscriber_number_field,
        }

    def _validated_data(self) -> ReportData | None:
        self.customer_tab.form.clear_errors()
        self.new_owner_tab.form.clear_errors()
        self.document_tab.clear_errors()
        if self.document_combo.currentData() in {
            DocumentType.TRANSFER.value, DocumentType.AFTERSALE.value,
        }:
            active_side_errors = list(self.ocr_side_errors_by_target.get("new_owner", []))
        else:
            active_side_errors = list(self.ocr_side_errors_by_target.get("customer", []))
        if (
            self.new_owner_upload.isVisible()
            and self.document_combo.currentData() not in {
                DocumentType.TRANSFER.value, DocumentType.AFTERSALE.value,
            }
        ):
            active_side_errors += self.ocr_side_errors_by_target.get("new_owner", [])
        if active_side_errors:
            # Already visible inline as the red "SAI ẢNH" badge/note on the
            # relevant upload card — the status bar is enough, no modal.
            self.statusBar().showMessage(
                "Không thể tiếp tục: có ảnh CCCD đang nằm sai khung · xem khung ảnh được đánh dấu đỏ"
            )
            return None
        data = self._collect_data()
        errors = self.registry.for_data(data).check(data)
        if not errors:
            return data
        fields = self._field_map()
        first_path = errors[0].path
        for error in errors:
            if error.path in fields:
                fields[error.path].set_error(error.message)
        if first_path == "subscriber_number":
            pass  # already visible in the left column, no tab switch needed
        elif first_path.startswith("customer."):
            self.tabs.setCurrentIndex(self.customer_index)
        elif first_path.startswith("new_owner."):
            self.tabs.setCurrentIndex(self.new_owner_index)
        else:
            self.tabs.setCurrentIndex(self.document_index)
        self.statusBar().showMessage(f"Còn {len(errors)} trường cần bổ sung · xem thông báo màu đỏ dưới ô nhập")
        return None

    def _confirm(self) -> ReportData | None:
        data = self._validated_data()
        if data is None:
            return None
        return data if ReviewDialog(data, self).exec_() == QDialog.Accepted else None

    def _preview(self) -> None:
        # Deliberately skipped validation: a preview shows the template with
        # whatever data currently exists — even blank — so staff can check
        # layout without first satisfying every required field. Only "Tạo
        # tài liệu" actually requires a clean check (via _confirm below).
        data = self._collect_data()
        try:
            output = self.registry.for_data(data).preview(data, Path(tempfile.gettempdir()) / "CCCDReportPreview")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output)))
            self.statusBar().showMessage(f"Đã mở bản xem trước: {output.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Không tạo được bản xem trước", str(exc))

    def _export(self) -> None:
        data = self._confirm()
        if data is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu tài liệu", str(default_output_dir()))
        if not folder:
            return
        try:
            output = self.registry.for_data(data).generate(data, Path(folder))
            customer_name = data.customer.display_name()
            QMessageBox.information(self, "Tạo tài liệu thành công", f"Đã lưu:\n{output}")
            hint = (
                f" · Tạo tài liệu khác cho {customer_name}? Chọn ở trên."
                if customer_name
                else ""
            )
            self.statusBar().showMessage(f"Đã tạo {output.name}{hint}")
        except Exception as exc:
            QMessageBox.critical(self, "Không tạo được tài liệu", str(exc))

    def _new_case(self) -> None:
        if self._ocr_busy():
            return
        self.customer_upload.clear_files()
        self.new_owner_upload.clear_files()
        self.customer_tab.form.reset_values()
        self.new_owner_tab.form.reset_values()
        self.document_tab.reset_case()
        self.subscriber_number_field.set_value("")
        self.subscriber_number_field.clear_error()
        self._apply_shop_defaults()
        self.ocr_text_by_target.clear()
        self.ocr_side_errors_by_target.clear()
        self.ocr_identity_warnings_by_target.clear()
        self.raw_ocr.clear()
        self.raw_toggle.setChecked(False)
        self.tabs.setCurrentIndex(self.customer_index)
        self._document_changed()
        if self.document_combo.currentData() in {
            DocumentType.TRANSFER.value, DocumentType.AFTERSALE.value,
        }:
            self._apply_company_profile()
        self.statusBar().showMessage("Đã mở hồ sơ mới · biểu mẫu và thông tin cửa hàng được giữ lại")

    def _apply_shop_defaults(self) -> None:
        """Pre-fill the shop name/address from the company profile — editing
        them for one document does not write back here (no auto-persist),
        only CompanyProfilePage's explicit save does. shop_phone is NOT
        included: it's not shown on every document type, and it's an
        OPERATOR field now (see field_meta.py), so it's simply remembered
        across cases via QSettings like staff_name instead."""
        common = self.document_tab.common
        common["shop_name"].set_value(self.company_profile.organization_name)
        common["shop_address"].set_value(self.company_profile.headquarters_address)

    def _load_settings(self) -> None:
        self._apply_shop_defaults()
        fields = self.document_tab.all_fields()
        for name in persistent_document_field_names():
            value = self.settings.value(name, "")
            if value and name in fields:
                fields[name].set_value(str(value))

    def closeEvent(self, event) -> None:
        fields = self.document_tab.all_fields()
        for name in persistent_document_field_names():
            if name in fields:
                self.settings.setValue(name, fields[name].value())
        super().closeEvent(event)
