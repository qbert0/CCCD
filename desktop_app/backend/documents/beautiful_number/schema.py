from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import FieldError, common_errors, person_errors, required_errors


class BeautifulNumberSchema:
    @staticmethod
    def required_paths(_data: ReportData) -> list[str]:
        return ["document_date", "subscriber_number", "customer.full_name", "customer.id_number", "commitment_months", "monthly_fee"]

    @classmethod
    def validate(cls, data: ReportData) -> list[FieldError]:
        return (
            required_errors(data, cls.required_paths(data))
            + common_errors(data)
            + person_errors("customer", data.customer, {"id_number"})
        )
