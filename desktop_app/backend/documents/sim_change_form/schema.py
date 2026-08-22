from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import (
    FieldError,
    common_errors,
    person_errors,
    required_errors,
    subscriber_list_errors,
)


class SimChangeFormSchema:
    @staticmethod
    def required_paths(data: ReportData) -> list[str]:
        return [
            "customer.full_name",
            "customer.id_number",
            "customer.issue_date",
            "customer.issue_place",
            "customer.address",
            "sim_replacement_reason",
        ]

    @classmethod
    def validate(cls, data: ReportData) -> list[FieldError]:
        errors = required_errors(data, cls.required_paths(data))
        errors += subscriber_list_errors(data)
        rows = [row for row in data.subscribers if str(row.get("subscriber_number", "")).strip()]
        if rows and not str(rows[0].get("sim_serial", "")).strip():
            errors.append(FieldError("subscribers.0.sim_serial", "Cần nhập số seri SIM mới"))
        # Thay SIM is physically one card swap per phiếu -- the shared
        # subscriber-list editor allows adding more rows (needed by the
        # other 4 services), but this document has exactly one "Số thuê
        # bao" line, so a 2nd+ row here would silently only ever print the
        # first and hide that a real subscriber never made it onto the form.
        if len(rows) > 1:
            errors.append(FieldError(
                "subscribers.1.subscriber_number",
                "Thay SIM chỉ áp dụng cho một thuê bao mỗi lần",
            ))
        if data.sim_replacement_reason == "Lý do khác" and not data.sim_replacement_other_reason.strip():
            errors.append(FieldError("sim_replacement_other_reason", "Cần ghi rõ lý do thay SIM"))
        errors += common_errors(data, date_paths=(), phone_paths=())
        errors += person_errors("customer", data.customer, {"id_number", "issue_date"})
        return errors
