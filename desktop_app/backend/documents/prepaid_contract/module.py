from desktop_app.backend.domain.models import DocumentType
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from .schema import PrepaidContractSchema


class PrepaidContractDocumentModule(BaseDocumentModule):
    document_type = DocumentType.PREPAID_CONTRACT
    suffix = ".docx"
    schema = PrepaidContractSchema
    placeholders = frozenset({
        "contract_number", "subscriber_code", "document_date_line", "prepaid_organization_name",
        "prepaid_headquarters_address", "prepaid_business_number", "prepaid_business_issue_place",
        "prepaid_business_issue_date", "prepaid_representative_name",
        "prepaid_representative_position", "prepaid_authorization",
        "prepaid_organization_id_number", "prepaid_organization_issue_place",
        "prepaid_organization_issue_date", "prepaid_organization_birth_date",
        "prepaid_organization_phone", "prepaid_organization_email",
        "prepaid_organization_other_contact", "prepaid_individual_name",
        "prepaid_individual_id_number", "prepaid_individual_issue_place",
        "prepaid_individual_issue_date", "prepaid_individual_birth_date",
        "prepaid_individual_address", "prepaid_individual_phone", "prepaid_individual_email",
        "prepaid_individual_other_contact", "prepaid_individual_nationality", "shop_address",
        "provider_representative", "provider_position", "service_point_name", "staff_name",
        "shop_phone", "registration_time", "subscriber_number", "sim_serial", "activation_date",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "prepaid_contract", "00_MAU_HOP_DONG_TRA_TRUOC.docx"
    )
