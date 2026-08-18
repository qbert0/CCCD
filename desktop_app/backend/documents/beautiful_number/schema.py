import re

from desktop_app.backend.domain.models import ReportData
from desktop_app.backend.validation.rules import (
    FieldError, common_errors, person_errors, required_errors, valid_phone,
)


class BeautifulNumberSchema:
    @staticmethod
    def _valid_monthly_fee(value: str) -> bool:
        text = str(value or "").strip()
        if re.fullmatch(r"\d+", text):
            return int(text) > 0
        # Backward compatibility for drafts saved before the UI switched to
        # the thousand-VND numeric field.
        legacy = re.sub(r"\s*(?:đồng|đ)\s*$", "", text, flags=re.IGNORECASE)
        if not re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", legacy):
            return False
        return int(re.sub(r"[.,]", "", legacy)) > 0

    @staticmethod
    def required_paths(data: ReportData) -> list[str]:
        paths = [
            "document_date", "subscriber_number", "customer.full_name", "customer.id_number",
        ]
        if data.beautiful_subscribers:
            return paths
        paths += ["commitment_months", "monthly_fee"]
        # Row 2 is opt-in (its own "+ Thêm số thuê bao khác" control) -- only
        # require its own fields once the user has actually started filling
        # it in, same dynamic-requirement pattern as Transfer's
        # source_contract_number -> source_contract_date.
        if data.subscriber_number_2 or data.commitment_months_2 or data.monthly_fee_2 or data.commitment_note_2:
            paths += ["subscriber_number_2", "commitment_months_2", "monthly_fee_2"]
        return paths

    @classmethod
    def validate(cls, data: ReportData) -> list[FieldError]:
        errors = (
            required_errors(data, cls.required_paths(data))
            + common_errors(data)
            + person_errors("customer", data.customer, {"id_number"})
        )
        if data.beautiful_subscribers:
            for index, row in enumerate(data.beautiful_subscribers):
                for name, label in (
                    ("subscriber_number", "Số thuê bao"),
                    ("commitment_months", "Thời gian cam kết"),
                    ("monthly_fee", "Cước cam kết tối thiểu/tháng"),
                ):
                    value = str(row.get(name, "") or "").strip()
                    path = f"beautiful_subscribers.{index}.{name}"
                    if not value:
                        errors.append(FieldError(path, f"{label} là thông tin bắt buộc"))
                    elif name == "subscriber_number" and not valid_phone(value):
                        errors.append(FieldError(path, "Số điện thoại phải gồm từ 9 đến 12 chữ số"))
                months = str(row.get("commitment_months", "") or "").strip()
                match = re.fullmatch(r"(\d+)\s*(?:tháng)?", months, flags=re.IGNORECASE)
                if months and (not match or int(match.group(1)) <= 0):
                    errors.append(FieldError(
                        f"beautiful_subscribers.{index}.commitment_months",
                        "Số tháng phải là một số nguyên lớn hơn 0",
                    ))
                fee = str(row.get("monthly_fee", "") or "").strip()
                if fee and not cls._valid_monthly_fee(fee):
                    errors.append(FieldError(
                        f"beautiful_subscribers.{index}.monthly_fee",
                        "Mức cước phải là số nguyên lớn hơn 0 (đơn vị nghìn đồng)",
                    ))
            return errors
        for path in ("commitment_months", "commitment_months_2"):
            value = str(getattr(data, path) or "").strip()
            match = re.fullmatch(r"(\d+)\s*(?:tháng)?", value, flags=re.IGNORECASE)
            if value and (not match or int(match.group(1)) <= 0):
                errors.append(FieldError(path, "Số tháng phải là một số nguyên lớn hơn 0"))
        for path in ("monthly_fee", "monthly_fee_2"):
            value = str(getattr(data, path) or "").strip()
            if value and not cls._valid_monthly_fee(value):
                errors.append(FieldError(
                    path, "Mức cước phải là số nguyên lớn hơn 0 (đơn vị nghìn đồng)"
                ))
        return errors
