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
    # Company Profile's own 2nd contact number ("SĐT liên hệ 2") -- only
    # meaningful when this PersonData is the company profile or the
    # representative session record, not a real CCCD/customer field.
    phone_2: str = ""
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
    # Prepaid Contract has three distinct parties on screen.  Keep the
    # representative separate from both the saved company (customer) and
    # the CCCD-scanned end customer (new_owner), so editing one tab can
    # never accidentally overwrite another.
    representative: PersonData = field(default_factory=PersonData)
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
    # Aftersale's "Thông tin tài liệu" tab identity block -- by explicit
    # request, sourced entirely from the company profile (business
    # registration number/issue date/place), not the actual customer.
    # Auto-filled from company_profile at boot/new-case time, same pattern
    # as shop_name/shop_address, and stays editable per-document.
    shop_id_number: str = ""
    shop_issue_date: str = ""
    shop_issue_place: str = ""
    staff_name: str = ""
    backup_phone_1: str = ""
    backup_phone_2: str = ""
    commitment_months: str = "12"
    monthly_fee: str = ""
    # Beautiful Number's own repeating subscriber-number table. Row 1's
    # number is a field of its own (subscriber_number_1) rather than plain
    # subscriber_number, because it's one-directionally synced FROM the
    # scan-column subscriber_number (typing there updates row 1) without the
    # reverse ever happening (editing row 1 must never touch the scan
    # column) -- see the "_2" fields below for the optional 2nd row, added
    # via the "+ Thêm số thuê bao khác" control.
    subscriber_number_1: str = ""
    subscriber_number_2: str = ""
    commitment_months_2: str = ""
    monthly_fee_2: str = ""
    commitment_note_2: str = ""
    # Unlimited-entry web editor for the Beautiful Number appendix.  The
    # first entry is printed in the original table; remaining entries are
    # paginated onto continuation sheets by the PDF renderer.  The legacy
    # fixed row-1/row-2 fields above remain for old saved data/QWidget code.
    beautiful_subscribers: list[dict[str, str]] = field(default_factory=list)
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
    transfer_time: str = field(default_factory=lambda: datetime.now().strftime("%H"))
    transfer_effective_date: str = field(default_factory=lambda: date.today().strftime("%d/%m/%Y"))
    has_id_attachment: bool = True
    has_original_sim: bool = False
    other_attachment: str = ""
    subscriber_code: str = ""
    service_point_name: str = ""
    provider_representative: str = ""
    provider_position: str = ""
    # The representative's own contact details -- Prepaid Contract only,
    # auto-filled from the representative session (the only record that
    # actually carries a phone/email for this person; company_profile's own
    # phone/phone_2 are the SHOP's numbers, not the representative's own).
    # The template's identity block has no printed slot left for these
    # (every line is already accounted for), so they're captured for the
    # shop's own reference rather than printed.
    provider_phone: str = ""
    provider_email: str = ""
    provider_unit_address: str = ""
    service_point_address: str = ""
    service_point_phone: str = ""
    registration_time: str = ""
    # The printed prepaid template has five real data rows.  A list keeps
    # the UI extensible while the renderer caps output at that capacity.
    prepaid_subscribers: list[dict[str, str]] = field(default_factory=list)
    # Old callers used customer as either an organization OR an individual.
    # The desktop UI opts into the new company/representative/customer model
    # while legacy API/tests remain renderable.
    prepaid_structured_parties: bool = False
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
        rows = [
            ("Loại tài liệu", DOCUMENT_NAMES[self.document_type]),
            ("Ngày lập", self.document_date),
        ]
        if self.document_type == DocumentType.AFTERSALE and self.customer.entity_type == "Tổ chức":
            rows.extend([
                ("Tổ chức", self.customer.organization_name),
                ("Số ĐKKD", self.customer.business_registration_number),
                ("Địa chỉ tổ chức", self.customer.headquarters_address),
                ("Khách hàng", self.new_owner.full_name),
                ("CCCD/CMND", self.new_owner.id_number),
                ("Ngày/Nơi cấp", f"{self.new_owner.issue_date} - {self.new_owner.issue_place}"),
            ])
        elif self.document_type == DocumentType.PREPAID_CONTRACT and self.prepaid_structured_parties:
            rows.extend([
                ("Công ty", self.customer.organization_name),
                ("Người đại diện", self.representative.full_name),
                ("Chức vụ", self.representative.representative_position),
                ("Khách hàng", self.new_owner.full_name),
                ("CCCD/CMND", self.new_owner.id_number),
                ("Điểm cung cấp", self.service_point_name),
            ])
        else:
            customer_label = "Bên A" if self.document_type == DocumentType.TRANSFER else "Họ tên"
            rows.extend([
                (customer_label, self.customer.display_name()),
                ("CCCD/CMND", self.customer.id_number),
                ("Ngày sinh", self.customer.date_of_birth),
                ("Ngày/Nơi cấp", f"{self.customer.issue_date} - {self.customer.issue_place}"),
                ("Ngày hết hạn", self.customer.expiry_date),
                ("Địa chỉ", self.customer.address),
            ])
        rows.extend([
            ("Số thuê bao", self.subscriber_number),
            ("Số sê-ri SIM", self.sim_serial),
        ])
        if self.document_type == DocumentType.PREPAID_CONTRACT and self.prepaid_subscribers:
            rows.extend(
                (f"SIM {index + 1}", " · ".join(filter(None, (
                    str(item.get("subscriber_number", "")),
                    str(item.get("sim_serial", "")),
                    str(item.get("activation_date", "")),
                ))))
                for index, item in enumerate(self.prepaid_subscribers[:5])
            )
        needs_new_owner = self.document_type == DocumentType.TRANSFER or (
            self.document_type == DocumentType.AFTERSALE
            and self.customer.entity_type != "Tổ chức"
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
            if self.beautiful_subscribers:
                rows.extend(
                    (f"Số thuê bao {index + 1}", " · ".join(filter(None, (
                        str(item.get("subscriber_number", "")),
                        str(item.get("commitment_months", "")),
                        str(item.get("monthly_fee", "")),
                    ))))
                    for index, item in enumerate(self.beautiful_subscribers)
                )
                return "\n".join(f"{label}: {value or '(để trống)'}" for label, value in rows)
            rows.extend(
                [
                    ("Số thuê bao 1", self.subscriber_number_1 or self.subscriber_number),
                    ("Thời gian cam kết 1 (tháng)", self.commitment_months),
                    ("Cước tối thiểu/tháng 1", self.monthly_fee),
                ]
            )
            if self.subscriber_number_2 or self.commitment_months_2 or self.monthly_fee_2 or self.commitment_note_2:
                rows.extend(
                    [
                        ("Số thuê bao 2", self.subscriber_number_2),
                        ("Thời gian cam kết 2 (tháng)", self.commitment_months_2),
                        ("Cước tối thiểu/tháng 2", self.monthly_fee_2),
                    ]
                )
        return "\n".join(f"{label}: {value or '(để trống)'}" for label, value in rows)
