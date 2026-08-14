from .base import BaseDocumentForm


class BeautifulNumberForm(BaseDocumentForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        months = self.add_field("Thời gian cam kết", "commitment_months", required=True)
        months.set_value("12 tháng")
        self.add_field("Cước cam kết tối thiểu/tháng", "monthly_fee", required=True)
        self.add_field("Ghi chú trong bảng sản phẩm", "commitment_note")

    def reset_values(self) -> None:
        super().reset_values()
        self.fields["commitment_months"].set_value("12 tháng")
