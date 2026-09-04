from desktop_app.backend.domain.models import DocumentType, ReportData
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from ..renderer import _common_context, _date_parts, _given_name, _subscriber_numbers_joined, choice_mark
from .schema import SimChangeFormSchema


class SimChangeFormDocumentModule(BaseDocumentModule):
    document_type = DocumentType.SIM_CHANGE_FORM
    suffix = ".docx"
    schema = SimChangeFormSchema
    allow_missing_placeholders = True
    placeholders = frozenset({
        "sim_customer_name", "sim_customer_birth_date", "sim_customer_gender",
        "sim_customer_nationality", "sim_customer_id_number", "sim_customer_issue_date",
        "sim_customer_issue_place", "sim_customer_address", "sim_customer_phone",
        "sim_customer_email", "sim_subscriber_number", "sim_new_serial", "sim_current_serial",
        "sim_reason_lost_mark", "sim_reason_damaged_mark", "sim_reason_other_mark",
        "sim_reason_other_value", "sim_request_day", "sim_request_month", "sim_request_year",
        "sim_request_date_line", "sim_document_date_line",
        "frequent_phone_1", "frequent_phone_2", "frequent_phone_3", "frequent_phone_4",
        "frequent_phone_5", "activation_date", "recent_topup_value", "recent_topup_method",
        "remaining_validity", "account_balance", "last_changed_service",
        "customer_signature_name", "customer_signature_given_name",
        "provider_representative_signature", "provider_representative_signature_given_name",
        "sim_operator_signature_name", "sim_operator_signature_given_name",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "sim_change_form",
        "00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx",
    )

    def build_context(self, data: ReportData) -> dict[str, str]:
        """First document type migrated off the renderer._docx_context()
        monolith (see BaseDocumentModule.build_context's own docstring) --
        every field below is this template's own placeholder set (see
        `placeholders` above) minus the 4 shared with other document types,
        which come from _common_context() instead. Values copied verbatim
        from _docx_context()'s own sim_* block, not re-derived from
        scratch, so this is a straight extraction, not a rewrite."""
        customer = data.customer
        sim_request_day, sim_request_month, sim_request_year = _date_parts(data.document_date)
        context = {
            **_common_context(data),
            "sim_customer_name": customer.display_name().upper(),
            "sim_customer_birth_date": customer.date_of_birth,
            "sim_customer_gender": customer.gender,
            "sim_customer_nationality": customer.nationality,
            "sim_customer_id_number": customer.id_number,
            "sim_customer_issue_date": customer.issue_date,
            "sim_customer_issue_place": customer.issue_place,
            "sim_customer_address": customer.address,
            # The shop's OWN contact number (already auto-defaulted from the
            # saved company profile), not something the clerk types per case.
            "sim_customer_phone": data.shop_phone,
            "sim_customer_email": customer.email,
            "sim_subscriber_number": _subscriber_numbers_joined(data),
            # The shared subscriber editor's serial is the NEW card serial
            # here, keeping that editor identical across all 5 services.
            "sim_new_serial": data.sim_serial,
            "sim_current_serial": data.sim_current_serial,
            "sim_reason_lost_mark": choice_mark(data.sim_replacement_reason == "Mất SIM"),
            "sim_reason_damaged_mark": choice_mark(data.sim_replacement_reason == "Hỏng SIM"),
            "sim_reason_other_mark": choice_mark(data.sim_replacement_reason == "Lý do khác"),
            "sim_reason_other_value": data.sim_replacement_other_reason,
            "sim_request_day": sim_request_day,
            "sim_request_month": sim_request_month,
            "sim_request_year": sim_request_year,
            "sim_request_date_line": f"ngày {sim_request_day} tháng {sim_request_month} năm {sim_request_year}",
            "sim_document_date_line": f"ngày {sim_request_day} tháng {sim_request_month} năm {sim_request_year}",
            "frequent_phone_1": data.frequent_phone_1,
            "frequent_phone_2": data.frequent_phone_2,
            "frequent_phone_3": data.frequent_phone_3,
            "frequent_phone_4": data.frequent_phone_4,
            "frequent_phone_5": data.frequent_phone_5,
            "recent_topup_value": data.recent_topup_value,
            "recent_topup_method": data.recent_topup_method,
            "remaining_validity": data.remaining_validity,
            "account_balance": data.account_balance,
            "last_changed_service": data.last_changed_service,
            "sim_operator_signature_name": data.staff_name.upper(),
        }
        context["sim_operator_signature_given_name"] = _given_name(context["sim_operator_signature_name"])
        return context
