from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum


class DocumentType(str, Enum):
    TRANSFER = "transfer"
    AFTERSALE = "aftersale"
    BEAUTIFUL_NUMBER = "beautiful_number"
    PREPAID_CONTRACT = "prepaid_contract"


DOCUMENT_NAMES = {
    DocumentType.TRANSFER: (
        "Biên bản chuyển quyền sử dụng dịch vụ thông tin di động mặt đất "
        "và thanh lý hợp đồng"
    ),
    DocumentType.AFTERSALE: "Giấy cam kết – Dành cho các giao dịch sau bán hàng",
    DocumentType.BEAUTIFUL_NUMBER: "Phụ lục số 01 – Cam kết sử dụng sản phẩm số đẹp",
    DocumentType.PREPAID_CONTRACT: (
        "Hợp đồng cung cấp và sử dụng dịch vụ thông tin di động mặt đất "
        "Vietnamobile – Hình thức thanh toán trả trước"
    ),
}

DOCUMENT_SHORT_NAMES = {
    DocumentType.TRANSFER: "Chuyển quyền & thanh lý hợp đồng",
    DocumentType.AFTERSALE: "Cam kết giao dịch sau bán hàng",
    DocumentType.BEAUTIFUL_NUMBER: "Phụ lục cam kết số đẹp",
    DocumentType.PREPAID_CONTRACT: "Hợp đồng thuê bao trả trước",
}


@dataclass
class PersonData:
    entity_type: str = "Cá nhân"
    full_name: str = ""
    id_number: str = ""
    old_id_number: str = ""
    date_of_birth: str = ""
    gender: str = ""
    nationality: str = "Việt Nam"
    hometown: str = ""
    address: str = ""
    issue_date: str = ""
    issue_place: str = "Cục Cảnh sát QLHC về TTXH"
    expiry_date: str = ""
    phone: str = ""
    email: str = ""
    other_contact: str = ""
    foreign_country: str = ""
    organization_name: str = ""
    headquarters_address: str = ""
    business_registration_number: str = ""
    business_registration_issue_place: str = ""
    business_registration_issue_date: str = ""
    representative_name: str = ""
    representative_position: str = ""
    authorization_number: str = ""
    authorization_date: str = ""

    def display_name(self) -> str:
        return self.organization_name if self.entity_type == "Tổ chức" else self.full_name

    def merge(self, values: dict[str, str], overwrite: bool = True) -> None:
        aliases = {
            "fullname": "full_name",
            "name": "full_name",
            "cccd_number": "id_number",
            "id": "id_number",
            "cmnd_old": "old_id_number",
            "dob": "date_of_birth",
            "date_of_birth": "date_of_birth",
            "sex": "gender",
            "address": "address",
            "permanent_residence": "address",
        }
        valid_fields = set(asdict(self))
        for key, raw_value in values.items():
            target = aliases.get(key, key)
            value = str(raw_value or "").strip()
            if target in valid_fields and value and (overwrite or not getattr(self, target)):
                setattr(self, target, value)


@dataclass
class ReportData:
    document_type: DocumentType
    customer: PersonData = field(default_factory=PersonData)
    new_owner: PersonData = field(default_factory=PersonData)
    document_date: str = field(default_factory=lambda: date.today().strftime("%d/%m/%Y"))
    subscriber_number: str = ""
    sim_serial: str = ""
    activation_date: str = ""
    contract_number: str = ""
    shop_name: str = "Vietnamobile"
    shop_address: str = ""
    # Up to 3 ordered organization contact numbers -- filled once (persisted
    # across cases, same as staff_name) rather than retyped per document.
    # shop_phone is number 1; shop_phone_2/3 are optional extras.
    shop_phone: str = ""
    shop_phone_2: str = ""
    shop_phone_3: str = ""
    staff_name: str = ""
    backup_phone_1: str = ""
    backup_phone_2: str = ""
    commitment_months: str = "12 tháng"
    monthly_fee: str = ""
    service_action: str = "Cập nhật thông tin"
    payment_method: str = "Trả trước"
    source_contract_number: str = ""
    # Dates of pre-existing paperwork the shop must actually look up (the
    # original service contract / prepaid registration form) -- unlike
    # transfer_time/transfer_effective_date below (the moment THIS transfer
    # takes effect, which really is "now"), these should never silently
    # default to today.
    source_contract_date: str = ""
    registration_form_date: str = ""
    transfer_time: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))
    transfer_effective_date: str = field(default_factory=lambda: date.today().strftime("%d/%m/%Y"))
    has_id_attachment: bool = True
    has_original_sim: bool = False
    other_attachment: str = ""
    subscriber_code: str = ""
    service_point_name: str = ""
    provider_representative: str = ""
    provider_position: str = ""
    registration_time: str = ""
    commitment_note: str = ""
    notes: str = ""

    def validation_errors(self) -> list[str]:
        from desktop_app.backend.documents import DocumentRegistry

        return [error.message for error in DocumentRegistry().for_data(self).check(self)]

    def safe_stem(self) -> str:
        name = DOCUMENT_NAMES[self.document_type]
        normalized = unicodedata.normalize("NFD", name)
        ascii_name = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        ascii_name = ascii_name.replace("đ", "d").replace("Đ", "D")
        slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_")
        subscriber = re.sub(r"\D", "", self.subscriber_number) or "Chua_co_SDT"
        return f"{slug}_{subscriber}"

    def summary(self) -> str:
        customer_label = "Bên A" if self.document_type == DocumentType.TRANSFER else "Họ tên"
        rows = [
            ("Loại tài liệu", DOCUMENT_NAMES[self.document_type]),
            ("Ngày lập", self.document_date),
            (customer_label, self.customer.display_name()),
            ("CCCD/CMND", self.customer.id_number),
            ("Ngày sinh", self.customer.date_of_birth),
            ("Ngày/Nơi cấp", f"{self.customer.issue_date} - {self.customer.issue_place}"),
            ("Ngày hết hạn", self.customer.expiry_date),
            ("Địa chỉ", self.customer.address),
            ("Số thuê bao", self.subscriber_number),
            ("Số sê-ri SIM", self.sim_serial),
        ]
        needs_new_owner = self.document_type == DocumentType.TRANSFER or (
            self.document_type == DocumentType.AFTERSALE
            and self.service_action == "Chuyển chủ quyền"
        )
        if needs_new_owner:
            rows.extend(
                [
                    (
                        "Bên C · Chủ thuê bao mới"
                        if self.document_type == DocumentType.TRANSFER
                        else "Chủ mới",
                        self.new_owner.display_name(),
                    ),
                    ("CCCD chủ mới", self.new_owner.id_number),
                    ("Địa chỉ chủ mới", self.new_owner.address),
                ]
            )
        if self.document_type == DocumentType.BEAUTIFUL_NUMBER:
            rows.extend(
                [
                    ("Thời gian cam kết", self.commitment_months),
                    ("Cước tối thiểu/tháng", self.monthly_fee),
                ]
            )
        return "\n".join(f"{label}: {value or '(để trống)'}" for label, value in rows)
