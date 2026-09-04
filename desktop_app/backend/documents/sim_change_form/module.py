from desktop_app.backend.domain.models import DocumentType, ReportData
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from ..renderer import (
    CHECKED_BOX,
    EMPTY_BOX,
    _common_context,
    _date_parts,
    _given_name,
    _subscriber_numbers_joined,
    choice_mark,
    dotted,
)
from .schema import SimChangeFormSchema


class SimChangeFormDocumentModule(BaseDocumentModule):
    document_type = DocumentType.SIM_CHANGE_FORM
    suffix = ".docx"
    schema = SimChangeFormSchema
    allow_missing_placeholders = True
    placeholders = frozenset({
        "sim_customer_name", "sim_customer_birth_date", "sim_customer_gender",
        "sim_customer_nationality", "sim_customer_id_number", "sim_customer_issue_date",
        "sim_customer_issue_place", "sim_customer_address", "sim_customer_phone",
        "sim_customer_email", "sim_subscriber_number", "sim_new_serial", "sim_current_serial",
        "sim_reason_lost_mark", "sim_reason_damaged_mark", "sim_reason_other_mark",
        "sim_reason_other_value", "sim_request_day", "sim_request_month", "sim_request_year",
        "sim_request_date_line", "sim_document_date_line",
        "frequent_phone_1", "frequent_phone_2", "frequent_phone_3", "frequent_phone_4",
        "frequent_phone_5", "activation_date", "recent_topup_value", "recent_topup_method",
        "remaining_validity", "account_balance", "last_changed_service",
        "customer_signature_name", "customer_signature_given_name",
        "provider_representative_signature", "provider_representative_signature_given_name",
        "sim_operator_signature_name", "sim_operator_signature_given_name",
        # "Thông tin khách hàng thay đổi" column -- the actual physical
        # signer's updated info, whenever this document represents a real
        # old -> new change (QUANG_HA_STT: Bên A/customer is the fixed
        # "Người đại diện 2" identity that originally registered the
        # number, new_owner is the actual walk-in customer scanned via
        # QR). Left blank/dotted for SIM_REPLACEMENT/QUANG_HA_SIM_CK,
        # whose new_owner is always empty -- see build_context below.
        "sim_customer_new_name", "sim_customer_new_id_number",
        "sim_customer_new_birth_date", "sim_customer_new_gender",
        "sim_customer_new_issue_date", "sim_customer_new_issue_place",
        "sim_customer_new_address", "sim_customer_new_phone",
        "sim_customer_new_email", "sim_customer_new_nationality",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "sim_change_form",
        "00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx",
    )

    def build_context(self, data: ReportData) -> dict[str, str]:
        """First document type migrated off the renderer._docx_context()
        monolith (see BaseDocumentModule.build_context's own docstring) --
        every field below is this template's own placeholder set (see
        `placeholders` above) minus the 4 shared with other document types,
        which come from _common_context() instead. Values copied verbatim
        from _docx_context()'s own sim_* block, not re-derived from
        scratch, so this is a straight extraction, not a rewrite."""
        customer = data.customer
        new_owner = data.new_owner
        # True only when this case actually carries a 2nd, distinct party
        # (QUANG_HA_STT) -- SIM_REPLACEMENT/QUANG_HA_SIM_CK never populate
        # new_owner (single-party services), so this stays False for them
        # and the "thay đổi" column/signature both fall back to their
        # original blank-dots/customer-signs-for-themselves behavior.
        has_new_owner = bool(new_owner.full_name.strip())
        sim_request_day, sim_request_month, sim_request_year = _date_parts(data.document_date)

        def nationality_mark(person) -> str:
            if not person.nationality.strip():
                return f"{EMPTY_BOX} Việt Nam    {EMPTY_BOX} Nước ngoài"
            if person.nationality.casefold() == "việt nam":
                return f"{CHECKED_BOX} Việt Nam    {EMPTY_BOX} Nước ngoài"
            return f"{EMPTY_BOX} Việt Nam    {CHECKED_BOX} Nước ngoài: {person.foreign_country or person.nationality}"

        context = {
            **_common_context(data),
            "sim_customer_name": customer.display_name().upper(),
            "sim_customer_birth_date": customer.date_of_birth,
            "sim_customer_gender": customer.gender,
            "sim_customer_nationality": customer.nationality,
            "sim_customer_id_number": customer.id_number,
            "sim_customer_issue_date": customer.issue_date,
            "sim_customer_issue_place": customer.issue_place,
            "sim_customer_address": customer.address,
            # The shop's OWN contact number (already auto-defaulted from the
            # saved company profile), not something the clerk types per case.
            "sim_customer_phone": data.shop_phone,
            "sim_customer_email": customer.email,
            "sim_subscriber_number": _subscriber_numbers_joined(data),
            # The shared subscriber editor's serial is the NEW card serial
            # here, keeping that editor identical across all 5 services.
            "sim_new_serial": data.sim_serial,
            "sim_current_serial": data.sim_current_serial,
            "sim_reason_lost_mark": choice_mark(data.sim_replacement_reason == "Mất SIM"),
            "sim_reason_damaged_mark": choice_mark(data.sim_replacement_reason == "Hỏng SIM"),
            "sim_reason_other_mark": choice_mark(data.sim_replacement_reason == "Lý do khác"),
            "sim_reason_other_value": data.sim_replacement_other_reason,
            "sim_request_day": sim_request_day,
            "sim_request_month": sim_request_month,
            "sim_request_year": sim_request_year,
            "sim_request_date_line": f"ngày {sim_request_day} tháng {sim_request_month} năm {sim_request_year}",
            "sim_document_date_line": f"ngày {sim_request_day} tháng {sim_request_month} năm {sim_request_year}",
            "frequent_phone_1": data.frequent_phone_1,
            "frequent_phone_2": data.frequent_phone_2,
            "frequent_phone_3": data.frequent_phone_3,
            "frequent_phone_4": data.frequent_phone_4,
            "frequent_phone_5": data.frequent_phone_5,
            "recent_topup_value": data.recent_topup_value,
            "recent_topup_method": data.recent_topup_method,
            "remaining_validity": data.remaining_validity,
            "account_balance": data.account_balance,
            "last_changed_service": data.last_changed_service,
            "sim_operator_signature_name": data.staff_name.upper(),
            # PersonData's own dataclass defaults (issue_place in
            # particular: "Cục Cảnh sát QLHC về TTXH", never an empty
            # string) leak through an unset new_owner -- gate every field
            # behind has_new_owner explicitly rather than trusting
            # dotted()'s own empty-string check, or SIM_REPLACEMENT/
            # QUANG_HA_SIM_CK's blank new_owner would still print that
            # default place name instead of the intended blank dots.
            "sim_customer_new_name": dotted(new_owner.display_name().upper() if has_new_owner else "", 28),
            "sim_customer_new_id_number": dotted(new_owner.id_number if has_new_owner else "", 16),
            "sim_customer_new_birth_date": dotted(new_owner.date_of_birth if has_new_owner else "", 12),
            "sim_customer_new_gender": dotted(new_owner.gender if has_new_owner else "", 16),
            "sim_customer_new_issue_date": dotted(new_owner.issue_date if has_new_owner else "", 12),
            "sim_customer_new_issue_place": dotted(new_owner.issue_place if has_new_owner else "", 28),
            "sim_customer_new_address": dotted(new_owner.address if has_new_owner else "", 36),
            "sim_customer_new_phone": dotted(new_owner.phone if has_new_owner else "", 16),
            "sim_customer_new_email": dotted(new_owner.email if has_new_owner else "", 24),
            "sim_customer_new_nationality": (
                nationality_mark(new_owner) if has_new_owner
                else f"{EMPTY_BOX} Việt Nam    {EMPTY_BOX} Nước ngoài"
            ),
        }
        context["sim_operator_signature_given_name"] = _given_name(context["sim_operator_signature_name"])
        # "KHÁCH HÀNG ĐẠI DIỆN" signs in person -- for QUANG_HA_STT that's
        # always the actual walk-in customer (new_owner), never the fixed
        # "Người đại diện 2" identity that only exists on paper for the
        # original registration (representative_2 is never physically
        # present to sign this document). Every other caller of this
        # module keeps _common_context's own customer_signature_name
        # (the customer signs for themselves) unchanged.
        if has_new_owner:
            context["customer_signature_name"] = new_owner.display_name().upper()
            context["customer_signature_given_name"] = _given_name(context["customer_signature_name"])
        return context
