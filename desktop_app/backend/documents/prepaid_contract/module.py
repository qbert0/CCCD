from desktop_app.backend.domain.models import DocumentType, ReportData
from desktop_app.backend.paths import resource_path

from ..base import BaseDocumentModule
from ..renderer import CHECKED_BOX, EMPTY_BOX, _common_context, _date_parts, _given_name
from .schema import PrepaidContractSchema


class PrepaidContractDocumentModule(BaseDocumentModule):
    document_type = DocumentType.PREPAID_CONTRACT
    suffix = ".docx"
    schema = PrepaidContractSchema
    # This template is intentionally edited by the user and may omit fields.
    # Fill exactly the supported placeholders that remain in the DOCX instead
    # of requiring every field in the context to be present in the template.
    allow_missing_placeholders = True
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
        "prepaid_party_a_signature_name", "prepaid_party_a_signature_given_name",
        "provider_representative", "provider_representative_signature",
        "provider_representative_signature_given_name",
        "provider_position", "service_point_name", "staff_name",
        "shop_phone", "registration_time", "subscriber_number", "sim_serial", "activation_date",
    })
    template = resource_path(
        "desktop_app", "backend", "documents", "prepaid_contract", "00_MAU_HOP_DONG_TRA_TRUOC.docx"
    )

    def build_context(self, data: ReportData) -> dict[str, str]:
        """Values copied verbatim from _docx_context()'s own prepaid_*
        block, not re-derived -- a straight extraction (see
        SimChangeFormDocumentModule.build_context for the first one, same
        approach)."""
        customer, new_owner = data.customer, data.new_owner
        is_organization = customer.entity_type == "Tổ chức"
        prepaid_structured = bool(data.prepaid_structured_parties)
        # Bên A ("prepaid_individual"/"prepaid_representative") is either
        # the genuinely separate representative/new_owner pair (structured
        # mode: an org handing the SIM to a specific individual) or just
        # the customer signing for themselves (legacy mode) -- same split
        # prepaid_party_a_signature_name's own text below follows.
        prepaid_representative = data.representative if prepaid_structured else customer
        prepaid_individual = new_owner if prepaid_structured else customer
        day, month, year = _date_parts(data.document_date)
        organization_phones = " - ".join(
            value for value in (data.shop_phone, data.shop_phone_2, data.shop_phone_3) if value
        )

        def authorization(person) -> str:
            return " - ".join(
                value for value in (person.authorization_number, person.authorization_date) if value
            )

        def organization(value: str) -> str:
            return value if prepaid_structured or is_organization else ""

        def individual(value: str) -> str:
            return value if prepaid_structured or not is_organization else ""

        context = {
            **_common_context(data),
            "contract_number": data.contract_number,
            "subscriber_code": data.subscriber_code or data.subscriber_number,
            "document_date_line": f"Ngày {day} tháng {month} năm {year}",
            "prepaid_organization_name": organization(customer.organization_name.upper()),
            "prepaid_headquarters_address": organization(customer.headquarters_address),
            "prepaid_business_number": organization(customer.business_registration_number),
            "prepaid_business_issue_place": organization(customer.business_registration_issue_place),
            "prepaid_business_issue_date": organization(customer.business_registration_issue_date),
            "prepaid_representative_name": organization(
                prepaid_representative.full_name or customer.representative_name
            ),
            "prepaid_representative_position": organization(prepaid_representative.representative_position),
            "prepaid_authorization": organization(authorization(prepaid_representative)),
            "prepaid_organization_id_number": organization(prepaid_representative.id_number),
            "prepaid_organization_issue_place": organization(prepaid_representative.issue_place),
            "prepaid_organization_issue_date": organization(prepaid_representative.issue_date),
            "prepaid_organization_birth_date": organization(prepaid_representative.date_of_birth),
            "prepaid_organization_phone": organization(prepaid_representative.phone),
            "prepaid_organization_email": organization(prepaid_representative.email),
            "prepaid_organization_other_contact": organization(prepaid_representative.other_contact),
            "prepaid_individual_name": individual(prepaid_individual.full_name.upper()),
            "prepaid_individual_id_number": individual(prepaid_individual.id_number),
            "prepaid_individual_issue_place": individual(prepaid_individual.issue_place),
            "prepaid_individual_issue_date": individual(prepaid_individual.issue_date),
            "prepaid_individual_birth_date": individual(prepaid_individual.date_of_birth),
            "prepaid_individual_address": individual(prepaid_individual.address),
            "prepaid_individual_phone": individual(prepaid_individual.phone),
            "prepaid_individual_email": individual(prepaid_individual.email),
            "prepaid_individual_other_contact": individual(prepaid_individual.other_contact),
            "prepaid_individual_nationality": individual(
                (
                    f"{CHECKED_BOX} Việt Nam    {EMPTY_BOX} Nước ngoài"
                    if prepaid_individual.nationality.casefold() == "việt nam"
                    else (
                        f"{EMPTY_BOX} Việt Nam    {CHECKED_BOX} Nước ngoài: "
                        f"{prepaid_individual.foreign_country or prepaid_individual.nationality}"
                    )
                )
                if prepaid_individual.nationality.strip()
                else ""
            ),
            "shop_address": data.provider_unit_address if prepaid_structured else data.shop_address,
            # Bên A's signature is the person actually taking over the
            # subscription: the new owner in structured mode, or the
            # customer signing for themselves in legacy mode (their own
            # representative when they're an organization).
            "prepaid_party_a_signature_name": (
                new_owner.display_name() if prepaid_structured
                else (customer.representative_name if is_organization else customer.display_name())
            ).upper(),
            "provider_representative": data.provider_representative,
            "provider_position": data.provider_position,
            "service_point_name": data.service_point_name,
            "staff_name": data.staff_name.upper(),
            "shop_phone": data.service_point_phone if prepaid_structured else organization_phones,
            "registration_time": data.registration_time,
            "sim_serial": data.sim_serial,
        }
        context["prepaid_party_a_signature_given_name"] = _given_name(
            context["prepaid_party_a_signature_name"]
        )
        return context
