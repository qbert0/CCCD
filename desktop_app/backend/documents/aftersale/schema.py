from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import (
    FieldError,
    common_errors,
    organization_information_required,
    person_errors,
    required_errors,
    subscriber_list_errors,
)


class AftersaleSchema:
    @staticmethod
    def required_paths(data: ReportData) -> list[str]:
        paths = (
            organization_information_required("customer")
            if data.customer.entity_type == "Tổ chức"
            else [
                "customer.full_name", "customer.id_number", "customer.issue_date",
                "customer.issue_place", "customer.address",
            ]
        )
        if data.service_action == "Chuyển chủ quyền":
            paths += [
                "new_owner.full_name", "new_owner.id_number",
                "new_owner.issue_date", "new_owner.issue_place",
            ]
        return paths

    @classmethod
    def validate(cls, data: ReportData) -> list[FieldError]:
        errors = required_errors(data, cls.required_paths(data))
        errors += subscriber_list_errors(data)
        if not (data.has_id_attachment or data.has_original_sim or data.other_attachment.strip()):
            errors.append(FieldError("other_attachment", "Cần chọn hoặc mô tả ít nhất một giấy tờ kèm theo"))
        errors += common_errors(
            data,
            date_paths=("customer.business_registration_issue_date",),
            phone_paths=(),
        )
        if data.customer.entity_type != "Tổ chức":
            errors += person_errors("customer", data.customer, {"id_number", "issue_date"})
        if data.service_action == "Chuyển chủ quyền":
            errors += person_errors("new_owner", data.new_owner, {"id_number", "issue_date"})
        return errors
