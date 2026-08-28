from pathlib import Path

from desktop_app.backend.domain.models import DocumentType, ReportData, ServiceTemplate
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from .schema import AftersaleSchema


class AftersaleDocumentModule(BaseDocumentModule):
    document_type = DocumentType.AFTERSALE
    suffix = ".docx"
    schema = AftersaleSchema
    # Two real, separately-authored templates share this one field contract
    # (see _resolve_template below) -- the sim-replacement one just doesn't
    # print a document date line, so allow_missing_placeholders covers that
    # gap without needing a second, narrower placeholder set.
    allow_missing_placeholders = True
    placeholders = frozenset({
        "aftersale_day", "aftersale_month", "aftersale_year",
        "aftersale_customer_name", "aftersale_customer_id_number",
        "aftersale_customer_issue_date", "aftersale_customer_issue_place",
        "aftersale_customer_address", "aftersale_customer_phone",
        "id_attachment_mark", "sim_attachment_mark", "other_attachment_mark",
        "other_attachment_value", "update_information_mark", "update_subscriber_number",
        "replace_sim_mark", "replace_sim_subscriber_number", "transfer_mark",
        "transfer_subscriber_number", "transfer_new_owner_name", "transfer_new_owner_id_number",
        "transfer_new_owner_issue_date", "transfer_new_owner_issue_place",
        "requester_role_mark", "new_owner_role_mark", "common_subscriber_number",
        "backup_phone_1_line", "backup_phone_2_line",
        "aftersale_requester_signature_name", "aftersale_requester_signature_given_name",
        "aftersale_new_owner_signature_name", "aftersale_new_owner_signature_given_name",
        "aftersale_clerk_signature_name", "aftersale_clerk_signature_given_name",
    })
    # The transfer services' own template (Chuyển chủ quyền cam kết/trả
    # trước, both cá nhân and tổ chức -- 4 services in total). Kept as
    # `template` since that's this module's required single-template
    # contract; _resolve_template below picks the other one instead for
    # the 5th service, Thay SIM.
    template = resource_path(
        "desktop_app", "backend", "documents", "aftersale", "00_MAU_CAM_KET_SAU_BAN_HANG.docx"
    )
    sim_replacement_template = resource_path(
        "desktop_app", "backend", "documents", "aftersale",
        "00_MAU_CAM_KET_SAU_BAN_HANG_ap_dung_cho_thay_sim.docx",
    )

    def _all_templates(self) -> tuple[Path, ...]:
        return (self.template, self.sim_replacement_template)

    def _resolve_template(self, data: ReportData) -> Path:
        if data.service_template == ServiceTemplate.SIM_REPLACEMENT.value:
            return self.sim_replacement_template
        return self.template
