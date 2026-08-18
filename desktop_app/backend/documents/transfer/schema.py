import re
import unicodedata

from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import (
    FieldError, common_errors, party_required, personal_information_required,
    person_errors, required_errors,
)


class TransferSchema:
    @staticmethod
    def required_paths(data: ReportData) -> list[str]:
        paths = ["document_date", "subscriber_number", "payment_method", "transfer_effective_date"]
        paths += (
            [
                "customer.organization_name",
                "customer.headquarters_address",
                "customer.business_registration_number",
                *personal_information_required("customer"),
            ]
            if data.customer.entity_type == "Tổ chức"
            else party_required("customer", data.customer)
        )
        paths += personal_information_required("new_owner")
        if data.new_owner.entity_type == "Tổ chức":
            paths += [
                "new_owner.organization_name",
                "new_owner.headquarters_address",
                "new_owner.business_registration_number",
            ]
        return paths

    @classmethod
    def validate(cls, data: ReportData) -> list[FieldError]:
        errors = required_errors(data, cls.required_paths(data))
        if not (data.source_contract_number.strip() or data.registration_form_date.strip()):
            errors.append(FieldError("source_contract_number", "Cần nhập số hợp đồng hoặc ngày Phiếu đăng ký dịch vụ"))
        if data.source_contract_number.strip() and not data.source_contract_date.strip():
            errors.append(FieldError("source_contract_date", "Ngày hợp đồng là bắt buộc khi đã nhập số hợp đồng"))
        if data.source_contract_date.strip() and not data.source_contract_number.strip():
            errors.append(FieldError("source_contract_number", "Số hợp đồng là bắt buộc khi đã nhập ngày hợp đồng"))
        transfer_hour = str(data.transfer_time or "").strip()
        if transfer_hour and (
            not re.fullmatch(r"\d{1,2}", transfer_hour)
            or not 0 <= int(transfer_hour) <= 23
        ):
            errors.append(FieldError("transfer_time", "Giờ chuyển quyền phải từ 0 đến 23"))
        errors += common_errors(data, (
            "source_contract_date", "registration_form_date", "transfer_effective_date",
        ))
        errors += person_errors(
            "customer", data.customer, {"id_number", "date_of_birth", "issue_date"}
        )
        errors += person_errors(
            "new_owner", data.new_owner, {"id_number", "date_of_birth", "issue_date"}
        )
        current_id = "".join(char for char in data.customer.id_number if char.isdigit())
        new_id = "".join(char for char in data.new_owner.id_number if char.isdigit())
        if current_id and new_id and current_id == new_id:
            errors.append(
                FieldError("new_owner.id_number", "Chủ thuê bao mới phải khác chủ thuê bao hiện tại")
            )
        current_name = unicodedata.normalize("NFD", data.customer.display_name().casefold())
        new_name = unicodedata.normalize("NFD", data.new_owner.display_name().casefold())
        current_name = "".join(c for c in current_name if c.isalnum() and unicodedata.category(c) != "Mn")
        new_name = "".join(c for c in new_name if c.isalnum() and unicodedata.category(c) != "Mn")
        if current_name and new_name and current_name == new_name:
            name_path = (
                "new_owner.organization_name"
                if data.new_owner.entity_type == "Tổ chức"
                else "new_owner.full_name"
            )
            errors.append(FieldError(name_path, "Tên chủ mới đang trùng với chủ hiện tại"))
        return errors
