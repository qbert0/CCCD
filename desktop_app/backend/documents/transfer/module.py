from desktop_app.backend.domain.models import DocumentType
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from .schema import TransferSchema


class TransferDocumentModule(BaseDocumentModule):
    document_type = DocumentType.TRANSFER
    suffix = ".docx"
    schema = TransferSchema
    placeholders = frozenset({
        "payment_method", "source_contract_number", "source_contract_day",
        "source_contract_month", "source_contract_year", "registration_form_day",
        "registration_form_month", "registration_form_year", "document_day",
        "document_month", "document_year", "subscriber_number", "transfer_time",
        "transfer_effective_day", "transfer_effective_month", "transfer_effective_year",
        "customer_name", "new_owner_name",
        "customer_headquarters", "new_owner_headquarters", "customer_business_number",
        "new_owner_business_number", "customer_representative", "new_owner_representative",
        "customer_authorization", "new_owner_authorization", "customer_id_number",
        "new_owner_id_number", "customer_issue_date", "new_owner_issue_date",
        "customer_issue_place", "new_owner_issue_place", "customer_birth_date",
        "new_owner_birth_date", "customer_address", "new_owner_address",
        "customer_nationality", "new_owner_nationality", "subscriber_number",
        "customer_representative_signature_name", "customer_representative_signature_given_name",
        "new_owner_signature_name", "new_owner_signature_given_name",
        "provider_representative_signature", "provider_representative_signature_given_name",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "transfer", "00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx"
    )
