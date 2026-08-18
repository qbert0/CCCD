"""The QWebChannel bridge object: the only thing Python and the web view
talk to each other through. Business logic (OCR, validation, document
generation, field layout) is never duplicated here -- every slot below is a
thin adapter calling straight into desktop_app.backend/desktop_app.frontend's
existing pure functions and Qt services.
"""

from __future__ import annotations

import base64
import json
import re
import tempfile
from dataclasses import asdict
from pathlib import Path

from PyQt5.QtCore import QObject, QSettings, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from desktop_app.backend.config.company_profile import load_company_profile, save_company_profile
from desktop_app.backend.config.representative_profile import (
    load_representative_profile,
    save_representative_profile as save_representative_profile_storage,
)
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
from desktop_app.backend.validation.rules import (
    common_errors,
    organization_information_required,
    personal_information_required,
    person_errors,
    required_errors,
)
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
    resolve_company_profile_layout,
    resolve_document_tab_layout,
    resolve_person_layout,
    resolve_prepaid_sim_layout,
    resolve_representative_profile_layout,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ORGANIZATION_DOCUMENTS = {
    DocumentType.TRANSFER,
    DocumentType.AFTERSALE,
    DocumentType.PREPAID_CONTRACT,
}


def _needs_new_owner(document_type: DocumentType, service_action: str) -> bool:
    return document_type in {
        DocumentType.TRANSFER, DocumentType.AFTERSALE, DocumentType.PREPAID_CONTRACT,
    }


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
        self.representative_profile = load_representative_profile(self.settings)

        self._active_document_type: DocumentType | None = None
        self._service_action = "Cập nhật thông tin"
        self.workers: list = []
        self._accepted_files: dict[str, dict[CardSide, OCRFileResult]] = {
            "customer": {}, "new_owner": {}, "representative": {},
        }
        self._ocr_done_count: dict[str, int] = {}
        self._ocr_total_count: dict[str, int] = {}

    def _profile_defaults_patch(self, document_type: DocumentType) -> dict:
        """Return an explicit copy of the saved global defaults.

        Document forms own their copy after this point.  This method is used
        once for a new document and again only when the user presses the
        reset/update button, so normal per-document edits are never silently
        overwritten while switching tabs or document types.
        """
        company = self.company_profile
        representative = person_from_dict(asdict(self.representative_profile))
        representative.entity_type = "Cá nhân"
        if not representative.full_name:
            representative.full_name = company.representative_name
        saved_position = (
            representative.representative_position
            or company.representative_position
        )
        representative.representative_position = (
            saved_position if saved_position in {"Giám đốc", "Nhân viên"} else "Giám đốc"
        )

        patch: dict = {
            "shop_name": company.organization_name,
            "shop_address": company.headquarters_address,
            "shop_phone": company.phone,
            "shop_phone_2": company.phone_2,
            "shop_id_number": company.business_registration_number,
            "shop_issue_date": company.business_registration_issue_date,
            "shop_issue_place": company.business_registration_issue_place,
        }
        if document_type in ORGANIZATION_DOCUMENTS:
            customer = person_from_dict(asdict(company))
            customer.entity_type = "Tổ chức"
            if document_type == DocumentType.TRANSFER:
                # The first transfer tab uses the same switchable party form
                # as the subscriber tab. Company identity comes from the
                # company profile; the visible personal/CCCD portion comes
                # from the separately saved representative profile.
                for name in (
                    "full_name", "id_number", "issue_date", "issue_place",
                    "date_of_birth", "nationality", "address",
                ):
                    setattr(customer, name, getattr(representative, name))
                customer.representative_name = representative.full_name
            patch["customer"] = asdict(customer)

        if document_type == DocumentType.PREPAID_CONTRACT:
            patch.update(
                {
                    "representative": asdict(representative),
                    "provider_representative": (
                        representative.full_name or company.representative_name
                    ),
                    "provider_position": (
                        representative.representative_position
                        or company.representative_position
                    ),
                    "provider_phone": representative.phone,
                    "provider_email": representative.email,
                    "provider_unit_address": company.headquarters_address,
                }
            )
        elif document_type == DocumentType.AFTERSALE:
            patch["provider_representative"] = (
                representative.full_name or company.representative_name
            )
        return patch

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def _default_report_dict(self) -> dict:
        data = asdict(ReportData(document_type=DocumentType.TRANSFER))
        data["document_type"] = ""
        data["shop_name"] = self.company_profile.organization_name
        data["shop_address"] = self.company_profile.headquarters_address
        # Aftersale's own identity block (shop_id_number/issue_date/place) --
        # always company-sourced, no OPERATOR-tier fallback needed since
        # there's no legacy value to preserve for these 3.
        data["shop_id_number"] = self.company_profile.business_registration_number
        data["shop_issue_date"] = self.company_profile.business_registration_issue_date
        data["shop_issue_place"] = self.company_profile.business_registration_issue_place
        for name in persistent_document_field_names():
            value = self.settings.value(name, "")
            if value:
                data[name] = str(value)
        # Company Profile's own phone fields win over an older OPERATOR-
        # remembered shop_phone/shop_phone_2 once set, same non-destructive-
        # merge reasoning as CCCD.mergeNonEmpty() on the JS side.
        if self.company_profile.phone:
            data["shop_phone"] = self.company_profile.phone
        if self.company_profile.phone_2:
            data["shop_phone_2"] = self.company_profile.phone_2
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

    @pyqtSlot(str, result=str)
    def get_new_document_state(self, document_type: str) -> str:
        """Create a clean per-document draft from the latest saved defaults."""
        data = self._default_report_dict()
        data["document_type"] = document_type or ""
        return json.dumps(data)

    @pyqtSlot(str, result=str)
    def apply_profile_defaults(self, document_type: str) -> str:
        """Explicitly reset the active document's copied profile fields."""
        return json.dumps(self._profile_defaults_patch(DocumentType(document_type)))

    # ------------------------------------------------------------------
    # Document type / entity type structural recompute
    # ------------------------------------------------------------------

    @pyqtSlot(str, result=str)
    def on_document_type_changed(self, request_json: str) -> str:
        request = json.loads(request_json)
        previous_raw = request.get("previous_document_type") or ""
        new_raw = request.get("new_document_type") or ""
        state = request["state"]
        apply_profile_defaults = bool(request.get("apply_profile_defaults", True))
        preserve_subject = bool(request.get("preserve_subject", True))
        previous = DocumentType(previous_raw) if previous_raw else None
        document_type = DocumentType(new_raw) if new_raw else None

        state_patch: dict = {}
        ready = document_type is not None

        if not ready:
            if previous in {DocumentType.TRANSFER, DocumentType.AFTERSALE, DocumentType.PREPAID_CONTRACT}:
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

        profile_patch = (
            self._profile_defaults_patch(document_type)
            if apply_profile_defaults else {}
        )
        state_patch.update(
            {
                key: value
                for key, value in profile_patch.items()
                if key not in {"customer", "representative"}
            }
        )

        preserved_subject: PersonData | None = None
        if preserve_subject:
            if previous in ORGANIZATION_DOCUMENTS and document_type not in ORGANIZATION_DOCUMENTS:
                preserved_subject = person_from_dict(state.get("new_owner", {}))
            elif previous not in ORGANIZATION_DOCUMENTS and document_type in ORGANIZATION_DOCUMENTS:
                preserved_subject = person_from_dict(state.get("customer", {}))

        customer = person_from_dict(state.get("customer", {}))
        new_owner = person_from_dict(state.get("new_owner", {}))

        if preserved_subject is not None and has_identity(preserved_subject):
            target = person_with_defaults_overlay(preserved_subject)
            if document_type in ORGANIZATION_DOCUMENTS:
                new_owner = target
            else:
                customer = target

        if document_type in ORGANIZATION_DOCUMENTS:
            if "customer" in profile_patch:
                customer = person_from_dict(profile_patch["customer"])
            if document_type != DocumentType.TRANSFER:
                customer.entity_type = "Tổ chức"
            if document_type in {DocumentType.AFTERSALE, DocumentType.PREPAID_CONTRACT}:
                new_owner.entity_type = "Cá nhân"

        state_patch["customer"] = asdict(customer)
        state_patch["new_owner"] = asdict(new_owner)

        if document_type == DocumentType.BEAUTIFUL_NUMBER:
            beautiful_rows = state.get("beautiful_subscribers")
            if not isinstance(beautiful_rows, list) or not beautiful_rows:
                beautiful_rows = [{
                    "subscriber_number": state.get("subscriber_number_1") or state.get("subscriber_number", ""),
                    "commitment_months": state.get("commitment_months", "12"),
                    "monthly_fee": state.get("monthly_fee", ""),
                    "commitment_note": state.get("commitment_note", ""),
                }]
                if any(state.get(name) for name in (
                    "subscriber_number_2", "commitment_months_2", "monthly_fee_2", "commitment_note_2",
                )):
                    beautiful_rows.append({
                        "subscriber_number": state.get("subscriber_number_2", ""),
                        "commitment_months": state.get("commitment_months_2", ""),
                        "monthly_fee": state.get("monthly_fee_2", ""),
                        "commitment_note": state.get("commitment_note_2", ""),
                    })
            state_patch["beautiful_subscribers"] = beautiful_rows

        representative = person_from_dict(state.get("representative", {}))
        if document_type == DocumentType.PREPAID_CONTRACT:
            if "representative" in profile_patch:
                representative = person_from_dict(profile_patch["representative"])
            representative.entity_type = "Cá nhân"
            state_patch["representative"] = asdict(representative)
            state_patch["prepaid_structured_parties"] = True

            rows = state.get("prepaid_subscribers")
            if not isinstance(rows, list) or not rows:
                rows = [{
                    "subscriber_number": state.get("subscriber_number", ""),
                    "sim_serial": state.get("sim_serial", ""),
                    "activation_date": state.get("activation_date", ""),
                }]
            state_patch["prepaid_subscribers"] = rows[:5]
        else:
            state_patch["prepaid_structured_parties"] = False

        if document_type == DocumentType.PREPAID_CONTRACT and apply_profile_defaults:
            state_patch["service_point_address"] = (
                state.get("service_point_address") or state.get("shop_address", "")
            )
            state_patch["service_point_phone"] = (
                state.get("service_point_phone") or state.get("shop_phone", "")
            )
        if document_type == DocumentType.TRANSFER:
            raw_hour = str(state.get("transfer_time", "") or "").strip()
            match = re.match(r"^(\d{1,2})", raw_hour)
            state_patch["transfer_time"] = match.group(1).zfill(2) if match else ""

        service_action = state.get("service_action") or "Cập nhật thông tin"
        needs_new = _needs_new_owner(document_type, service_action)

        self._active_document_type = document_type
        self._service_action = service_action

        customer_role = "prepaid_company" if document_type == DocumentType.PREPAID_CONTRACT else "customer"
        new_owner_role = "prepaid_customer" if document_type == DocumentType.PREPAID_CONTRACT else "new_owner"
        customer_layout = resolve_person_layout("customer", document_type, customer_role, customer.entity_type)
        new_owner_layout = resolve_person_layout("new_owner", document_type, new_owner_role, new_owner.entity_type)
        representative_layout = (
            resolve_person_layout(
                "representative", document_type, "prepaid_representative", representative.entity_type
            )
            if document_type == DocumentType.PREPAID_CONTRACT
            else self._empty_layouts()["representative"]
        )
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
                    "representative": representative_layout,
                    "new_owner": new_owner_layout,
                    "document": resolve_document_tab_layout(document_type),
                    "sims": resolve_prepaid_sim_layout() if document_type == DocumentType.PREPAID_CONTRACT else {},
                },
            }
        )

    @staticmethod
    def _tab_ui(document_type: DocumentType | None, needs_new: bool) -> dict:
        if document_type == DocumentType.TRANSFER:
            return {
                "customerLabel": "Tổ chức", "newOwnerLabel": "Thuê bao", "documentLabel": "Hợp đồng",
                "representativeLabel": "Người đại diện", "simsLabel": "Danh sách SIM",
                "representativeTabVisible": False, "newOwnerTabVisible": needs_new,
                "simsTabVisible": False, "newOwnerUploadVisible": False,
            }
        if document_type == DocumentType.AFTERSALE:
            return {
                "customerLabel": "Tổ chức", "newOwnerLabel": "Khách hàng",
                "documentLabel": "Thông tin tài liệu",
                "representativeLabel": "Người đại diện", "simsLabel": "Danh sách SIM",
                "representativeTabVisible": False, "newOwnerTabVisible": True,
                "simsTabVisible": False, "newOwnerUploadVisible": False,
            }
        if document_type == DocumentType.PREPAID_CONTRACT:
            return {
                "customerLabel": "Công ty", "representativeLabel": "Người đại diện",
                "newOwnerLabel": "Khách hàng",
                "documentLabel": "Bên cung cấp dịch vụ viễn thông",
                "simsLabel": "Danh sách số SIM và ngày hòa mạng",
                "representativeTabVisible": True, "newOwnerTabVisible": True,
                "simsTabVisible": True, "newOwnerUploadVisible": False,
            }
        return {
            "customerLabel": "Khách hàng", "newOwnerLabel": "Chủ thuê bao mới", "documentLabel": "Thông tin tài liệu",
            "representativeLabel": "Người đại diện", "simsLabel": "Danh sách SIM",
            "representativeTabVisible": False, "newOwnerTabVisible": needs_new,
            "simsTabVisible": False, "newOwnerUploadVisible": needs_new,
        }

    @staticmethod
    def _empty_layouts() -> dict:
        empty = {"primary_rows": [], "detail_rows": [], "has_detail": False, "allow_entity": False}
        return {
            "customer": empty, "representative": empty, "new_owner": empty,
            "document": {"common_rows": [], "primary_rows": [], "detail_rows": [], "has_detail": False, "notes_field": None},
            "sims": {},
        }

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
        data["representative"] = person_from_dict(data.get("representative", {}))
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
        # Targeted resets only -- "representative" is a Company Profile
        # dialog session, not case data, and must survive "Hồ sơ mới".
        self._accepted_files["customer"] = {}
        self._accepted_files["new_owner"] = {}
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
        """"Thông tin công ty" sub-tab: 4 fixed rows, by explicit request --
        see resolve_company_profile_layout(). Independent of any active
        document type on the main page, so it works no matter what's
        currently open."""
        return json.dumps(resolve_company_profile_layout())

    @pyqtSlot(result=str)
    def get_company_profile(self) -> str:
        return json.dumps(asdict(self.company_profile))

    @pyqtSlot(result=str)
    def get_representative_profile_layout(self) -> str:
        """"Người đại diện" sub-tab: 3 fixed rows -- see
        resolve_representative_profile_layout()."""
        return json.dumps(resolve_representative_profile_layout())

    @pyqtSlot(result=str)
    def get_representative_profile(self) -> str:
        return json.dumps(asdict(self.representative_profile))

    @pyqtSlot(str, result=str)
    def save_representative_profile(self, person_json: str) -> str:
        person = person_from_dict(json.loads(person_json))
        person.entity_type = "Cá nhân"
        report = ReportData(document_type=DocumentType.AFTERSALE, customer=person)
        errors = required_errors(report, personal_information_required("customer"))
        errors += person_errors("customer", person, {"id_number", "date_of_birth", "issue_date"})
        if errors:
            return json.dumps(
                {
                    "ok": False,
                    "errors": [
                        {"path": e.path.replace("customer.", "representative.", 1), "message": e.message}
                        for e in errors
                    ],
                }
            )
        save_representative_profile_storage(self.settings, person)
        self.representative_profile = person
        return json.dumps({"ok": True, "errors": []})

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
        required = organization_information_required("customer")
        errors = required_errors(report, required)
        errors += common_errors(report, ("customer.business_registration_issue_date",), ())
        errors += person_errors("customer", person, {"phone"})
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
