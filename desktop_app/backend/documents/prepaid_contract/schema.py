from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import (
    FieldError,
    common_errors,
    duplicate_subscriber_errors,
    organization_information_required,
    party_required,
    personal_information_required,
    person_errors,
    required_errors,
    valid_date,
    valid_phone,
)


class PrepaidContractSchema:
    @staticmethod
    def required_paths(data: ReportData) -> list[str]:
        if data.prepaid_structured_parties:
            return [
                *organization_information_required("customer"),
                *personal_information_required("representative"),
                "representative.representative_position",
                *personal_information_required("new_owner"),
                "provider_unit_address", "provider_representative",
                "staff_name", "service_point_address", "service_point_phone",
            ]
        paths = [
            "document_date", "subscriber_number", *party_required("customer", data.customer),
            "staff_name", "shop_address", "shop_phone", "activation_date",
        ]
        if data.customer.entity_type == "Tổ chức":
            paths += [
                "customer.business_registration_issue_place",
                "customer.business_registration_issue_date",
                "customer.date_of_birth",
                "customer.representative_position",
            ]
        return paths

    @classmethod
    def validate(cls, data: ReportData) -> list[FieldError]:
        if data.prepaid_structured_parties:
            errors = required_errors(data, cls.required_paths(data))
            errors += person_errors(
                "representative", data.representative,
                {"id_number", "date_of_birth", "issue_date", "phone", "email"},
            )
            errors += person_errors(
                "new_owner", data.new_owner,
                {"id_number", "date_of_birth", "issue_date", "phone", "email"},
            )
            registration_date = data.customer.business_registration_issue_date
            if registration_date and not valid_date(registration_date):
                errors.append(FieldError(
                    "customer.business_registration_issue_date",
                    "Ngày phải đúng định dạng DD/MM/YYYY",
                ))
            if data.service_point_phone and not valid_phone(data.service_point_phone):
                errors.append(FieldError(
                    "service_point_phone", "Số điện thoại phải gồm từ 9 đến 12 chữ số"
                ))

            rows = data.prepaid_subscribers[:5] or [
                {"subscriber_number": "", "sim_serial": "", "activation_date": ""}
            ]
            # sim_serial has no natural default and isn't identity or a
            # phone number -- by explicit request, only phone/subscriber
            # numbers (plus real identity) stay hard-required; a missing
            # SIM serial prints as a blank line instead of blocking
            # generation, same as every other optional field already does.
            required_names = {"subscriber_number": "Số thuê bao", "activation_date": "Ngày hòa mạng"}
            for index, row in enumerate(rows):
                for name, label in required_names.items():
                    value = str(row.get(name, "") or "").strip()
                    path = f"prepaid_subscribers.{index}.{name}"
                    if not value:
                        errors.append(FieldError(path, f"{label} là thông tin bắt buộc"))
                    elif name == "activation_date" and not valid_date(value):
                        errors.append(FieldError(path, "Ngày phải đúng định dạng DD/MM/YYYY"))
                number = str(row.get("subscriber_number", "") or "").strip()
                if number and not valid_phone(number):
                    errors.append(FieldError(
                        f"prepaid_subscribers.{index}.subscriber_number", "Số điện thoại phải gồm từ 9 đến 12 chữ số"
                    ))
            errors += duplicate_subscriber_errors(rows, "prepaid_subscribers")
            return errors

        errors = required_errors(data, cls.required_paths(data))
        errors += common_errors(
            data,
            ("activation_date",),
            ("subscriber_number", "shop_phone"),
        )
        errors += person_errors(
            "customer",
            data.customer,
            {"id_number", "date_of_birth", "issue_date", "authorization_date", "phone", "email"},
        )
        registration_date = data.customer.business_registration_issue_date
        if registration_date and not valid_date(registration_date):
            errors.append(
                FieldError(
                    "customer.business_registration_issue_date",
                    "Ngày phải đúng định dạng DD/MM/YYYY",
                )
            )
        return errors
