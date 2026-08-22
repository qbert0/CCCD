from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from desktop_app.backend.domain.models import PersonData, ReportData


@dataclass(frozen=True)
class FieldError:
    path: str
    message: str


LABELS = {
    "customer.full_name": "Họ và tên",
    "customer.organization_name": "Tên cơ quan/tổ chức",
    "customer.headquarters_address": "Địa chỉ trụ sở chính",
    "customer.business_registration_number": "Số đăng ký doanh nghiệp",
    "customer.business_registration_issue_place": "Nơi cấp giấy đăng ký doanh nghiệp",
    "customer.business_registration_issue_date": "Ngày cấp giấy đăng ký doanh nghiệp",
    "customer.representative_name": "Họ tên người đại diện",
    "customer.representative_position": "Chức vụ người đại diện",
    "customer.id_number": "Số CCCD/CMND",
    "customer.issue_date": "Ngày cấp",
    "customer.issue_place": "Nơi cấp",
    "customer.date_of_birth": "Ngày sinh",
    "customer.address": "Địa chỉ theo giấy tờ",
    "customer.nationality": "Quốc tịch",
    "customer.phone": "Điện thoại liên hệ",
    "new_owner.full_name": "Họ tên chủ thuê bao mới",
    "new_owner.organization_name": "Tên tổ chức chủ mới",
    "new_owner.headquarters_address": "Trụ sở chủ mới",
    "new_owner.business_registration_number": "Đăng ký doanh nghiệp chủ mới",
    "new_owner.representative_name": "Người đại diện chủ mới",
    "new_owner.id_number": "CCCD/CMND chủ mới",
    "new_owner.issue_date": "Ngày cấp của chủ mới",
    "new_owner.issue_place": "Nơi cấp của chủ mới",
    "new_owner.date_of_birth": "Ngày sinh của chủ mới",
    "new_owner.address": "Địa chỉ chủ mới",
    "new_owner.nationality": "Quốc tịch của chủ mới",
    "new_owner.phone": "Điện thoại khách hàng",
    "representative.full_name": "Họ tên người đại diện",
    "representative.id_number": "CCCD/CMND người đại diện",
    "representative.issue_date": "Ngày cấp của người đại diện",
    "representative.issue_place": "Nơi cấp của người đại diện",
    "representative.date_of_birth": "Ngày sinh của người đại diện",
    "representative.address": "Địa chỉ người đại diện",
    "representative.nationality": "Quốc tịch người đại diện",
    "representative.representative_position": "Chức vụ người đại diện",
    "representative.phone": "Điện thoại người đại diện",
    "document_date": "Ngày lập tài liệu",
    "subscriber_number": "Số thuê bao",
    "shop_name": "Tên cửa hàng",
    "shop_address": "Địa chỉ cửa hàng/điểm giao dịch",
    "shop_phone": "Điện thoại cửa hàng/điểm giao dịch",
    "staff_name": "Nhân viên giao dịch",
    "commitment_months": "Thời gian cam kết",
    "monthly_fee": "Cước cam kết tối thiểu",
    "backup_phone_1": "Số điện thoại phối hợp giải quyết",
    "sim_serial": "Số sê-ri SIM",
    "activation_date": "Ngày hòa mạng",
    "service_point_name": "Điểm cung cấp dịch vụ viễn thông",
    "registration_time": "Thời gian đăng ký thông tin thuê bao",
    "provider_unit_address": "Địa chỉ đơn vị cung cấp",
    "provider_representative": "Người đại diện bên cung cấp",
    "service_point_address": "Địa điểm giao dịch",
    "service_point_phone": "Số điện thoại điểm giao dịch",
    "payment_method": "Hình thức thanh toán",
    "transfer_effective_date": "Ngày chuyển quyền có hiệu lực",
}


def value_at(data: ReportData, path: str):
    target = data
    for part in path.split("."):
        target = getattr(target, part, "")
    return target


def required_errors(data: ReportData, paths: list[str]) -> list[FieldError]:
    return [
        FieldError(path, f"{LABELS.get(path, path)} là thông tin bắt buộc")
        for path in paths
        if not str(value_at(data, path) or "").strip()
    ]


def party_required(prefix: str, person: PersonData) -> list[str]:
    if person.entity_type == "Tổ chức":
        return [
            f"{prefix}.organization_name",
            f"{prefix}.headquarters_address",
            f"{prefix}.business_registration_number",
            f"{prefix}.representative_name",
            f"{prefix}.id_number",
            f"{prefix}.issue_date",
            f"{prefix}.issue_place",
        ]
    return [
        f"{prefix}.full_name",
        f"{prefix}.id_number",
        f"{prefix}.issue_date",
        f"{prefix}.issue_place",
        f"{prefix}.date_of_birth",
        f"{prefix}.address",
        f"{prefix}.nationality",
    ]


def organization_information_required(prefix: str) -> list[str]:
    """Required fields in the reusable company/organization form."""
    return [
        f"{prefix}.organization_name",
        f"{prefix}.business_registration_number",
        f"{prefix}.business_registration_issue_date",
        f"{prefix}.business_registration_issue_place",
        f"{prefix}.headquarters_address",
    ]


def personal_information_required(prefix: str) -> list[str]:
    """Required fields in the reusable CCCD-backed personal form."""
    return [
        f"{prefix}.full_name",
        f"{prefix}.id_number",
        f"{prefix}.issue_date",
        f"{prefix}.issue_place",
        f"{prefix}.date_of_birth",
        f"{prefix}.nationality",
        f"{prefix}.address",
    ]


def valid_date(value: str) -> bool:
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value.strip()):
        return False
    try:
        datetime.strptime(value.strip(), "%d/%m/%Y")
    except ValueError:
        return False
    return True


def parse_date(value: str) -> date | None:
    return datetime.strptime(value, "%d/%m/%Y").date() if value and valid_date(value) else None


def valid_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return bool(re.fullmatch(r"[+\d().\s-]+", value) and 9 <= len(digits) <= 12)


def duplicate_subscriber_errors(
    rows: list[dict[str, str]],
    path_prefix: str,
) -> list[FieldError]:
    """Mark every occurrence of a duplicated subscriber number.

    Comparison uses digits only so harmless display punctuation cannot hide
    a duplicate (for example ``0925 123 456`` and ``0925123456``).
    Empty rows remain available for data entry and are never duplicates.
    """
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        value = str(row.get("subscriber_number", "") or "").strip()
        canonical = re.sub(r"\D", "", value)
        if 9 <= len(canonical) <= 12:
            groups.setdefault(canonical, []).append(index)

    errors: list[FieldError] = []
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        row_numbers = ", ".join(str(index + 1) for index in indexes)
        message = f"Số thuê bao bị trùng ở các dòng {row_numbers}"
        errors.extend(
            FieldError(f"{path_prefix}.{index}.subscriber_number", message)
            for index in indexes
        )
    return errors


def common_errors(
    data: ReportData,
    date_paths: tuple[str, ...] = (),
    phone_paths: tuple[str, ...] = ("subscriber_number",),
) -> list[FieldError]:
    errors: list[FieldError] = []
    for path in phone_paths:
        value = str(value_at(data, path) or "").strip()
        if value and not valid_phone(value):
            errors.append(FieldError(path, "Số điện thoại phải gồm từ 9 đến 12 chữ số"))
    for path in ("document_date", *date_paths):
        value = str(value_at(data, path) or "").strip()
        if value and not valid_date(value):
            errors.append(FieldError(path, "Ngày không hợp lệ. Hãy nhập đúng DD/MM/YYYY."))
    return errors


def subscriber_list_errors(data: ReportData) -> list[FieldError]:
    """Shared by Transfer/Aftersale: at least one number must be available
    (scalar `subscriber_number` OR a non-empty row in `data.subscribers` --
    see ReportData.has_subscriber_number()), and every row that's actually
    filled in must be phone-format-valid. Mirrors the per-row validation
    BeautifulNumberSchema already does over its own `beautiful_subscribers`
    list."""
    errors: list[FieldError] = []
    if not data.has_subscriber_number():
        errors.append(FieldError("subscriber_number", "Số thuê bao là thông tin bắt buộc"))
    for index, row in enumerate(data.subscribers):
        value = str(row.get("subscriber_number", "") or "").strip()
        if value and not valid_phone(value):
            errors.append(
                FieldError(f"subscribers.{index}.subscriber_number", "Số điện thoại phải gồm từ 9 đến 12 chữ số")
            )
    errors += duplicate_subscriber_errors(data.subscribers, "subscribers")
    return errors


def person_errors(
    prefix: str,
    person: PersonData,
    active_fields: set[str] | None = None,
) -> list[FieldError]:
    active = active_fields or {
        "id_number", "date_of_birth", "issue_date", "expiry_date",
        "authorization_date", "phone", "email",
    }
    errors: list[FieldError] = []
    if "id_number" in active and person.id_number and not re.fullmatch(r"\d{9}|\d{12}", person.id_number.strip()):
        errors.append(FieldError(f"{prefix}.id_number", "CCCD/CMND phải gồm đúng 9 hoặc 12 chữ số"))
    for name in ("date_of_birth", "issue_date", "expiry_date", "authorization_date"):
        value = getattr(person, name)
        if name in active and value and not valid_date(value):
            errors.append(FieldError(f"{prefix}.{name}", "Ngày phải đúng định dạng DD/MM/YYYY"))
    if "phone" in active and person.phone and not valid_phone(person.phone):
        errors.append(FieldError(f"{prefix}.phone", "Số điện thoại phải gồm từ 9 đến 12 chữ số"))
    if "email" in active and person.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", person.email):
        errors.append(FieldError(f"{prefix}.email", "Email không đúng định dạng"))
    birth, issue, expiry = map(
        parse_date, (person.date_of_birth, person.issue_date, person.expiry_date)
    )
    if "date_of_birth" in active and birth and birth > date.today():
        errors.append(FieldError(f"{prefix}.date_of_birth", "Ngày sinh không thể ở tương lai"))
    if {"date_of_birth", "issue_date"}.issubset(active) and birth and issue and issue < birth:
        errors.append(FieldError(f"{prefix}.issue_date", "Ngày cấp không thể trước ngày sinh"))
    if "issue_date" in active and issue and issue > date.today():
        errors.append(FieldError(f"{prefix}.issue_date", "Ngày cấp không thể ở tương lai"))
    if {"issue_date", "expiry_date"}.issubset(active) and issue and expiry and expiry <= issue:
        errors.append(FieldError(f"{prefix}.expiry_date", "Ngày hết hạn phải sau ngày cấp"))
    return errors
