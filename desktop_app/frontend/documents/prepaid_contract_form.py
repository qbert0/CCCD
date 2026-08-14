from .base import BaseDocumentForm


class PrepaidContractForm(BaseDocumentForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Order matters for packing: the 4 SHORT fields fill row 1 (3) + the
        # start of row 2 (1), then service_point_name (MEDIUM, 2 cols)
        # exactly fills the rest of row 2 -- 2 rows total instead of 3.
        self.add_field("Số sê-ri SIM", "sim_serial", required=True, input_kind="number")
        self.add_field("Ngày hòa mạng", "activation_date", required=True, input_kind="date")
        self.add_field("Thời gian đăng ký thông tin thuê bao", "registration_time", required=True)
        self.add_field("Người đại diện bên cung cấp", "provider_representative")
        self.add_field("Điểm cung cấp dịch vụ viễn thông", "service_point_name", required=True)
        self.add_field("Số hợp đồng", "contract_number", input_kind="number")
        self.add_field("Mã thuê bao", "subscriber_code", input_kind="number")
        self.add_field("Chức vụ người đại diện", "provider_position")
