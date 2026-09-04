import unittest

from desktop_app.backend.domain.models import DocumentType, PersonData, ReportData
from desktop_app.backend.documents import DocumentRegistry
from desktop_app.backend.ocr.parser import parse_ocr_text, parse_qr
from desktop_app.backend.validation.rules import valid_date


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.registry = DocumentRegistry()

    def test_parse_standard_cccd_qr(self):
        raw = "001099999999|099999999|NGUYỄN VĂN A|01011999|Nam|Số 1 Đường ABC, Hà Nội|01012021"
        result = parse_qr(raw)
        self.assertEqual(result["id_number"], "001099999999")
        self.assertEqual(result["full_name"], "NGUYỄN VĂN A")
        self.assertEqual(result["date_of_birth"], "01/01/1999")
        self.assertEqual(result["issue_date"], "01/01/2021")

    def test_transfer_time_no_longer_defaults_to_current_hour(self):
        # Per direct instruction: the clerk types this by hand every time,
        # never silently pre-filled with whatever hour the case happened
        # to be opened at (transfer_effective_date is unaffected -- still
        # defaults to today).
        self.assertEqual(ReportData(document_type=DocumentType.TRANSFER).transfer_time, "")

    def test_transfer_requires_new_owner(self):
        data = ReportData(
            document_type=DocumentType.TRANSFER,
            customer=PersonData(full_name="A", id_number="001099999999"),
            subscriber_number="0925000000",
        )
        self.assertTrue(any("chủ" in error.casefold() for error in data.validation_errors()))

    def test_transfer_organization_subscriber_requires_only_three_extra_company_fields(self):
        person = PersonData(
            entity_type="Tổ chức",
            full_name="Nguyễn Văn A",
            id_number="001099999999",
            issue_date="01/01/2021",
            issue_place="Cục Cảnh sát QLHC về TTXH",
            date_of_birth="01/01/1990",
            nationality="Việt Nam",
            address="Hà Nội",
        )
        data = ReportData(document_type=DocumentType.TRANSFER, new_owner=person)
        paths = {error.path for error in self.registry.for_data(data).check(data)}
        self.assertIn("new_owner.organization_name", paths)
        self.assertIn("new_owner.headquarters_address", paths)
        self.assertIn("new_owner.business_registration_number", paths)
        self.assertNotIn("new_owner.business_registration_issue_date", paths)
        self.assertNotIn("new_owner.business_registration_issue_place", paths)

    def test_aftersale_transfer_requires_new_owner(self):
        data = ReportData(
            document_type=DocumentType.AFTERSALE,
            customer=PersonData(full_name="A", id_number="001099999999"),
            subscriber_number="0925000000",
            service_action="Chuyển chủ quyền",
        )
        self.assertTrue(any("chủ" in error.casefold() for error in data.validation_errors()))

    def test_parse_back_side_mrz(self):
        raw = (
            "NGUYEN<<VAN<A<<<<<<<<<<<<<<<<\n"
            "9901019M3601014VNM<<<<<<<<<<<2\n"
            "IDVNM099999999001099999999<<<2\n"
            "Ngay,thang,nam/Date,month,year01/01/2021"
        )
        result = parse_ocr_text(raw)
        self.assertEqual(result["id_number"], "001099999999")
        self.assertEqual(result["full_name"], "Nguyen Van A")
        self.assertEqual(result["date_of_birth"], "01/01/1999")
        self.assertEqual(result["gender"], "Nam")
        self.assertEqual(result["expiry_date"], "01/01/2036")

    def test_schema_returns_field_paths(self):
        data = ReportData(document_type=DocumentType.PREPAID_CONTRACT)
        paths = {error.path for error in self.registry.for_data(data).check(data)}
        self.assertIn("customer.full_name", paths)
        self.assertIn("customer.id_number", paths)
        self.assertIn("subscriber_number", paths)

    def test_schema_rejects_invalid_dates_and_phone(self):
        data = ReportData(
            document_type=DocumentType.PREPAID_CONTRACT,
            customer=PersonData(
                full_name="Nguyễn Văn A",
                id_number="001099999999",
                date_of_birth="31/02/2000",
                phone="123",
            ),
            document_date="2026-08-12",
            subscriber_number="0925",
        )
        paths = {error.path for error in self.registry.for_data(data).check(data)}
        self.assertIn("document_date", paths)
        self.assertIn("customer.date_of_birth", paths)
        self.assertIn("customer.phone", paths)
        self.assertIn("subscriber_number", paths)

    def test_date_validation_rejects_extra_digits_and_impossible_dates(self):
        for value in ("12/12/199611", "111/12/1996", "31/02/2026", "29/02/2025"):
            with self.subTest(value=value):
                self.assertFalse(valid_date(value))
        self.assertTrue(valid_date("29/02/2024"))

    def test_schema_rejects_relevant_date_order_and_ignores_hidden_expiry(self):
        data = ReportData(
            document_type=DocumentType.PREPAID_CONTRACT,
            customer=PersonData(
                full_name="Nguyễn Văn A",
                id_number="001099999999",
                date_of_birth="01/01/2000",
                issue_date="01/01/1999",
                expiry_date="01/01/1998",
            ),
            subscriber_number="0925123456",
        )
        paths = {error.path for error in self.registry.for_data(data).check(data)}
        self.assertIn("customer.issue_date", paths)
        self.assertNotIn("customer.expiry_date", paths)

    def test_prepaid_organization_has_its_own_required_fields(self):
        data = ReportData(
            document_type=DocumentType.PREPAID_CONTRACT,
            customer=PersonData(
                entity_type="Tổ chức",
                organization_name="Công ty A",
                headquarters_address="Hà Nội",
                business_registration_number="0101234567",
                representative_name="Nguyễn Văn A",
                id_number="001099999999",
                issue_date="01/01/2021",
                issue_place="Cục Cảnh sát QLHC về TTXH",
                date_of_birth="01/01/1980",
                phone="0901234567",
            ),
        )
        paths = {error.path for error in self.registry.for_data(data).check(data)}
        self.assertIn("customer.business_registration_issue_place", paths)
        self.assertIn("customer.business_registration_issue_date", paths)
        self.assertIn("customer.representative_position", paths)
        self.assertNotIn("customer.full_name", paths)


if __name__ == "__main__":
    unittest.main()
