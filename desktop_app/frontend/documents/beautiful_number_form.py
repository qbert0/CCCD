from .base import BaseDocumentForm

# (label, name, required, input_kind) -- shared with the web bridge's schema
# resolver, same pattern as PERSON_FIELDS. subscriber_number_1/_2,
# commitment_months_2, monthly_fee_2 and commitment_note_2 back the live
# web UI's repeating subscriber-number table (see resolve_document_form_layout()
# in web_bridge/schema.py) -- required is False here even for
# commitment_months_2/monthly_fee_2 since row 2 is opt-in; the real
# requirement only kicks in once it's used (BeautifulNumberSchema.required_paths).
FIELDS = [
    ("Số thuê bao", "subscriber_number_1", False, "text"),
    ("Thời gian cam kết", "commitment_months", True, "number"),
    ("Cước cam kết tối thiểu/tháng (nghìn đồng)", "monthly_fee", True, "number"),
    ("Ghi chú trong bảng sản phẩm", "commitment_note", False, "text"),
    ("Số thuê bao 2", "subscriber_number_2", False, "text"),
    ("Thời gian cam kết 2", "commitment_months_2", False, "number"),
    ("Cước cam kết tối thiểu/tháng 2 (nghìn đồng)", "monthly_fee_2", False, "number"),
    ("Ghi chú trong bảng sản phẩm 2", "commitment_note_2", False, "text"),
]


class BeautifulNumberForm(BaseDocumentForm):
    def __init__(self, parent=None):
        super().__init__(parent)
        for label_text, name, required, input_kind in FIELDS:
            self.add_field(label_text, name, required=required, input_kind=input_kind)
        self.fields["commitment_months"].set_value("12")

    def reset_values(self) -> None:
        super().reset_values()
        self.fields["commitment_months"].set_value("12")
