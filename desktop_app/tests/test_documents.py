import tempfile
import unittest
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from desktop_app.backend.documents import DocumentRegistry
from desktop_app.backend.domain.models import DocumentType, PersonData, ReportData


def _textbox_text(paragraph: Paragraph) -> list[str]:
    texts = []
    for txbx_content in paragraph._p.findall(".//" + qn("w:txbxContent")):
        for p_element in txbx_content.findall(qn("w:p")):
            texts.append(Paragraph(p_element, paragraph._parent).text)
    return texts


def docx_text(path: Path) -> str:
    document = Document(str(path))
    values = []
    for paragraph in document.paragraphs:
        values.append(paragraph.text)
        values.extend(_textbox_text(paragraph))
    for table in document.tables:
        for row in table.rows:
            values.extend(cell.text for cell in row.cells)
    return "\n".join(values)


class DocumentTest(unittest.TestCase):
    def setUp(self):
        self.customer = PersonData(
            full_name="NGUYỄN VĂN AN",
            id_number="001099999999",
            date_of_birth="01/01/1999",
            nationality="Việt Nam",
            address="123 Đường Láng, Đống Đa, Hà Nội",
            issue_date="01/01/2021",
            issue_place="Cục Cảnh sát QLHC về TTXH",
            phone="0901234567",
        )
        self.registry = DocumentRegistry()

    def report(self, doc_type: DocumentType) -> ReportData:
        return ReportData(
            document_type=doc_type,
            customer=self.customer,
            new_owner=PersonData(
                full_name="TRẦN THỊ B",
                id_number="001204001289",
                date_of_birth="01/02/2004",
                nationality="Việt Nam",
                address="Hoàn Kiếm, Hà Nội",
                issue_date="02/02/2022",
                issue_place="Cục Cảnh sát QLHC về TTXH",
            ),
            document_date="11/08/2026",
            subscriber_number="0925123456",
            sim_serial="8984041234567890123",
            activation_date="11/08/2026",
            source_contract_number="HĐ-2026-01",
            source_contract_date="10/08/2026",
            transfer_effective_date="11/08/2026",
            provider_representative="LÊ THỊ ĐẠI DIỆN",
            shop_name="Vietnamobile",
            shop_address="123 Xã Đàn, Hà Nội",
            shop_phone="02435730123",
            staff_name="Nguyễn Giao Dịch",
            backup_phone_1="0901234567",
            service_point_name="Điểm giao dịch Xã Đàn",
            registration_time="09:30 ngày 11/08/2026",
            commitment_months="12 tháng",
            monthly_fee="500.000 đồng",
        )

    def test_generates_beautiful_number_pdf_template(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.report(DocumentType.BEAUTIFUL_NUMBER)
            output = self.registry.for_data(data).generate(data, Path(folder))
            reader = PdfReader(str(output))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertEqual(len(reader.pages), 2)
            self.assertIn("0925123456", text)

    def test_prepaid_individual_does_not_fill_organization_section(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.report(DocumentType.PREPAID_CONTRACT)
            output = self.registry.for_data(data).generate(data, Path(folder))
            text = docx_text(output)
            self.assertEqual(text.count("001099999999"), 1)
            self.assertIn("NGUYỄN VĂN AN", text)
            self.assertIn("8984041234567890123", text)
            self.assertIn("Điểm giao dịch Xã Đàn", text)
            self.assertNotIn("{{", text)

    def test_generates_transfer_docx_with_customer(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.report(DocumentType.TRANSFER)
            output = self.registry.for_data(data).generate(data, Path(folder))
            text = docx_text(output)
            self.assertIn("NGUYỄN VĂN AN", text)
            self.assertIn("001099999999", text)
            self.assertIn("TRẦN THỊ B", text)
            self.assertIn("001204001289", text)
            self.assertIn("0925123456", text)
            self.assertIn("HĐ-2026-01 ngày 10 tháng 08 năm 2026", text)
            self.assertIn("Hôm nay, ngày 11 tháng 08 năm 2026", text)
            self.assertNotIn("{{", text)
            self.assertNotIn("{{pay_method}}", text)
            self.assertNotIn("Cty TNHH Viễn Thông Tiến Prô", text)
            self.assertNotIn("Trụ sở chính\nBa Đình, Bỉm Sơn", text)

    def test_transfer_and_prepaid_fill_signature_textbox(self):
        """The "Bên B" signature name used to be hardcoded inside a Word text
        box in both templates, so it never picked up provider_representative
        (renderer.py didn't walk into <w:txbxContent>). Confirm the fix: the
        signature line now reflects whatever was actually entered, and the
        old hardcoded name is gone."""
        for doc_type in (DocumentType.TRANSFER, DocumentType.PREPAID_CONTRACT):
            with tempfile.TemporaryDirectory() as folder:
                data = self.report(doc_type)
                output = self.registry.for_data(data).generate(data, Path(folder))
                text = docx_text(output)
                self.assertIn("LÊ THỊ ĐẠI DIỆN", text)
                self.assertNotIn("VÕ DUY NHẬT", text)

    def test_transfer_rejects_same_current_and_new_owner(self):
        data = self.report(DocumentType.TRANSFER)
        data.new_owner.id_number = data.customer.id_number
        errors = self.registry.for_data(data).check(data)
        self.assertTrue(any(error.path == "new_owner.id_number" for error in errors))

    def test_transfer_contract_number_requires_its_date(self):
        data = self.report(DocumentType.TRANSFER)
        data.source_contract_date = ""
        errors = self.registry.for_data(data).check(data)
        self.assertTrue(any(error.path == "source_contract_date" for error in errors))

    def test_generates_aftersale_with_reviewed_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.report(DocumentType.AFTERSALE)
            data.document_date = "11/08/2026"
            data.shop_address = "123 Xã Đàn, Hà Nội"
            data.shop_phone = "02435730123"
            output = self.registry.for_data(data).generate(data, Path(folder))
            text = docx_text(output)
            self.assertIn("Ngày 11 tháng 08 năm 2026", text)
            self.assertIn("Địa chỉ: 123 Xã Đàn, Hà Nội", text)
            self.assertIn("0925123456", text)
            self.assertNotIn("{{", text)
            self.assertNotIn("CÔNG TY TNHH VIỄN THÔNG TIẾN PRÔ", text)

    def test_aftersale_only_fills_the_selected_service(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.report(DocumentType.AFTERSALE)
            data.service_action = "Chuyển chủ quyền"
            output = self.registry.for_data(data).generate(data, Path(folder))
            text = docx_text(output)
            self.assertIn("☐✓ Chuyển chủ quyền", text)
            self.assertIn("☐ Cập nhật thông tin", text)
            self.assertIn("☐ Thay SIM", text)
            self.assertRegex(text, r"Vietnamobile: \.{20,}")
            self.assertIn("cho Ông/Bà TRẦN THỊ B", text)

            document = Document(output)
            # A checked box renders as two runs -- the same hollow "☐" box
            # glyph as an unchecked one, then an oversized "✓" pulled back
            # onto it -- rather than the single U+2611 glyph, whose filled
            # rendering varies badly by font/platform.
            check_runs = [
                run
                for paragraph in document.paragraphs
                for run in paragraph.runs
                if run.text == "✓"
            ]
            self.assertTrue(check_runs)
            self.assertTrue(all(run.font.size and run.font.size.pt == 20 for run in check_runs))
            self.assertTrue(all(run.bold for run in check_runs))
            signature_text = "\n".join(p.text for p in document.paragraphs[-6:])
            self.assertIn("NGƯỜI YÊU CẦU", signature_text)
            self.assertIn("CHỦ THUÊ BAO MỚI", signature_text)
            self.assertIn("GIAO DỊCH VIÊN", signature_text)
            final_columns = document._element.body.sectPr.xpath("./w:cols")[0]
            self.assertEqual(
                final_columns.get(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}num"
                ),
                "3",
            )

    def test_prepaid_organization_fills_only_organization_section(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.report(DocumentType.PREPAID_CONTRACT)
            data.customer = PersonData(
                entity_type="Tổ chức",
                organization_name="CÔNG TY TNHH VIỄN THÔNG MẪU",
                headquarters_address="10 Xã Đàn, Hà Nội",
                business_registration_number="0101234567",
                business_registration_issue_place="Sở Tài chính Hà Nội",
                business_registration_issue_date="01/01/2020",
                representative_name="NGUYỄN ĐẠI DIỆN",
                representative_position="Giám đốc",
                id_number="001090001234",
                date_of_birth="01/01/1990",
                issue_date="01/01/2022",
                issue_place="Cục Cảnh sát QLHC về TTXH",
                phone="0901234567",
            )
            output = self.registry.for_data(data).generate(data, Path(folder))
            text = docx_text(output)
            self.assertIn("CÔNG TY TNHH VIỄN THÔNG MẪU", text)
            self.assertIn("NGUYỄN ĐẠI DIỆN", text)
            self.assertEqual(text.count("001090001234"), 1)
            self.assertNotIn("NGUYỄN VĂN AN", text)
            self.assertNotIn("{{", text)

    def test_prepaid_foreign_person_prints_passport_country(self):
        with tempfile.TemporaryDirectory() as folder:
            data = self.report(DocumentType.PREPAID_CONTRACT)
            data.customer.nationality = "Nhật Bản"
            data.customer.foreign_country = "Nhật Bản"
            output = self.registry.for_data(data).generate(data, Path(folder))
            text = docx_text(output)
            self.assertIn("☐ Việt Nam    ☐✓ Nước ngoài: Nhật Bản", text)

    def test_placeholder_split_across_word_runs_keeps_other_run_styles(self):
        from desktop_app.backend.documents.renderer import _replace_placeholders

        document = Document()
        paragraph = document.add_paragraph()
        paragraph.add_run("Họ tên: ").bold = True
        first = paragraph.add_run("{{ customer_")
        first.italic = True
        last = paragraph.add_run("name }} / giữ nguyên")
        last.underline = True

        _replace_placeholders(paragraph, {"customer_name": "NGUYỄN VĂN AN"})

        self.assertEqual(paragraph.text, "Họ tên: NGUYỄN VĂN AN / giữ nguyên")
        self.assertTrue(paragraph.runs[0].bold)
        self.assertTrue(paragraph.runs[1].italic)


if __name__ == "__main__":
    unittest.main()
