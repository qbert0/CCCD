from pathlib import Path

from desktop_app.backend.domain.models import DocumentType, ReportData, ServiceTemplate
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from ..renderer import _common_context, _date_parts, _given_name, _subscriber_numbers_joined, choice_mark, dotted
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
        # Both Quang Hà services (STT and SIM_CK) use the sim-replacement-
        # specific aftersale template -- per direct instruction, not just
        # QUANG_HA_SIM_CK's own "Thay SIM" shape (which already matched
        # SIM_REPLACEMENT's own case below).
        if data.service_template in (
            ServiceTemplate.SIM_REPLACEMENT.value,
            ServiceTemplate.QUANG_HA_SIM_CK.value,
            ServiceTemplate.QUANG_HA_STT.value,
        ):
            return self.sim_replacement_template
        return self.template

    def build_context(self, data: ReportData) -> dict[str, str]:
        """Values copied verbatim from _docx_context()'s own aftersale_*/
        *_mark/*_signature_name block, not re-derived -- a straight
        extraction (see SimChangeFormDocumentModule.build_context for the
        first one, same approach)."""
        customer, new_owner = data.customer, data.new_owner
        is_organization = customer.entity_type == "Tổ chức"
        aftersale_day, aftersale_month, aftersale_year = _date_parts(data.document_date)
        subscriber_numbers_joined = _subscriber_numbers_joined(data)

        def action_value(action: str, value: str, length: int = 20) -> str:
            return dotted(value, length) if data.service_action == action else "." * length

        context = {
            **_common_context(data),
            "aftersale_day": dotted(aftersale_day, 4),
            "aftersale_month": dotted(aftersale_month, 4),
            "aftersale_year": dotted(aftersale_year, 6),
            # This is the form's "Khách hàng / Người yêu cầu" identity, not
            # an unconditional shop identity. Organization services
            # naturally use the saved company profile; individual
            # transfers and SIM replacement use the scanned current owner.
            "aftersale_customer_name": dotted(customer.display_name().upper(), 46),
            "aftersale_customer_id_number": dotted(
                customer.business_registration_number if is_organization else customer.id_number, 18
            ),
            "aftersale_customer_issue_date": dotted(
                customer.business_registration_issue_date if is_organization else customer.issue_date, 14
            ),
            "aftersale_customer_issue_place": dotted(
                customer.business_registration_issue_place if is_organization else customer.issue_place, 26
            ),
            "aftersale_customer_address": dotted(
                customer.headquarters_address if is_organization else customer.address, 48
            ),
            "aftersale_customer_phone": dotted(
                " - ".join(value for value in (customer.phone, customer.phone_2) if value), 24
            ),
            # The 3 aftersale signature-table names. "Người yêu cầu" is
            # deliberately NOT always the customer: when the old owner is an
            # organization, an org can't physically sign, so its own
            # representative_name signs on its behalf; when the old owner
            # is an individual, they sign for themselves. "Chủ thuê bao
            # mới" is always the new owner, in both cases.
            "aftersale_requester_signature_name": (
                customer.representative_name if is_organization else customer.display_name()
            ).upper(),
            "aftersale_new_owner_signature_name": new_owner.display_name().upper(),
            "aftersale_clerk_signature_name": data.staff_name.upper(),
            "id_attachment_mark": choice_mark(data.has_id_attachment),
            "sim_attachment_mark": choice_mark(data.has_original_sim),
            "other_attachment_mark": choice_mark(bool(data.other_attachment.strip())),
            "other_attachment_value": dotted(data.other_attachment, 48),
            "update_information_mark": choice_mark(data.service_action == "Cập nhật thông tin"),
            "update_subscriber_number": action_value(
                "Cập nhật thông tin", subscriber_numbers_joined, 30
            ),
            "replace_sim_mark": choice_mark(data.service_action == "Thay SIM"),
            "replace_sim_subscriber_number": action_value("Thay SIM", subscriber_numbers_joined, 30),
            "transfer_mark": choice_mark(data.service_action == "Chuyển chủ quyền"),
            "transfer_subscriber_number": action_value(
                "Chuyển chủ quyền", subscriber_numbers_joined, 22
            ),
            "transfer_new_owner_name": action_value(
                "Chuyển chủ quyền", new_owner.display_name().upper(), 28
            ),
            "transfer_new_owner_id_number": action_value(
                "Chuyển chủ quyền", new_owner.id_number, 20
            ),
            "transfer_new_owner_issue_date": action_value(
                "Chuyển chủ quyền", new_owner.issue_date, 14
            ),
            "transfer_new_owner_issue_place": action_value(
                "Chuyển chủ quyền", new_owner.issue_place, 24
            ),
            "requester_role_mark": choice_mark(data.service_action != "Chuyển chủ quyền"),
            "new_owner_role_mark": choice_mark(data.service_action == "Chuyển chủ quyền"),
            "common_subscriber_number": dotted(subscriber_numbers_joined, 24),
            "backup_phone_1_line": dotted(data.backup_phone_1 or customer.phone, 20),
            "backup_phone_2_line": dotted(data.shop_phone_2, 20),
        }
        for name_key, given_key in (
            ("aftersale_requester_signature_name", "aftersale_requester_signature_given_name"),
            ("aftersale_new_owner_signature_name", "aftersale_new_owner_signature_given_name"),
            ("aftersale_clerk_signature_name", "aftersale_clerk_signature_given_name"),
        ):
            context[given_key] = _given_name(context[name_key])
        return context
