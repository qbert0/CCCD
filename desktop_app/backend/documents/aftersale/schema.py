from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import FieldError, common_errors, person_errors, required_errors


class AftersaleSchema:
    @staticmethod
    def required_paths(data: ReportData) -> list[str]:
        paths = [
            "document_date", "subscriber_number", "customer.full_name", "customer.id_number",
            "customer.issue_date", "customer.issue_place", "customer.address", "customer.phone",
            "shop_name", "shop_address", "shop_phone", "staff_name", "backup_phone_1",
        ]
        if data.service_action == "Chuyển chủ quyền":
            paths += ["new_owner.full_name", "new_owner.id_number", "new_owner.issue_date", "new_owner.issue_place"]
        return paths

    @classmethod
    def validate(cls, data: ReportData) -> list[FieldError]:
        errors = required_errors(data, cls.required_paths(data))
        if not (data.has_id_attachment or data.has_original_sim or data.other_attachment.strip()):
            errors.append(FieldError("other_attachment", "Cần chọn hoặc mô tả ít nhất một giấy tờ kèm theo"))
        errors += common_errors(
            data,
            phone_paths=("subscriber_number", "shop_phone", "backup_phone_1", "backup_phone_2"),
        )
        errors += person_errors("customer", data.customer, {"id_number", "issue_date", "phone"})
        if data.service_action == "Chuyển chủ quyền":
            errors += person_errors("new_owner", data.new_owner, {"id_number", "issue_date"})
            current_id = "".join(char for char in data.customer.id_number if char.isdigit())
            new_id = "".join(char for char in data.new_owner.id_number if char.isdigit())
            if current_id and new_id and current_id == new_id:
                errors.append(
                    FieldError("new_owner.id_number", "Chủ thuê bao mới phải khác chủ thuê bao hiện tại")
                )
        return errors
