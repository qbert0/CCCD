from desktop_app.backend.domain.models import DocumentType
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from .schema import AftersaleSchema


class AftersaleDocumentModule(BaseDocumentModule):
    document_type = DocumentType.AFTERSALE
    suffix = ".docx"
    schema = AftersaleSchema
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
    template = resource_path(
        "desktop_app", "backend", "documents", "aftersale", "00_MAU_CAM_KET_SAU_BAN_HANG.docx"
    )
