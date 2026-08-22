from desktop_app.backend.domain.models import DocumentType
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
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
        "provider_representative", "provider_representative_given_name",
        "sim_operator_signature_name", "sim_operator_signature_given_name",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "sim_change_form",
        "00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx",
    )
