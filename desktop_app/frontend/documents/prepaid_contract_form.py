from .base import BaseDocumentForm

# (label, name, required, input_kind) -- shared with the web bridge's schema
# resolver, same pattern as PERSON_FIELDS. Order matters for packing: the 4
# SHORT fields fill row 1 (3) + the start of row 2 (1), then
# service_point_name (MEDIUM, 2 cols) exactly fills the rest of row 2 -- 2
# rows total instead of 3.
FIELDS = [
    # Retained for the legacy QWidget form.  The web UI edits these values in
    # its dedicated repeating five-row SIM tab instead.
    ("Số sê-ri SIM", "sim_serial", True, "number"),
    ("Ngày hòa mạng", "activation_date", True, "date"),
    ("Địa chỉ đơn vị cung cấp", "provider_unit_address", True, "text"),
    ("Người đại diện", "provider_representative", True, "text"),
    ("Điểm cung cấp dịch vụ viễn thông", "service_point_name", False, "text"),
    ("Nhân viên giao dịch", "staff_name", True, "text"),
    ("Địa điểm giao dịch", "service_point_address", True, "text"),
    ("Số điện thoại", "service_point_phone", True, "number"),
    ("Thời gian thực hiện", "registration_time", False, "text"),
]


class PrepaidContractForm(BaseDocumentForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        for label_text, name, required, input_kind in FIELDS:
            self.add_field(label_text, name, required=required, input_kind=input_kind)
