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
import shutil
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path

from PyQt5.QtCore import QObject, QSettings, QStandardPaths, QThread, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog

from desktop_app.backend.config.company_profile import load_company_profile, save_company_profile
from desktop_app.backend.config.document_set_settings import (
    load_document_set_overrides,
    save_document_set_overrides,
)
from desktop_app.backend.config.operator_profiles import (
    OperatorProfile,
    load_operator_profiles,
    operator_for_service,
    save_operator_profiles as save_operator_profiles_storage,
)
from desktop_app.backend.config.representative_profile import (
    load_representative_profile,
    save_representative_profile as save_representative_profile_storage,
)
from desktop_app.backend.documents import (
    ConversionToolsMissing,
    DocumentRegistry,
    convert_docx_batch_to_images,
    generate_service_template,
    generated_output_images,
    next_output_number,
    required_input_numbers,
    scan_numbered_images,
)
from desktop_app.backend.documents.renderer import SIGNATURE_FORM_HEIGHT, SIGNATURE_FORM_WIDTH
from desktop_app.backend.domain.models import (
    DOCUMENT_NAMES,
    DOCUMENT_SHORT_NAMES,
    SERVICE_TEMPLATE_CUSTOMER_ENTITY_TYPE,
    SERVICE_TEMPLATE_DOCUMENTS,
    SERVICE_TEMPLATE_NAMES,
    SERVICE_TEMPLATE_PAYMENT_METHOD,
    SERVICE_TEMPLATE_SERVICE_ACTION,
    DocumentType,
    PersonData,
    ReportData,
    ServiceTemplate,
)
from desktop_app.backend.ocr import CardSide, OCRFileResult, OCRService, combine_file_results
from desktop_app.backend.paths import default_output_dir, resource_path
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
    resolve_service_form_layout,
    resolve_subscriber_list_layout,
)

ORGANIZATION_DOCUMENTS = {
    DocumentType.TRANSFER,
    DocumentType.AFTERSALE,
    DocumentType.PREPAID_CONTRACT,
}
# Also the transfer template's "Đại diện Bên C" default: that role is
# frequently signed by shop staff on the new owner's behalf, so it reuses
# this exact same variable+default rather than a separate one.
DEFAULT_PROVIDER_REPRESENTATIVE_NAME = "VÕ DUY NHẬT"
# Bên B's own signature/stamp image -- one shop-wide setting (see
# choose_provider_signature/get_provider_signature), independent of any
# profile, mirroring DEFAULT_PROVIDER_REPRESENTATIVE_NAME's fixed-identity
# reasoning above.
PROVIDER_SIGNATURE_SETTINGS_KEY = "provider_signature_path"
# Starting value for Prepaid Contract's "Điểm cung cấp dịch vụ viễn thông" --
# like service_point_address/service_point_phone below, a per-case editable
# default (falls back only when the field is still empty), not a fixed value.
DEFAULT_SERVICE_POINT_NAME = "TD Vietnamobile"


def _signatures_dir() -> Path:
    signatures_dir = Path(
        QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    ) / "signatures"
    signatures_dir.mkdir(parents=True, exist_ok=True)
    return signatures_dir


def _needs_new_owner(document_type: DocumentType, service_action: str) -> bool:
    return document_type in {
        DocumentType.TRANSFER, DocumentType.AFTERSALE, DocumentType.PREPAID_CONTRACT,
    }


# How many "Tạo bộ hồ sơ" clicks can run at once (one QThread each, see
# DocumentGenerationWorker) before a new click is refused outright rather
# than silently queued -- an unbounded number of concurrent PaddleOCR-class
# workloads would just thrash the machine instead of finishing faster.
MAX_CONCURRENT_GENERATION_JOBS = 10

# Chuyển quyền trả trước (Tổ chức → Cá nhân) is the only mẫu that needs these
# 2 extra pages appended after its generated documents -- the shop's own
# business registration certificate (proving the signing representative's
# authority), by explicit request. Listed page-order (fig2 then fig1), not
# filename order: fig2.jpg is the certificate's own page 1 (company/owner
# info), fig1.jpg its page 2 (the representative's personal details).
_PREPAID_TRANSFER_ORG_EXTRA_PAGES = (
    resource_path("desktop_app", "backend", "documents", "transfer", "fig2.jpg"),
    resource_path("desktop_app", "backend", "documents", "transfer", "fig1.jpg"),
)


class DocumentGenerationWorker(QThread):
    """One "Tạo bộ hồ sơ" job on its own OS thread -- mirrors OCRWorker
    (desktop_app/frontend/pages/home_page.py) exactly: every value this
    needs is captured here at construction time, on the calling (main)
    thread, so run() never reads back into a live WebBridge attribute
    (self.document_set_overrides, self._last_source_dir, self.settings)
    that another slot could mutate -- e.g. the user picking a different
    source folder or saving different document-set settings -- while this
    job is still in flight for an earlier case."""

    finished_job = pyqtSignal(str, str)  # job_id, JSON result

    def __init__(
        self, job_id: str, template: ServiceTemplate, data: ReportData,
        document_types: list, folder: Path, source_dir: Path | None,
        source_images: dict, parent=None,
    ):
        super().__init__(parent)
        self.job_id = job_id
        self.template = template
        self.data = data
        self.document_types = document_types
        self.folder = folder
        self.source_dir = source_dir
        self.source_images = source_images

    def run(self) -> None:
        # Identical body to the old synchronous generate_service_template_documents
        # (generation -> image conversion -> atomic commit), just operating
        # on this worker's own constructor-captured values instead of self.*,
        # and emitting the result instead of returning it.
        try:
            counter = next_output_number(self.folder)
            with tempfile.TemporaryDirectory() as tmp:
                temp_root = Path(tmp)
                docx_dir = temp_root / "documents"
                staged_images_dir = temp_root / "images"
                docx_outputs, errors = generate_service_template(
                    self.template, self.data, docx_dir, self.document_types,
                )
                if errors:
                    seen: set[tuple[str, str]] = set()
                    error_list = []
                    for error in errors:
                        # Document variants retain historical field paths,
                        # but the visible editor owns one canonical list.
                        path = error.path
                        for internal_prefix in ("beautiful_subscribers.", "prepaid_subscribers."):
                            if path.startswith(internal_prefix):
                                path = "subscribers." + path[len(internal_prefix):]
                        path = {
                            "subscriber_number": "subscribers.0.subscriber_number",
                            "sim_serial": "subscribers.0.sim_serial",
                            "activation_date": "subscribers.0.activation_date",
                        }.get(path, path)
                        key = (path, error.message)
                        if key not in seen:
                            seen.add(key)
                            error_list.append({"path": path, "message": error.message})
                    self.finished_job.emit(
                        self.job_id, json.dumps({"ok": False, "errors": error_list, "paths": []}),
                    )
                    return

                def name_page(_docx_path: Path, _page_index: int) -> str:
                    nonlocal counter
                    result = f"{counter}.jpg"
                    counter += 1
                    return result

                staged_outputs = convert_docx_batch_to_images(
                    docx_outputs, staged_images_dir, filename_for=name_page,
                )
                if self.template == ServiceTemplate.PREPAID_TRANSFER_ORG:
                    for extra_page in _PREPAID_TRANSFER_ORG_EXTRA_PAGES:
                        target = staged_images_dir / name_page(extra_page, 1)
                        shutil.copy2(extra_page, target)
                        staged_outputs.append(target)

                # Commit only after generation and conversion have both
                # succeeded. Inputs 1-6 are refreshed when exporting to a
                # different folder, so that destination is self-contained.
                self.folder.mkdir(parents=True, exist_ok=True)
                if self.source_dir and self.source_dir.resolve() != self.folder.resolve():
                    for number, source_path in self.source_images.items():
                        if 1 <= number <= 6:
                            shutil.copy2(
                                source_path, self.folder / f"{number}{source_path.suffix.casefold()}",
                            )

                # A multi-file result cannot be replaced by one filesystem
                # syscall, so keep the complete old set in a same-volume
                # backup until every new page is installed. Any commit
                # failure restores the exact previous result, including
                # pages that the new shorter set would otherwise remove.
                final_outputs: list[Path] = []
                installed: list[Path] = []
                pending_paths: list[Path] = []
                old_outputs = generated_output_images(self.folder)
                with tempfile.TemporaryDirectory(prefix=".cccd-report-backup-", dir=self.folder) as backup:
                    backup_dir = Path(backup)
                    backed_up: list[tuple[Path, Path]] = []
                    try:
                        for old_path in old_outputs:
                            backup_path = backup_dir / old_path.name
                            old_path.replace(backup_path)
                            backed_up.append((old_path, backup_path))
                        for staged in staged_outputs:
                            final_path = self.folder / staged.name
                            pending = self.folder / f".cccd-report-{staged.name}.tmp"
                            pending_paths.append(pending)
                            shutil.copy2(staged, pending)
                            pending.replace(final_path)
                            installed.append(final_path)
                            final_outputs.append(final_path)
                    except Exception:
                        for pending in pending_paths:
                            if pending.exists():
                                pending.unlink()
                        for final_path in installed:
                            if final_path.exists():
                                final_path.unlink()
                        for original, backup_path in backed_up:
                            if backup_path.exists():
                                backup_path.replace(original)
                        raise
        except ConversionToolsMissing as exc:
            self.finished_job.emit(self.job_id, json.dumps({"ok": False, "message": str(exc), "paths": []}))
            return
        except Exception as exc:  # noqa: BLE001
            self.finished_job.emit(self.job_id, json.dumps({"ok": False, "message": str(exc), "paths": []}))
            return
        self.finished_job.emit(
            self.job_id,
            json.dumps({"ok": True, "paths": [str(path) for path in final_outputs], "folder": str(self.folder)}),
        )


class WebBridge(QObject):
    ocrProgress = pyqtSignal(str, int, int)
    ocrFileResult = pyqtSignal(str, str)
    ocrBatchFinished = pyqtSignal(str, str)
    ocrBatchFailed = pyqtSignal(str, str)
    generationFinished = pyqtSignal(str, str)

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window  # QMainWindow, for QFileDialog/QMessageBox parenting
        self.settings = QSettings("CCCDReport", "DesktopApp")
        self.registry = DocumentRegistry()
        self.company_profile = load_company_profile(self.settings)
        self.representative_profile = load_representative_profile(self.settings)
        self.operator_profiles = load_operator_profiles(self.settings)
        self.document_set_overrides = load_document_set_overrides(self.settings)

        self._active_document_type: DocumentType | None = None
        self._service_action = "Cập nhật thông tin"
        self.workers: list = []
        self._generation_workers: dict[str, DocumentGenerationWorker] = {}
        self._accepted_files: dict[str, dict[CardSide, OCRFileResult]] = {
            "customer": {}, "new_owner": {}, "representative": {},
        }
        self._ocr_done_count: dict[str, int] = {}
        self._ocr_total_count: dict[str, int] = {}
        # The currently selected numbered dossier folder, also offered as a
        # one-click output destination.
        self._last_source_dir: str = ""

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
            "provider_company": asdict(company),
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
                # Bên A's signature cell prints THIS SAME person (Đại diện
                # Bên A = representative_profile, per the copy above), so
                # its image travels with the identity copy -- only here,
                # not for Aftersale/Prepaid, whose customer objects never
                # take on the representative's identity and would show the
                # wrong person's signature under the right person's name.
                customer.signature_path = representative.signature_path
            patch["customer"] = asdict(customer)

        if document_type == DocumentType.PREPAID_CONTRACT:
            patch.update(
                {
                    "representative": asdict(representative),
                    # Bên B / "Đại diện bên cung cấp dịch vụ" is Vietnamobile's
                    # own signing representative -- a fixed identity, not
                    # whoever happens to be filled into "Người đại diện"
                    # (that profile feeds a DIFFERENT role: the org-party
                    # representative for TRANSFER's old owner, prepaid_contract's
                    # structured-mode representative, etc.). Always this name.
                    "provider_representative": DEFAULT_PROVIDER_REPRESENTATIVE_NAME,
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
            patch["provider_representative"] = DEFAULT_PROVIDER_REPRESENTATIVE_NAME
        return patch

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def _default_report_dict(self) -> dict:
        data = asdict(ReportData(document_type=DocumentType.TRANSFER))
        data["document_type"] = ""
        data["shop_name"] = self.company_profile.organization_name
        data["shop_address"] = self.company_profile.headquarters_address
        # Legacy shop identity defaults retained for saved drafts and the
        # advanced editor. Aftersale itself renders the actual requester.
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
        # Document selection no longer exists in the live application. The
        # hidden document_type value is assigned only after selecting a
        # service, immediately before its internal renderers are used.
        return json.dumps({
            "state": self._default_report_dict(),
            "subscriber_layout": resolve_subscriber_list_layout(),
        })

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
            state_patch["service_point_name"] = (
                state.get("service_point_name") or DEFAULT_SERVICE_POINT_NAME
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

    @pyqtSlot(result=str)
    def choose_source_folder(self) -> str:
        """Return numbered image paths without assigning business roles.

        The selected service decides whether 1-3 are the new owner (an
        organization transfer), the old owner/requester, and whether 4-6
        are needed. Keeping this response neutral also allows the folder to
        be selected before the service.
        """
        folder = QFileDialog.getExistingDirectory(
            self.window, "Chọn thư mục ảnh (1.jpg, 2.jpg, ... theo quy ước)", str(default_output_dir())
        )
        if not folder:
            return json.dumps({"folder": ""})
        self._last_source_dir = folder
        numbered = scan_numbered_images(Path(folder))
        return json.dumps({
            "folder": folder,
            "images": {
                str(number): str(path)
                for number, path in numbered.items()
                if 1 <= number <= 6
            },
        })

    @pyqtSlot(str, str, result=str)
    def submit_folder_images(self, target: str, paths_json: str) -> str:
        """Run the OCR pipeline for paths resolved by choose_source_folder."""
        allow_parallel = target.startswith("common_")
        if self._ocr_busy() and not allow_parallel:
            return json.dumps({"started": False, "message": "Một lần đọc ảnh khác đang hoàn tất"})
        # A folder submission is a replacement dossier, not an incremental
        # upload. Never combine one newly selected side with the other side
        # left over from the previous folder.
        self._accepted_files[target] = {}
        paths = [Path(p) for p in json.loads(paths_json)]
        started = self._start_ocr(target, paths)
        return json.dumps({"started": started, "message": "" if started else "Không có ảnh để đọc"})

    def _start_ocr(self, target: str, paths: list[Path]) -> bool:
        if not paths:
            return False
        if self._ocr_busy() and not target.startswith("common_"):
            return False
        from desktop_app.frontend.pages.home_page import OCRWorker as _OCRWorker

        self._ocr_done_count[target] = 0
        self._ocr_total_count[target] = len(paths)
        self.ocrProgress.emit(target, 0, len(paths))
        for path in paths:
            worker = _OCRWorker(target, path, self)
            worker.completed.connect(self._ocr_file_completed)
            self.workers.append(worker)
            worker.start()
        return True

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
        data["provider_company"] = person_from_dict(data.get("provider_company", {}))
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

    # ------------------------------------------------------------------
    # Service templates ("mẫu") -- generate every document a mẫu needs in
    # one action, instead of re-running the document-type picker N times.
    # ------------------------------------------------------------------

    @pyqtSlot(result=str)
    def get_subscriber_list_layout(self) -> str:
        """Legacy unfiltered descriptor; the live UI receives this layout
        already filtered inside resolve_service_form_layout()."""
        return json.dumps(resolve_subscriber_list_layout())

    @pyqtSlot(result=str)
    def get_service_templates(self) -> str:
        return json.dumps([
            {
                "value": template.value,
                "label": SERVICE_TEMPLATE_NAMES[template],
                "documents": [
                    DOCUMENT_SHORT_NAMES[item] for item in self.document_set_overrides[template]
                ],
                "requires_new_owner": template != ServiceTemplate.SIM_REPLACEMENT,
                "required_images": list(required_input_numbers(template)),
                "source_role": (
                    "new_owner_123"
                    if template in {
                        ServiceTemplate.PREPAID_TRANSFER_ORG,
                        ServiceTemplate.COMMITMENT_TRANSFER_ORG,
                    }
                    else "requester_123"
                    if template == ServiceTemplate.SIM_REPLACEMENT
                    # Cá nhân -> cá nhân (both "trả trước" and "cam kết"):
                    # images 1-3 are the NEW owner, 4-6 the old one --
                    # swapped from the org->individual naming's own
                    # "old_123_new_456" order by explicit request.
                    else "new_123_old_456"
                ),
                "requires_monthly_fee": template != ServiceTemplate.SIM_REPLACEMENT,
            }
            for template in ServiceTemplate
        ])

    @pyqtSlot(str, result=str)
    def on_service_template_changed(self, request_json: str) -> str:
        """Resolve one dossier form from the selected business service.

        Generated document types stay an internal output detail. The state
        patch and `service_layout` are expressed only in business roles:
        organization/current owner, new owner, requester transaction and
        provider defaults. Subscribers are a separate fixed form.
        """
        request = json.loads(request_json)
        new_raw = request.get("new_service_template") or ""
        state = request["state"]
        common_dossier = request.get("common_dossier")

        if not new_raw:
            return json.dumps({
                "state_patch": {},
                "ui": {"ready": False, "serviceTemplateName": "", "documentCount": 0},
                "service_layout": {},
            })

        template = ServiceTemplate(new_raw)
        document_types = self.document_set_overrides[template]
        customer_entity_type = SERVICE_TEMPLATE_CUSTOMER_ENTITY_TYPE[template]
        state_patch = self._profile_defaults_patch(DocumentType.TRANSFER)
        # Bên B / "Đại diện bên cung cấp dịch vụ" is Vietnamobile's own fixed
        # signing identity, needed by TRANSFER, BEAUTIFUL_NUMBER, and
        # SIM_CHANGE_FORM's own templates too -- not just PREPAID_CONTRACT's.
        # Set unconditionally so it isn't silently blank for a mẫu (like
        # SIM_REPLACEMENT) that never includes PREPAID_CONTRACT, the only
        # document type whose defaults previously carried this value.
        provider_defaults = self._profile_defaults_patch(DocumentType.AFTERSALE)
        state_patch["provider_representative"] = provider_defaults["provider_representative"]
        # Bên B's own signature/stamp image -- a single shop-wide setting
        # (see choose_provider_signature/get_provider_signature below),
        # unrelated to any profile, matching provider_representative's own
        # fixed-identity status (see round 12's lesson in memory: this
        # role is Vietnamobile's own signer, not whichever "Người đại
        # diện" profile happens to be configured).
        state_patch["provider_signature_path"] = str(self.settings.value(PROVIDER_SIGNATURE_SETTINGS_KEY, "") or "")

        # The common dossier is positional and is therefore the sole OCR
        # authority across service changes. Never derive a new service from
        # the previous service's semantic customer/new_owner fields: for an
        # organization transfer person123 is the NEW owner, while for an
        # individual transfer the same person123 is the OLD owner.
        if isinstance(common_dossier, dict):
            person123 = dict(common_dossier.get("person123") or {})
            person456 = dict(common_dossier.get("person456") or {})
        else:
            # Compatibility for older callers/tests that predate the common
            # dossier request field.
            person123 = dict(state.get("customer", {}))
            person456 = dict(state.get("new_owner", {}))

        if customer_entity_type == "Tổ chức":
            customer = dict(state_patch.get("customer", asdict(self.company_profile)))
            new_owner = person123
        elif template == ServiceTemplate.SIM_REPLACEMENT:
            customer = person123
            new_owner = {}
        else:
            customer = person123
            new_owner = person456

        customer["entity_type"] = customer_entity_type
        new_owner["entity_type"] = "Cá nhân"
        state_patch["customer"] = customer
        state_patch["new_owner"] = new_owner
        # document_type is an internal renderer discriminator. It has no
        # control or form in the UI and always follows the service mapping.
        state_patch["document_type"] = document_types[0].value
        state_patch["service_action"] = SERVICE_TEMPLATE_SERVICE_ACTION[template]
        state_patch["service_template"] = template.value
        # "Hình thức thanh toán" follows the selected mẫu directly: mẫu 1/2
        # print "Trả trước", mẫu 3/4 print "Cam kết".
        state_patch["payment_method"] = SERVICE_TEMPLATE_PAYMENT_METHOD[template]
        operator = operator_for_service(self.operator_profiles, template)
        state_patch["staff_name"] = operator.name
        state_patch["operator_signature_path"] = operator.signature_path

        if DocumentType.PREPAID_CONTRACT in document_types:
            prepaid_patch = self._profile_defaults_patch(DocumentType.PREPAID_CONTRACT)
            for key in (
                "provider_company", "representative", "provider_representative",
                "provider_position", "provider_phone", "provider_email", "provider_unit_address",
            ):
                if key in prepaid_patch:
                    state_patch[key] = prepaid_patch[key]
            state_patch["prepaid_structured_parties"] = True
            state_patch["service_point_address"] = (
                state.get("service_point_address") or state_patch.get("shop_address") or state.get("shop_address", "")
            )
            state_patch["service_point_phone"] = (
                state.get("service_point_phone") or state_patch.get("shop_phone") or state.get("shop_phone", "")
            )
            state_patch["service_point_name"] = (
                state.get("service_point_name") or DEFAULT_SERVICE_POINT_NAME
            )
        else:
            state_patch["prepaid_structured_parties"] = False

        subscribers = state.get("subscribers")
        if not isinstance(subscribers, list) or not subscribers:
            from datetime import date as _date

            subscribers = [{
                "subscriber_number": state.get("subscriber_number", ""),
                "monthly_fee": "", "activation_date": _date.today().strftime("%d/%m/%Y"),
                "sim_serial": "", "commitment_note": "",
            }]
        else:
            from datetime import date as _date

            subscribers = [dict(row) for row in subscribers]
            for row in subscribers:
                row["commitment_months"] = str(row.get("commitment_months") or "12")
                row["activation_date"] = str(
                    row.get("activation_date") or _date.today().strftime("%d/%m/%Y")
                )
        state_patch["subscribers"] = subscribers

        return json.dumps({
            "state_patch": state_patch,
            "ui": {
                "ready": True,
                "serviceTemplateName": SERVICE_TEMPLATE_NAMES[template],
                "documentCount": len(document_types),
            },
            "service_layout": resolve_service_form_layout(template),
        })

    @pyqtSlot(result=str)
    def get_last_source_dir(self) -> str:
        return json.dumps(self._last_source_dir)

    @pyqtSlot(result=str)
    def get_default_output_dir(self) -> str:
        saved = str(self.settings.value("default_output_dir", "") or "")
        return json.dumps(saved or str(default_output_dir()))

    @pyqtSlot(str)
    def set_default_output_dir(self, path: str) -> None:
        self.settings.setValue("default_output_dir", path)

    @pyqtSlot(str, str, str, result=str)
    def generate_service_template_documents(self, template_value: str, state_json: str, output_dir: str) -> str:
        """`output_dir` is whatever folder the JS side already resolved --
        either `_last_source_dir` (the "save back into the same folder as
        the photos" option) or a folder the user picked via
        `choose_output_dir` below. An empty string means "use the saved
        default output dir" (point 5 of the dịch vụ workflow).

        Only dispatches a DocumentGenerationWorker and returns right away
        (`{"ok": True, "job_id": ...}`) -- the actual generate -> convert ->
        commit pipeline (see that class) now runs on its own thread so the
        GUI/QWebEngineView thread stays free for the user to keep editing a
        different case while an earlier "Tạo bộ hồ sơ" click is still
        running. The real result arrives later via the generationFinished
        signal, keyed by job_id. Every value the worker needs is resolved
        HERE, on the main thread, before it starts -- see
        DocumentGenerationWorker's own docstring for why (this call is the
        one place a snapshot of "what the live Settings/state say right
        now" is taken; nothing after dispatch ever re-reads it).

        The real product here is images, not the .docx files -- by explicit
        request ("cái tôi cần là ảnh chứ không phải là tài liệu word"). Each
        document is generated into a throwaway temp folder, converted to
        one JPG per page, and only the JPGs land in the real output folder;
        the .docx never does.

        Output is a NUMBERED SEQUENCE using the shop's fixed convention:
        inputs are slots 1-6 and generated pages always start at 7. A repeat
        run stages the complete new set first, atomically replaces matching
        page numbers, then removes obsolete extra pages from the previous
        result. It never appends 12, 13, ... to an old run.
        """
        if len(self._generation_workers) >= MAX_CONCURRENT_GENERATION_JOBS:
            return json.dumps({
                "ok": False,
                "overloaded": True,
                "message": (
                    f"Máy đang quá tải (đã có {MAX_CONCURRENT_GENERATION_JOBS} "
                    "bộ hồ sơ đang tạo cùng lúc), đợi một bộ xong rồi thử lại."
                ),
            })

        template = ServiceTemplate(template_value)
        document_types = self.document_set_overrides[template]
        state = json.loads(state_json)
        if not state.get("document_type"):
            state["document_type"] = document_types[0].value
        data = self._report_data_from_state(state)
        folder = Path(output_dir) if output_dir else Path(json.loads(self.get_default_output_dir()))
        source_dir = Path(self._last_source_dir) if self._last_source_dir else None
        source_images = scan_numbered_images(source_dir) if source_dir else {}
        missing_inputs = [number for number in required_input_numbers(template) if number not in source_images]
        if missing_inputs:
            return json.dumps({
                "ok": False,
                "errors": [{
                    "path": "source_folder",
                    "message": "Bộ hồ sơ thiếu ảnh " + ", ".join(f"{number}.jpg" for number in missing_inputs),
                }],
                "paths": [],
            })

        job_id = uuid.uuid4().hex
        worker = DocumentGenerationWorker(
            job_id, template, data, document_types, folder, source_dir, source_images, self,
        )
        worker.finished_job.connect(self._generation_job_finished)
        self._generation_workers[job_id] = worker
        worker.start()
        return json.dumps({"ok": True, "job_id": job_id})

    def _generation_job_finished(self, job_id: str, result_json: str) -> None:
        self._generation_workers.pop(job_id, None)
        self.generationFinished.emit(job_id, result_json)

    @pyqtSlot(result=str)
    def choose_output_dir(self) -> str:
        folder = QFileDialog.getExistingDirectory(
            self.window, "Chọn thư mục lưu tài liệu", json.loads(self.get_default_output_dir())
        )
        if folder:
            self.set_default_output_dir(folder)
        return json.dumps(folder or "")

    @pyqtSlot(str, result=str)
    def new_case(self, state_json: str) -> str:
        """Return clean case data while retaining the internal renderer key.

        The client reapplies the selected service immediately, restoring the
        service form and its role-based defaults.
        """
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
    # Service-specific transaction clerks
    # ------------------------------------------------------------------

    @pyqtSlot(result=str)
    def get_operator_profiles(self) -> str:
        return json.dumps({
            "profiles": [{
                "profile_id": profile.profile_id,
                "name": profile.name,
                "signature_path": profile.signature_path,
                "signature_thumbnail": (
                    thumbnail_data_url(Path(profile.signature_path))
                    if profile.signature_path and Path(profile.signature_path).is_file()
                    else ""
                ),
                "service_templates": profile.service_templates,
            } for profile in self.operator_profiles],
            "services": [
                {"value": template.value, "label": SERVICE_TEMPLATE_NAMES[template]}
                for template in ServiceTemplate
            ],
        })

    @pyqtSlot(result=str)
    def choose_operator_signature(self) -> str:
        """Native file picker for one clerk's own signature image. Just
        picks the file and hands back a display-sized preview -- the crop
        modal (SignatureCropModal, js/components.js) shows this, and only
        once the user confirms their crop does save_cropped_signature
        below write the final file, keyed by that profile's own slug."""
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Chọn ảnh chữ ký giao dịch viên", str(Path.home()),
            "Ảnh (*.png *.jpg *.jpeg)",
        )
        if not path:
            return json.dumps({"ok": False})
        return json.dumps({"ok": True, "signature_source": thumbnail_data_url(Path(path), max_size=1600)})

    @pyqtSlot(str, result=str)
    def save_operator_profiles(self, profiles_json: str) -> str:
        raw = json.loads(profiles_json)
        if not isinstance(raw, list) or not raw:
            return json.dumps({"ok": False, "message": "Cần có ít nhất một giao dịch viên"})

        valid_services = {template.value for template in ServiceTemplate}
        profiles: list[OperatorProfile] = []
        seen_ids: set[str] = set()
        assigned: dict[str, str] = {}
        for index, item in enumerate(raw, start=1):
            profile_id = str((item or {}).get("profile_id", "") or "").strip()
            name = str((item or {}).get("name", "") or "").strip()
            signature_path = str((item or {}).get("signature_path", "") or "").strip()
            services = [str(value) for value in (item or {}).get("service_templates", [])]
            if not re.fullmatch(r"operator_[A-Za-z0-9_-]{1,80}", profile_id) or profile_id in seen_ids:
                return json.dumps({"ok": False, "message": f"Giao dịch viên {index} có mã không hợp lệ"})
            if not name:
                return json.dumps({"ok": False, "message": f"Hãy nhập họ tên giao dịch viên {index}"})
            if any(service not in valid_services for service in services):
                return json.dumps({"ok": False, "message": f"Phân công dịch vụ của {name} không hợp lệ"})
            for service in services:
                if service in assigned:
                    return json.dumps({
                        "ok": False,
                        "message": "Mỗi dịch vụ chỉ được giao cho một người",
                    })
                assigned[service] = profile_id
            seen_ids.add(profile_id)
            profiles.append(OperatorProfile(
                profile_id=profile_id, name=name, signature_path=signature_path,
                service_templates=services,
            ))

        missing = valid_services - set(assigned)
        if missing:
            labels = ", ".join(
                SERVICE_TEMPLATE_NAMES[ServiceTemplate(value)] for value in sorted(missing)
            )
            return json.dumps({"ok": False, "message": f"Chưa phân công: {labels}"})
        save_operator_profiles_storage(self.settings, profiles)
        self.operator_profiles = profiles
        return json.dumps({"ok": True})

    # ------------------------------------------------------------------
    # Signature crop/position tool -- every choose_*_signature slot above
    # (and Bên B / representative below) only picks a file and returns a
    # preview; this pair is the shared "confirm" step every one of them
    # funnels through, so every signature file that ends up on disk is
    # already cropped to the exact same rectangle (SignatureCropModal in
    # js/components.js does the actual cropping, client-side, onto a
    # <canvas>, then hands the PNG bytes here).
    # ------------------------------------------------------------------

    @pyqtSlot(result=str)
    def get_signature_crop_size(self) -> str:
        return json.dumps({
            "width_mm": SIGNATURE_FORM_WIDTH / 36000,
            "height_mm": SIGNATURE_FORM_HEIGHT / 36000,
        })

    @pyqtSlot(str, str, result=str)
    def save_cropped_signature(self, base64_png: str, slug: str) -> str:
        """Write a client-cropped signature PNG to its slot's stable,
        per-signer file (always .png now, regardless of what format the
        original upload was -- the crop step always re-encodes). `slug`
        is one of the same per-signer names the old _store_signature_image
        used: "provider", "representative", "customer_representative", or
        f"operator_{profile_id}" -- the caller already knows which, same
        as it always has. Provider and representative persist immediately
        here (mirroring their old choose_*_signature behavior); operator
        profiles still wait for the explicit "Lưu giao dịch viên" save,
        and customer_representative is never persisted to Settings at all
        (per-case only) -- same 3-way split as before this feature."""
        destination = _signatures_dir() / f"{slug}.png"
        destination.write_bytes(base64.b64decode(base64_png))
        if slug == "provider":
            self.settings.setValue(PROVIDER_SIGNATURE_SETTINGS_KEY, str(destination))
            self.settings.sync()
        elif slug == "representative":
            self.representative_profile.signature_path = str(destination)
            save_representative_profile_storage(self.settings, self.representative_profile)
        return json.dumps({
            "ok": True,
            "signature_path": str(destination),
            "signature_thumbnail": thumbnail_data_url(destination),
        })

    # ------------------------------------------------------------------
    # Bên B / "Đại diện bên cung cấp dịch vụ" own signature image -- one
    # shop-wide setting, independent of any profile (see
    # PROVIDER_SIGNATURE_SETTINGS_KEY above).
    # ------------------------------------------------------------------

    @pyqtSlot(result=str)
    def get_provider_signature(self) -> str:
        path = str(self.settings.value(PROVIDER_SIGNATURE_SETTINGS_KEY, "") or "")
        return json.dumps({
            "signature_path": path,
            "signature_thumbnail": (
                thumbnail_data_url(Path(path)) if path and Path(path).is_file() else ""
            ),
        })

    @pyqtSlot(result=str)
    def choose_provider_signature(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Chọn ảnh chữ ký/con dấu bên cung cấp dịch vụ", str(Path.home()),
            "Ảnh (*.png *.jpg *.jpeg)",
        )
        if not path:
            return json.dumps({"ok": False})
        return json.dumps({"ok": True, "signature_source": thumbnail_data_url(Path(path), max_size=1600)})

    # ------------------------------------------------------------------
    # Which documents each service generates -- a safety net for a wrong
    # service→document mapping guess: the shop can turn any document off
    # or on per service by hand, independent of this app's own defaults.
    # ------------------------------------------------------------------

    @pyqtSlot(result=str)
    def get_document_set_settings(self) -> str:
        return json.dumps({
            "services": [
                {"value": template.value, "label": SERVICE_TEMPLATE_NAMES[template]}
                for template in ServiceTemplate
            ],
            "documents": [
                {"value": document_type.value, "label": DOCUMENT_SHORT_NAMES[document_type]}
                for document_type in DocumentType
            ],
            "selected": {
                template.value: [
                    document_type.value for document_type in self.document_set_overrides[template]
                ]
                for template in ServiceTemplate
            },
        })

    @pyqtSlot(str, result=str)
    def save_document_set_settings(self, selected_json: str) -> str:
        raw = json.loads(selected_json)
        if not isinstance(raw, dict):
            return json.dumps({"ok": False, "message": "Dữ liệu cài đặt không hợp lệ"})

        overrides: dict[ServiceTemplate, list[DocumentType]] = {}
        for template in ServiceTemplate:
            values = raw.get(template.value)
            if not isinstance(values, list) or not values:
                return json.dumps({
                    "ok": False,
                    "message": f"{SERVICE_TEMPLATE_NAMES[template]}: cần chọn ít nhất một tài liệu",
                })
            try:
                overrides[template] = [DocumentType(value) for value in values]
            except ValueError:
                return json.dumps({"ok": False, "message": "Loại tài liệu không hợp lệ"})

        save_document_set_overrides(self.settings, overrides)
        self.document_set_overrides = overrides
        return json.dumps({"ok": True})

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
        payload = asdict(self.representative_profile)
        signature_path = self.representative_profile.signature_path
        payload["signature_thumbnail"] = (
            thumbnail_data_url(Path(signature_path))
            if signature_path and Path(signature_path).is_file()
            else ""
        )
        return json.dumps(payload)

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

    @pyqtSlot(result=str)
    def choose_customer_representative_signature(self) -> str:
        """The old owner's own org representative's signature -- unlike
        choose_representative_signature (a persistent Settings profile),
        this is genuinely per-case (a different real organization/signer
        every time), so save_cropped_signature's "customer_representative"
        slug is never persisted to QSettings either; the caller stashes
        the confirmed result directly on state.customer."""
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Chọn ảnh chữ ký đại diện bên khách hàng", str(Path.home()),
            "Ảnh (*.png *.jpg *.jpeg)",
        )
        if not path:
            return json.dumps({"ok": False})
        return json.dumps({"ok": True, "signature_source": thumbnail_data_url(Path(path), max_size=1600)})

    @pyqtSlot(result=str)
    def choose_representative_signature(self) -> str:
        """Người đại diện's own signature image -- currently only printed
        via prepaid_representative_name (see renderer.py), replacing that
        one inline mention rather than a dedicated 2-line signature block
        (this role has never had one)."""
        path, _ = QFileDialog.getOpenFileName(
            self.window, "Chọn ảnh chữ ký người đại diện", str(Path.home()),
            "Ảnh (*.png *.jpg *.jpeg)",
        )
        if not path:
            return json.dumps({"ok": False})
        return json.dumps({"ok": True, "signature_source": thumbnail_data_url(Path(path), max_size=1600)})

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
