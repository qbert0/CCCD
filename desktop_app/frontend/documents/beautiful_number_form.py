from .base import BaseDocumentForm

# (label, name, required, input_kind) -- shared with the web bridge's schema
# resolver, same pattern as PERSON_FIELDS.
FIELDS = [
    ("Thời gian cam kết", "commitment_months", True, "text"),
    ("Cước cam kết tối thiểu/tháng", "monthly_fee", True, "text"),
    ("Ghi chú trong bảng sản phẩm", "commitment_note", False, "text"),
]


class BeautifulNumberForm(BaseDocumentForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        for label_text, name, required, input_kind in FIELDS:
            self.add_field(label_text, name, required=required, input_kind=input_kind)
        self.fields["commitment_months"].set_value("12 tháng")

    def reset_values(self) -> None:
        super().reset_values()
        self.fields["commitment_months"].set_value("12 tháng")
