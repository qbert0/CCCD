from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import (
    FieldError,
    person_errors,
    required_errors,
    subscriber_list_errors,
)


class ServiceRegistrationSchema:
    """Only ever used by QUANG_HA_STT, whose customer is always an
    individual (see SERVICE_TEMPLATE_CUSTOMER_ENTITY_TYPE) -- no org/
    individual branch needed, same simplification as
    OwnershipConfirmationSchema."""

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
        rows = [row for row in data.subscribers if str(row.get("subscriber_number", "")).strip()]
        # The reference form ("...Áp dụng trong trường hợp Khách hàng đăng
        # ký 03 số thuê bao đầu tiên") is a genuinely fixed 3-row table --
        # see _fill_service_registration_table in renderer.py -- so a 4th+
        # subscriber here would silently be dropped rather than printed.
        if len(rows) > 3:
            errors.append(FieldError(
                "subscribers.3.subscriber_number",
                "Phiếu đăng ký dịch vụ chỉ áp dụng cho tối đa 3 số thuê bao",
            ))
        errors += person_errors("customer", data.customer, {"id_number", "issue_date"})
        return errors
