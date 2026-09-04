from desktop_app.backend.domain.models import DocumentType, ReportData
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from ..renderer import _common_context, _date_parts, _given_name, choice_mark, dotted
from .schema import OwnershipConfirmationSchema


class OwnershipConfirmationDocumentModule(BaseDocumentModule):
    document_type = DocumentType.OWNERSHIP_CONFIRMATION
    suffix = ".docx"
    schema = OwnershipConfirmationSchema
    # The STT/Số thuê bao/Họ tên/Số GTTT/Ngày cấp table isn't a placeholder
    # -- like beautiful_number's own table, it's filled by
    # _fill_ownership_confirmation_table() cloning the template's own data
    # row per subscriber entry (see renderer.py).
    placeholders = frozenset({
        "ownership_day", "ownership_month", "ownership_year",
        "ownership_customer_name", "ownership_customer_id_number",
        "ownership_customer_issue_date", "ownership_customer_issue_place",
        "ownership_customer_address", "ownership_customer_phone",
        "id_attachment_mark", "sim_attachment_mark",
        "other_attachment_mark", "other_attachment_value",
        "ownership_requester_signature_name", "ownership_requester_signature_given_name",
        "ownership_clerk_signature_name", "ownership_clerk_signature_given_name",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "ownership_confirmation",
        "00_MAU_GIAY_CAM_KET_XAC_NHAN_QUYEN.docx",
    )

    def build_context(self, data: ReportData) -> dict[str, str]:
        """Values mirror AftersaleDocumentModule.build_context's own
        customer-identity/attachment block -- this document only ever
        applies to an individual customer (see schema.py's own note), so
        there's no org-vs-individual branch to carry over from aftersale."""
        customer = data.customer
        day, month, year = _date_parts(data.document_date)
        context = {
            **_common_context(data),
            "ownership_day": dotted(day, 4),
            "ownership_month": dotted(month, 4),
            "ownership_year": dotted(year, 6),
            "ownership_customer_name": dotted(customer.display_name().upper(), 46),
            "ownership_customer_id_number": dotted(customer.id_number, 18),
            "ownership_customer_issue_date": dotted(customer.issue_date, 14),
            "ownership_customer_issue_place": dotted(customer.issue_place, 26),
            "ownership_customer_address": dotted(customer.address, 48),
            "ownership_customer_phone": dotted(customer.phone, 24),
            # Same shared attachments checkbox group aftersale's own block
            # uses -- one physical set of checkboxes per case, so both
            # documents in QUANG_HA_STT's set print the same check state.
            "id_attachment_mark": choice_mark(data.has_id_attachment),
            "sim_attachment_mark": choice_mark(data.has_original_sim),
            "other_attachment_mark": choice_mark(bool(data.other_attachment.strip())),
            "other_attachment_value": dotted(data.other_attachment, 48),
            "ownership_requester_signature_name": customer.display_name().upper(),
            "ownership_clerk_signature_name": data.staff_name.upper(),
        }
        context["ownership_requester_signature_given_name"] = _given_name(
            context["ownership_requester_signature_name"]
        )
        context["ownership_clerk_signature_given_name"] = _given_name(
            context["ownership_clerk_signature_name"]
        )
        return context
