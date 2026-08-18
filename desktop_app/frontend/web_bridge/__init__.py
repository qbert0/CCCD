"""The QWebChannel bridge object: the only thing Python and the web view
talk to each other through. Business logic (OCR, validation, document
generation, field layout) is never duplicated here -- every slot below is a
thin adapter calling straight into desktop_app.backend/desktop_app.frontend's
existing pure functions and Qt services.
"""

from __future__ import annotations

import base64
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from PyQt5.QtCore import QObject, QSettings, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from desktop_app.backend.config.company_profile import load_company_profile, save_company_profile
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
from desktop_app.backend.validation.rules import person_errors, party_required, required_errors
from desktop_app.frontend.field_meta import persistent_document_field_names
from desktop_app.frontend.web_bridge.dto import (
    errors_to_json,
    has_identity,
    person_from_dict,
    person_with_defaults_overlay,
    thumbnail_data_url,
)
from desktop_app.frontend.web_bridge.schema import (
    SUBSCRIBER_NUMBER_FIELD,
    resolve_document_tab_layout,
    resolve_person_layout,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _needs_new_owner(document_type: DocumentType, service_action: str) -> bool:
    return document_type == DocumentType.TRANSFER or (
        document_type == DocumentType.AFTERSALE and service_action == "Chuyển chủ quyền"
    )


class WebBridge(QObject):
    ocrProgress = pyqtSignal(str, int, int)
    ocrFileResult = pyqtSignal(str, str)
    ocrBatchFinished = pyqtSignal(str, str)
    ocrBatchFailed = pyqtSignal(str, str)

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window  # QMainWindow, for QFileDialog/QMessageBox parenting
        self.settings = QSettings("CCCDReport", "DesktopApp")
        self.registry = DocumentRegistry()
        self.company_profile = load_company_profile(self.settings)

        self._active_document_type: DocumentType | None = None
        self._service_action = "Cập nhật thông tin"
        self.workers: list = []
        self._accepted_files: dict[str, dict[CardSide, OCRFileResult]] = {"customer": {}, "new_owner": {}}
        self._ocr_done_count: dict[str, int] = {}
        self._ocr_total_count: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def _default_report_dict(self) -> dict:
        data = asdict(ReportData(document_type=DocumentType.TRANSFER))
        data["document_type"] = ""
        data["shop_name"] = self.company_profile.organization_name
        data["shop_address"] = self.company_profile.headquarters_address
        for name in persistent_document_field_names():
            value = self.settings.value(name, "")
            if value:
                data[name] = str(value)
        return data

    @pyqtSlot(result=str)
    def get_initial_state(self) -> str:
        return json.dumps(
            {
                "state": self._default_report_dict(),
                "document_type_options": [
                    {"value": dt.value, "label": name} for dt, name in DOCUMENT_SHORT_NAMES.items()
                ],
            }
        )

    # ------------------------------------------------------------------
    # Document type / entity type structural recompute
    # ------------------------------------------------------------------

    @pyqtSlot(str, result=str)
    def on_document_type_changed(self, request_json: str) -> str:
        request = json.loads(request_json)
        previous_raw = request.get("previous_document_type") or ""
        new_raw = request.get("new_document_type") or ""
        state = request["state"]
        previous = DocumentType(previous_raw) if previous_raw else None
        document_type = DocumentType(new_raw) if new_raw else None

        state_patch: dict = {}
        ready = document_type is not None

        if not ready:
            if previous == DocumentType.TRANSFER:
                subject = person_from_dict(state.get("new_owner", {}))
                if has_identity(subject):
                    state_patch["customer"] = asdict(person_with_defaults_overlay(subject))
            self._active_document_type = None
            return json.dumps(
                {
                    "state_patch": state_patch,
                    "ui": {"ready": False, "documentFullTitle": "", "tabs": self._tab_ui(None, False)},
                    "layouts": self._empty_layouts(),
                }
            )

        preserved_subject: PersonData | None = None
        if previous == DocumentType.TRANSFER and document_type != DocumentType.TRANSFER:
            preserved_subject = person_from_dict(state.get("new_owner", {}))
        elif previous != DocumentType.TRANSFER and document_type == DocumentType.TRANSFER:
            preserved_subject = person_from_dict(state.get("customer", {}))

        customer = person_from_dict(state.get("customer", {}))
        new_owner = person_from_dict(state.get("new_owner", {}))

        if preserved_subject is not None and has_identity(preserved_subject):
            target = person_with_defaults_overlay(preserved_subject)
            if document_type == DocumentType.TRANSFER:
                new_owner = target
            else:
                customer = target

        if document_type == DocumentType.TRANSFER:
            customer = self.company_profile

        state_patch["customer"] = asdict(customer)
        state_patch["new_owner"] = asdict(new_owner)

        if document_type in (DocumentType.TRANSFER, DocumentType.PREPAID_CONTRACT):
            state_patch["provider_representative"] = self.company_profile.representative_name
            if document_type == DocumentType.PREPAID_CONTRACT:
                state_patch["provider_position"] = self.company_profile.representative_position

        service_action = state.get("service_action") or "Cập nhật thông tin"
        needs_new = _needs_new_owner(document_type, service_action)

        self._active_document_type = document_type
        self._service_action = service_action

        customer_layout = resolve_person_layout("customer", document_type, "customer", customer.entity_type)
        new_owner_layout = resolve_person_layout("new_owner", document_type, "new_owner", new_owner.entity_type)
        if not needs_new:
            new_owner_layout["primary_rows"] = _zero_required(new_owner_layout["primary_rows"])
            new_owner_layout["detail_rows"] = _zero_required(new_owner_layout["detail_rows"])

        return json.dumps(
            {
                "state_patch": state_patch,
                "ui": {
                    "ready": True,
                    "documentFullTitle": DOCUMENT_NAMES[document_type],
                    "tabs": self._tab_ui(document_type, needs_new),
                },
                "layouts": {
                    "customer": customer_layout,
                    "new_owner": new_owner_layout,
                    "document": resolve_document_tab_layout(document_type),
                },
            }
        )

    @staticmethod
    def _tab_ui(document_type: DocumentType | None, needs_new: bool) -> dict:
        if document_type == DocumentType.TRANSFER:
            return {
                "customerLabel": "Tổ chức", "newOwnerLabel": "Thuê bao", "documentLabel": "Hợp đồng",
                "newOwnerTabVisible": needs_new, "newOwnerUploadVisible": False,
            }
        return {
            "customerLabel": "Khách hàng", "newOwnerLabel": "Chủ thuê bao mới", "documentLabel": "Thông tin tài liệu",
            "newOwnerTabVisible": needs_new, "newOwnerUploadVisible": needs_new,
        }

    @staticmethod
    def _empty_layouts() -> dict:
        empty = {"primary_rows": [], "detail_rows": [], "has_detail": False, "allow_entity": False}
        return {"customer": empty, "new_owner": empty, "document": {"common_rows": [], "primary_rows": [], "detail_rows": [], "has_detail": False, "notes_field": None}}

    @pyqtSlot(str, str, result=str)
    def on_entity_type_changed(self, form: str, entity_type: str) -> str:
        if self._active_document_type is None:
            return json.dumps({"primary_rows": [], "detail_rows": [], "has_detail": False, "allow_entity": False})
        layout = resolve_person_layout(form, self._active_document_type, form, entity_type)
        if form == "new_owner" and not _needs_new_owner(self._active_document_type, self._service_action):
            layout["primary_rows"] = _zero_required(layout["primary_rows"])
            layout["detail_rows"] = _zero_required(layout["detail_rows"])
        return json.dumps(layout)

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------

    def _ocr_busy(self) -> bool:
        return any(worker.isRunning() for worker in self.workers)

    @pyqtSlot(str)
    def select_and_scan_images(self, target: str) -> None:
        if self._ocr_busy():
            QMessageBox.information(self.window, "Đang nhận dạng", "Vui lòng chờ lần quét hiện tại hoàn tất.")
            return
        selected, _ = QFileDialog.getOpenFileNames(
            self.window, "Chọn ảnh CCCD (có thể chọn cả 2 mặt cùng lúc)", "", "Ảnh CCCD (*.jpg *.jpeg *.png *.bmp *.webp)"
        )
        if selected:
            self._start_ocr(target, [Path(p) for p in selected])

    @pyqtSlot(str, str, str)
    def submit_dropped_image(self, target: str, filename: str, base64_data: str) -> None:
        suffix = Path(filename).suffix.casefold() or ".jpg"
        if suffix not in IMAGE_SUFFIXES:
            return
        tmp = Path(tempfile.gettempdir()) / f"cccd_drop_{next(tempfile._get_candidate_names())}{suffix}"
        tmp.write_bytes(base64.b64decode(base64_data))
        self._start_ocr(target, [tmp])

    def _start_ocr(self, target: str, paths: list[Path]) -> None:
        if not paths:
            return
        if self._ocr_busy():
            QMessageBox.information(self.window, "Đang nhận dạng", "Vui lòng chờ lần quét hiện tại hoàn tất.")
            return
        from desktop_app.frontend.pages.home_page import OCRWorker as _OCRWorker

        self._ocr_done_count[target] = 0
        self._ocr_total_count[target] = len(paths)
        self.ocrProgress.emit(target, 0, len(paths))
        for path in paths:
            worker = _OCRWorker(target, path, self)
            worker.completed.connect(self._ocr_file_completed)
            self.workers.append(worker)
            worker.start()

    def _ocr_file_completed(self, target: str, file_result: OCRFileResult) -> None:
        worker = self.sender()
        if worker in self.workers:
            self.workers.remove(worker)

        accepted = not file_result.error and file_result.side != CardSide.UNKNOWN
        if accepted:
            self._accepted_files[target][file_result.side] = file_result

        payload = {
            "accepted": accepted,
            "side": file_result.side.value,
            "fields": file_result.fields if accepted else {},
            "error": file_result.error,
            "filename": file_result.path.name,
            "source": file_result.source,
            "thumbnail_data_url": thumbnail_data_url(file_result.path) if accepted else "",
        }
        self.ocrFileResult.emit(target, json.dumps(payload))

        self._ocr_done_count[target] = self._ocr_done_count.get(target, 0) + 1
        done = self._ocr_done_count[target]
        total = self._ocr_total_count.get(target, done)
        self.ocrProgress.emit(target, done, total)
        if done >= total:
            self._finish_ocr_batch(target)

    def _finish_ocr_batch(self, target: str) -> None:
        current_files = list(self._accepted_files[target].values())
        try:
            result = combine_file_results(current_files) if current_files else None
        except RuntimeError as exc:
            self.ocrBatchFailed.emit(target, str(exc))
            return

        accepted = result is not None
        identity_warnings = [
            w for w in (result.warnings or []) if w.startswith("Nguy cơ ảnh CCCD không hợp lệ")
        ] if result else []

        self.ocrBatchFinished.emit(
            target,
            json.dumps(
                {
                    "accepted": accepted,
                    "fields": result.fields if result else {},
                    "warnings": identity_warnings if identity_warnings else (result.warnings if result else []),
                    "raw_text": result.raw_text if result else "",
                }
            ),
        )

    # ------------------------------------------------------------------
    # Validate / preview / export
    # ------------------------------------------------------------------

    def _report_data_from_state(self, state: dict) -> ReportData:
        data = dict(state)
        data["document_type"] = DocumentType(data["document_type"])
        data["customer"] = person_from_dict(data.get("customer", {}))
        data["new_owner"] = person_from_dict(data.get("new_owner", {}))
        valid = {f for f in ReportData.__dataclass_fields__}
        return ReportData(**{k: v for k, v in data.items() if k in valid})

    @pyqtSlot(str, result=str)
    def validate(self, state_json: str) -> str:
        data = self._report_data_from_state(json.loads(state_json))
        errors = self.registry.for_data(data).check(data)
        return errors_to_json(errors)

    @pyqtSlot(str, result=str)
    def get_review_summary(self, state_json: str) -> str:
        data = self._report_data_from_state(json.loads(state_json))
        return json.dumps(data.summary())

    @pyqtSlot(str, result=str)
    def preview_document(self, state_json: str) -> str:
        data = self._report_data_from_state(json.loads(state_json))
        try:
            output = self.registry.for_data(data).preview(data, Path(tempfile.gettempdir()) / "CCCDReportPreview")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output)))
            return json.dumps({"ok": True, "message": f"Đã mở bản xem trước: {output.name}"})
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user as-is, same as the old QMessageBox.critical
            return json.dumps({"ok": False, "message": str(exc)})

    @pyqtSlot(str, result=str)
    def export_document(self, state_json: str) -> str:
        data = self._report_data_from_state(json.loads(state_json))
        folder = QFileDialog.getExistingDirectory(self.window, "Chọn thư mục lưu tài liệu", str(default_output_dir()))
        if not folder:
            return json.dumps({"ok": False, "message": ""})
        try:
            output = self.registry.for_data(data).generate(data, Path(folder))
            return json.dumps({"ok": True, "path": str(output)})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "message": str(exc)})

    @pyqtSlot(str, result=str)
    def new_case(self, state_json: str) -> str:
        """Equivalent of HomePage._new_case(): fresh customer/new_owner/
        document defaults, but persistent OPERATOR-tier fields (staff_name,
        shop_phone) and the document type itself survive, exactly like the
        old "Hồ sơ mới" button. The caller (JS) still needs to re-run
        on_document_type_changed itself afterwards to refresh layouts/tabs/
        company-profile application -- this slot only resets the data."""
        state = json.loads(state_json)
        fresh = self._default_report_dict()
        fresh["document_type"] = state.get("document_type", "")
        self._accepted_files = {"customer": {}, "new_owner": {}}
        return json.dumps(fresh)

    @pyqtSlot(str)
    def persist_operator_fields(self, state_json: str) -> None:
        state = json.loads(state_json)
        for name in persistent_document_field_names():
            if name in state:
                self.settings.setValue(name, state[name])

    # ------------------------------------------------------------------
    # Company profile
    # ------------------------------------------------------------------

    @pyqtSlot(result=str)
    def get_company_profile_layout(self) -> str:
        """Same layout as Transfer's customer form in "Tổ chức" mode --
        CompanyProfilePage.__init__ configures its PersonForm identically
        (DocumentType.TRANSFER, role "customer", entity_type forced to "Tổ
        chức" and disabled). Independent of any active document type on the
        main page, so it works no matter what's currently open."""
        layout = resolve_person_layout("profile", DocumentType.TRANSFER, "customer", "Tổ chức")
        return json.dumps(layout)

    @pyqtSlot(result=str)
    def get_company_profile(self) -> str:
        return json.dumps(asdict(self.company_profile))

    @pyqtSlot(str, result=str)
    def save_company_profile(self, person_json: str) -> str:
        person = person_from_dict(json.loads(person_json))
        person.entity_type = "Tổ chức"
        # value_at() (rules.py) walks the path as real attribute names on
        # `report`, so this must stay prefixed "customer" (a real ReportData
        # field) for required_errors() to actually see the person's values --
        # only translated to "profile.*" afterwards, to match the JS-side
        # dialog's field paths (get_company_profile_layout()), which are
        # deliberately NOT "customer.*" so they can never collide with the
        # main page's own customer-tab errors if both happened to be
        # populated at once.
        report = ReportData(document_type=DocumentType.TRANSFER, customer=person)
        required = party_required("customer", person) + ["customer.date_of_birth", "customer.address", "customer.nationality"]
        errors = required_errors(report, required)
        errors += person_errors("customer", person, {"id_number", "date_of_birth", "issue_date", "authorization_date"})
        if errors:
            return json.dumps(
                {
                    "ok": False,
                    "errors": [{"path": e.path.replace("customer.", "profile.", 1), "message": e.message} for e in errors],
                }
            )
        save_company_profile(self.settings, person)
        self.company_profile = person
        return json.dumps({"ok": True, "errors": []})


def _zero_required(rows: list[list[dict]]) -> list[list[dict]]:
    """Equivalent of PersonForm.set_identity_required(False): force every
    field's required flag off (used when the new_owner tab is present but
    not actually needed for the current document/action)."""
    for row in rows:
        for cell in row:
            cell["field"]["required"] = False
    return rows
