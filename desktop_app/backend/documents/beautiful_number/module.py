from desktop_app.backend.domain.models import DocumentType, ReportData
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from ..renderer import _common_context, _date_parts
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

    def build_context(self, data: ReportData) -> dict[str, str]:
        day, month, year = _date_parts(data.document_date)
        return {
            **_common_context(data),
            "beautiful_number_day": day,
            "beautiful_number_month": month,
            "beautiful_number_year": year,
            "beautiful_number_customer_name": data.customer.display_name().title(),
            "beautiful_number_customer_id": data.customer.id_number,
        }
