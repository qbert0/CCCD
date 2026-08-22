from desktop_app.backend.domain.models import DocumentType
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from .schema import BeautifulNumberSchema


class BeautifulNumberDocumentModule(BaseDocumentModule):
    document_type = DocumentType.BEAUTIFUL_NUMBER
    suffix = ".docx"
    schema = BeautifulNumberSchema
    # The subscriber table itself isn't a placeholder -- it's filled by
    # _fill_beautiful_number_table() cloning the template's own data row,
    # since it needs an unbounded number of rows (see
    # ReportData.beautiful_subscribers).
    placeholders = frozenset({
        "beautiful_number_day", "beautiful_number_month", "beautiful_number_year",
        "beautiful_number_customer_name", "beautiful_number_customer_id",
        "customer_signature_name", "customer_signature_given_name",
        "provider_representative_signature", "provider_representative_signature_given_name",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "beautiful_number", "00_MAU_PHU_LUC_CAM_KET_SO_DEP_editable.docx"
    )
