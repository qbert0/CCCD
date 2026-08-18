from .base import BaseDocumentForm

# (label, name, required, input_kind) -- shared with the web bridge's schema
# resolver, same pattern as PERSON_FIELDS. Order matters for packing: the 4
# SHORT fields fill row 1 (3) + the start of row 2 (1), then
# service_point_name (MEDIUM, 2 cols) exactly fills the rest of row 2 -- 2
# rows total instead of 3.
FIELDS = [
    ("Số sê-ri SIM", "sim_serial", True, "number"),
    ("Ngày hòa mạng", "activation_date", True, "date"),
    ("Thời gian đăng ký thông tin thuê bao", "registration_time", True, "text"),
    ("Người đại diện bên cung cấp", "provider_representative", False, "text"),
    ("Điểm cung cấp dịch vụ viễn thông", "service_point_name", True, "text"),
    ("Số hợp đồng", "contract_number", False, "number"),
    ("Mã thuê bao", "subscriber_code", False, "number"),
    ("Chức vụ người đại diện", "provider_position", False, "text"),
]


class PrepaidContractForm(BaseDocumentForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        for label_text, name, required, input_kind in FIELDS:
            self.add_field(label_text, name, required=required, input_kind=input_kind)
