from desktop_app.backend.domain.models import DocumentType
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from .schema import BeautifulNumberSchema


class BeautifulNumberDocumentModule(BaseDocumentModule):
    document_type = DocumentType.BEAUTIFUL_NUMBER
    suffix = ".pdf"
    schema = BeautifulNumberSchema
    template = resource_path(
        "desktop_app", "backend", "documents", "beautiful_number", "00_MAU_PHU_LUC_CAM_KET_SO_DEP.pdf"
    )
