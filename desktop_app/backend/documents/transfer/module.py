from desktop_app.backend.domain.models import DocumentType, ReportData
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from ..renderer import _date_parts, _given_name, _hour_only, _common_context
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

    def build_context(self, data: ReportData) -> dict[str, str]:
        """Values copied verbatim from _docx_context()'s own
        transfer/customer_*/new_owner_* block, not re-derived -- a
        straight extraction (see SimChangeFormDocumentModule.build_context
        for the first one, same approach). transfer_contract_basis/
        transfer_document_intro/transfer_agreement_intro/
        transfer_effective_sentence are deliberately NOT here -- confirmed
        they aren't in this module's own `placeholders` (the current
        template doesn't use them; that's an existing, unrelated fact
        about the template, not something this migration changes)."""
        customer, new_owner = data.customer, data.new_owner
        day, month, year = _date_parts(data.document_date)
        contract_day, contract_month, contract_year = _date_parts(data.source_contract_date)
        form_day, form_month, form_year = _date_parts(data.registration_form_date)
        effective_day, effective_month, effective_year = _date_parts(data.transfer_effective_date)

        def authorization(person) -> str:
            return " - ".join(
                value for value in (person.authorization_number, person.authorization_date) if value
            )

        def party_organization(person, value: str) -> str:
            return value if person.entity_type == "Tổ chức" else ""

        context = {
            **_common_context(data),
            "document_day": f" {day}",
            "document_month": month,
            "document_year": year,
            "payment_method": data.payment_method,
            "source_contract_number": data.source_contract_number or "…………",
            "source_contract_day": contract_day,
            "source_contract_month": contract_month,
            "source_contract_year": f"{contract_year} ",
            "registration_form_day": f" {form_day}",
            "registration_form_month": form_month,
            "registration_form_year": form_year,
            "transfer_time": f"{_hour_only(data.transfer_time) or '……'} ",
            "transfer_effective_day": effective_day,
            "transfer_effective_month": effective_month,
            "transfer_effective_year": effective_year,
            "customer_representative_signature_name": (
                customer.full_name or customer.representative_name
            ).upper(),
            "new_owner_signature_name": new_owner.display_name().upper(),
            "customer_name": customer.display_name().upper(),
            "customer_headquarters": party_organization(customer, customer.headquarters_address),
            "customer_business_number": party_organization(customer, customer.business_registration_number),
            "customer_representative": party_organization(
                customer, (customer.full_name or customer.representative_name).upper()
            ),
            "customer_authorization": party_organization(customer, authorization(customer)),
            "customer_id_number": customer.id_number,
            "customer_issue_date": customer.issue_date,
            "customer_issue_place": customer.issue_place,
            "customer_birth_date": customer.date_of_birth,
            "customer_address": customer.address,
            "customer_nationality": customer.nationality,
            "new_owner_name": new_owner.display_name().upper(),
            "new_owner_headquarters": party_organization(new_owner, new_owner.headquarters_address),
            "new_owner_business_number": party_organization(new_owner, new_owner.business_registration_number),
            "new_owner_representative": party_organization(
                new_owner, (new_owner.representative_name or new_owner.full_name).upper()
            ),
            "new_owner_authorization": party_organization(new_owner, authorization(new_owner)),
            "new_owner_id_number": new_owner.id_number,
            "new_owner_issue_date": new_owner.issue_date,
            "new_owner_issue_place": new_owner.issue_place,
            "new_owner_birth_date": new_owner.date_of_birth,
            "new_owner_address": new_owner.address,
            "new_owner_nationality": new_owner.nationality,
        }
        context["customer_representative_signature_given_name"] = _given_name(
            context["customer_representative_signature_name"]
        )
        context["new_owner_signature_given_name"] = _given_name(context["new_owner_signature_name"])
        return context
