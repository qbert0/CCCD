from desktop_app.backend.domain.models import DocumentType, ReportData
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from ..renderer import CHECKED_BOX, EMPTY_BOX, _common_context, _date_parts, _given_name, dotted
from .schema import ServiceRegistrationSchema


class ServiceRegistrationDocumentModule(BaseDocumentModule):
    document_type = DocumentType.SERVICE_REGISTRATION
    suffix = ".docx"
    schema = ServiceRegistrationSchema
    # The "TT / Số thuê bao / Số sê-ri SIM / Ngày hòa mạng" table isn't a
    # placeholder -- like prepaid_contract's own table, it's filled by
    # _fill_service_registration_table() writing into a FIXED 3 pre-
    # existing template rows (never cloned -- the reference form is
    # explicitly capped at 3 subscribers), see renderer.py.
    placeholders = frozenset({
        "service_registration_day", "service_registration_month", "service_registration_year",
        "service_registration_customer_name", "service_registration_customer_id_number",
        "service_registration_customer_issue_date", "service_registration_customer_issue_place",
        "service_registration_customer_birth_date", "service_registration_customer_address",
        "service_registration_customer_phone", "service_registration_customer_email",
        "service_registration_customer_nationality",
        "service_point_name", "service_point_address", "service_point_phone",
        "registration_time", "staff_name",
        # Section II.1's own "Người đại diện: ... Chức vụ: ..." mention --
        # same 2 fields/role as prepaid_contract's identical line (Bên B's
        # own signing representative, the same person who signs "ĐẠI DIỆN
        # BÊN CUNG CẤP DỊCH VỤ VIỄN THÔNG" via provider_representative_signature
        # below -- see _common_context's own note on why that's a separate key).
        "provider_representative", "provider_position",
        "customer_signature_name", "customer_signature_given_name",
        "provider_representative_signature", "provider_representative_signature_given_name",
        "service_registration_clerk_signature_name", "service_registration_clerk_signature_given_name",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "service_registration",
        "00_MAU_PHIEU_DANG_KY_DICH_VU.docx",
    )

    def build_context(self, data: ReportData) -> dict[str, str]:
        """Values mirror AftersaleDocumentModule.build_context's own
        customer-identity block and PrepaidContractDocumentModule.build_context's
        own "điểm giao dịch" block -- this document only ever applies to
        an individual customer (see schema.py's own note), so there's no
        org-vs-individual branch to carry over from either."""
        customer = data.customer
        day, month, year = _date_parts(data.document_date)
        context = {
            **_common_context(data),
            "service_registration_day": dotted(day, 4),
            "service_registration_month": dotted(month, 4),
            "service_registration_year": dotted(year, 6),
            "service_registration_customer_name": dotted(customer.display_name().upper(), 46),
            "service_registration_customer_id_number": dotted(customer.id_number, 18),
            "service_registration_customer_issue_date": dotted(customer.issue_date, 14),
            "service_registration_customer_issue_place": dotted(customer.issue_place, 26),
            "service_registration_customer_birth_date": dotted(customer.date_of_birth, 12),
            "service_registration_customer_address": dotted(customer.address, 48),
            "service_registration_customer_phone": dotted(customer.phone, 20),
            "service_registration_customer_email": dotted(customer.email, 30),
            # The source form prints this as a real 2-option checkbox
            # ("☐ Việt Nam; ☐ Nước ngoài: ..."), not a free-text field --
            # per direct instruction, checkboxes stay checkboxes (printing
            # loses a plain-text substitute anyway). Same CHECKED_BOX/
            # EMPTY_BOX pattern as prepaid_contract's own
            # prepaid_individual_nationality.
            "service_registration_customer_nationality": (
                (
                    f"{CHECKED_BOX} Việt Nam    {EMPTY_BOX} Nước ngoài"
                    if customer.nationality.casefold() == "việt nam"
                    else (
                        f"{EMPTY_BOX} Việt Nam    {CHECKED_BOX} Nước ngoài: "
                        f"{customer.foreign_country or customer.nationality}"
                    )
                )
                if customer.nationality.strip()
                else f"{EMPTY_BOX} Việt Nam    {EMPTY_BOX} Nước ngoài"
            ),
            "service_point_name": data.service_point_name,
            "service_point_address": data.service_point_address,
            "service_point_phone": data.service_point_phone,
            "registration_time": data.registration_time,
            "staff_name": data.staff_name.upper(),
            "provider_representative": data.provider_representative,
            "provider_position": data.provider_position,
            "service_registration_clerk_signature_name": data.staff_name.upper(),
        }
        context["service_registration_clerk_signature_given_name"] = _given_name(
            context["service_registration_clerk_signature_name"]
        )
        return context
