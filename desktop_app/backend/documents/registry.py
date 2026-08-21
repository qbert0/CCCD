from __future__ import annotations

from desktop_app.backend.domain.models import DocumentType, ReportData

from .aftersale import AftersaleDocumentModule
from .base import BaseDocumentModule
from .beautiful_number import BeautifulNumberDocumentModule
from .prepaid_contract import PrepaidContractDocumentModule
from .sim_change_form import SimChangeFormDocumentModule
from .transfer import TransferDocumentModule


class DocumentRegistry:
    def __init__(self) -> None:
        modules = [
            TransferDocumentModule(),
            AftersaleDocumentModule(),
            BeautifulNumberDocumentModule(),
            PrepaidContractDocumentModule(),
            SimChangeFormDocumentModule(),
        ]
        self._modules = {module.document_type: module for module in modules}

    def get(self, document_type: DocumentType) -> BaseDocumentModule:
        return self._modules[document_type]

    def for_data(self, data: ReportData) -> BaseDocumentModule:
        return self.get(data.document_type)
