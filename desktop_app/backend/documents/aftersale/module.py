from desktop_app.backend.domain.models import DocumentType
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from .schema import AftersaleSchema


class AftersaleDocumentModule(BaseDocumentModule):
    document_type = DocumentType.AFTERSALE
    suffix = ".docx"
    schema = AftersaleSchema
    placeholders = frozenset({
        "aftersale_document_date_line", "shop_name", "shop_address", "shop_phone", "customer_name",
        "customer_id_number", "customer_issue_date", "customer_issue_place", "customer_address",
        "customer_phone", "attachment_checkboxes", "other_attachment_line",
        "update_information_choice", "update_information_commitment", "replace_sim_choice",
        "replace_sim_commitment", "transfer_choice", "aftersale_transfer_commitment",
        "aftersale_common_commitment", "backup_phone_commitment", "staff_name",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "aftersale", "00_MAU_CAM_KET_SAU_BAN_HANG.docx"
    )
