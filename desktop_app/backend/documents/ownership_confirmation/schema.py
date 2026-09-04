from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import (
    FieldError,
    person_errors,
    required_errors,
    subscriber_list_errors,
)


class OwnershipConfirmationSchema:
    """Unlike aftersale's own schema, this document is only ever used by
    QUANG_HA_STT, whose customer is always an individual (see
    SERVICE_TEMPLATE_CUSTOMER_ENTITY_TYPE) -- no org/individual branch
    needed here."""

    @staticmethod
    def required_paths(data: ReportData) -> list[str]:
        return [
            "customer.full_name", "customer.id_number", "customer.issue_date",
            "customer.issue_place", "customer.address",
        ]

    @classmethod
    def validate(cls, data: ReportData) -> list[FieldError]:
        errors = required_errors(data, cls.required_paths(data))
        errors += subscriber_list_errors(data)
        if not (data.has_id_attachment or data.has_original_sim or data.other_attachment.strip()):
            errors.append(FieldError("other_attachment", "Cần chọn hoặc mô tả ít nhất một giấy tờ kèm theo"))
        errors += person_errors("customer", data.customer, {"id_number", "issue_date"})
        return errors
