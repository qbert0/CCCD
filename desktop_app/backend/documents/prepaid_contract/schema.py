from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import (
    FieldError,
    common_errors,
    party_required,
    person_errors,
    required_errors,
    valid_date,
)


class PrepaidContractSchema:
    @staticmethod
    def required_paths(data: ReportData) -> list[str]:
        paths = [
            "document_date", "subscriber_number", *party_required("customer", data.customer),
            "customer.phone", "service_point_name", "staff_name", "shop_address", "shop_phone",
            "registration_time", "sim_serial", "activation_date",
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
