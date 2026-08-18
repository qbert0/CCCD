import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from desktop_app.backend.domain.models import DocumentType
from desktop_app.backend.ocr import CardSide, OCRFileResult, combine_file_results
from desktop_app.frontend.pages import HomePage


class FrontendValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = HomePage()

    def tearDown(self):
        self.window.close()

    def test_required_error_is_rendered_below_input(self):
        index = self.window.document_combo.findData(DocumentType.TRANSFER.value)
        self.window.document_combo.setCurrentIndex(index)
        self.assertIsNone(self.window._validated_data())
        field = self.window.new_owner_tab.form.fields["full_name"]
        self.assertFalse(field.error.isHidden())
        self.assertIn("bắt buộc", field.error.text())

    def test_transfer_uses_local_party_a_and_only_one_upload_card(self):
        index = self.window.document_combo.findData(DocumentType.TRANSFER.value)
        self.window.document_combo.setCurrentIndex(index)

        party_a = self.window.customer_tab.form.data()
        self.assertEqual(party_a.entity_type, "Tổ chức")
        self.assertEqual(party_a.organization_name, "Tên công ty của bạn")
        self.assertEqual(party_a.headquarters_address, "Địa chỉ trụ sở chính")
        self.assertFalse(self.window.new_owner_upload.isVisible())
        self.assertEqual(self.window.tabs.tabText(self.window.customer_index), "Tổ chức")
        self.assertEqual(self.window.tabs.tabText(self.window.new_owner_index), "Thuê bao")

    def test_transfer_primary_upload_targets_party_c(self):
        index = self.window.document_combo.findData(DocumentType.TRANSFER.value)
        self.window.document_combo.setCurrentIndex(index)
        image = Path("front.jpg")

        with patch.object(self.window, "_start_ocr") as start_ocr:
            self.window._start_primary_ocr([image])

        start_ocr.assert_called_once_with("new_owner", [image])

    def test_beautiful_number_uses_its_own_required_fields(self):
        index = self.window.document_combo.findData(DocumentType.BEAUTIFUL_NUMBER.value)
        self.window.document_combo.setCurrentIndex(index)
        self.window.customer_tab.form.fields["full_name"].set_value("Nguyễn Văn A")
        self.window.customer_tab.form.fields["id_number"].set_value("001099999999")
        self.window.subscriber_number_field.set_value("0925123456")

        self.assertIsNone(self.window._validated_data())
        monthly_fee = self.window.document_tab.forms[DocumentType.BEAUTIFUL_NUMBER].fields["monthly_fee"]
        self.assertIn("bắt buộc", monthly_fee.error.text())

    def test_upload_first_state_hides_document_and_second_party(self):
        self.assertEqual(self.window.document_combo.currentData(), "")
        self.assertFalse(self.window.tabs.isVisible())
        self.assertFalse(self.window.new_owner_upload.isVisible())
        self.assertFalse(self.window.export_button.isEnabled())

    def test_switching_documents_preserves_identity_data(self):
        self.window.customer_tab.form.fields["full_name"].set_value("Nguyễn Văn A")
        transfer = self.window.document_combo.findData(DocumentType.TRANSFER.value)
        beautiful = self.window.document_combo.findData(DocumentType.BEAUTIFUL_NUMBER.value)
        self.window.document_combo.setCurrentIndex(transfer)
        self.window.document_combo.setCurrentIndex(beautiful)
        self.assertEqual(
            self.window.customer_tab.form.fields["full_name"].value(),
            "Nguyễn Văn A",
        )

    def test_hidden_field_from_previous_document_does_not_block_current_one(self):
        prepaid = self.window.document_combo.findData(DocumentType.PREPAID_CONTRACT.value)
        beautiful = self.window.document_combo.findData(DocumentType.BEAUTIFUL_NUMBER.value)
        self.window.document_combo.setCurrentIndex(prepaid)
        self.window.customer_tab.form.fields["phone"].set_value("123")
        self.window.document_combo.setCurrentIndex(beautiful)
        self.window.customer_tab.form.fields["full_name"].set_value("Nguyễn Văn A")
        self.window.customer_tab.form.fields["id_number"].set_value("001099999999")
        self.window.subscriber_number_field.set_value("0925123456")
        form = self.window.document_tab.forms[DocumentType.BEAUTIFUL_NUMBER]
        form.fields["monthly_fee"].set_value("500.000 đồng")

        self.assertIsNotNone(self.window._validated_data())

    def test_new_case_clears_customer_and_transaction_but_keeps_work_context(self):
        transfer = self.window.document_combo.findData(DocumentType.TRANSFER.value)
        self.window.document_combo.setCurrentIndex(transfer)
        sample = Path("desktop_app/data/source/samples/cccd_front.jpg")
        self.window.customer_upload.accept_result(
            OCRFileResult(sample, CardSide.FRONT, {"full_name": "Khách cũ"}, "", "OCR test")
        )
        self.window.customer_tab.form.fields["full_name"].set_value("Khách cũ")
        self.window.subscriber_number_field.set_value("0925123456")
        self.window.document_tab.common["shop_address"].set_value("123 Xã Đàn (sửa riêng cho ca này)")
        self.window.raw_ocr.setPlainText("OCR cũ")
        self.window.ocr_text_by_target["customer"] = "OCR cũ"
        self.window.ocr_side_errors_by_target["customer"] = ["Lỗi cũ"]

        self.window._new_case()

        self.assertEqual(self.window.document_combo.currentData(), DocumentType.TRANSFER.value)
        # A per-document shop-field edit must NOT survive "Hồ sơ mới" — the
        # next case reverts to the company profile's own default instead.
        self.assertEqual(
            self.window.document_tab.common["shop_address"].value(),
            self.window.company_profile.headquarters_address,
        )
        self.assertEqual(self.window.subscriber_number_field.value(), "")
        self.assertEqual(self.window.customer_tab.form.fields["full_name"].value(), "")
        self.assertEqual(self.window.customer_tab.form.fields["nationality"].value(), "Việt Nam")
        self.assertIsNone(self.window.customer_upload.front_zone.path)
        self.assertEqual(self.window.raw_ocr.toPlainText(), "")
        self.assertEqual(self.window.ocr_side_errors_by_target, {})

    def test_unified_upload_replaces_only_the_same_detected_side(self):
        first_front = OCRFileResult(
            Path("front-old.jpg"), CardSide.FRONT, {"full_name": "Nguyễn Văn A"}, "", "OCR test"
        )
        back = OCRFileResult(
            Path("back.jpg"), CardSide.BACK, {"full_name": "Nguyễn Văn A"}, "", "OCR test"
        )
        new_front = OCRFileResult(
            Path("front-new.jpg"), CardSide.FRONT, {"full_name": "Trần Văn B"}, "", "OCR test"
        )
        card = self.window.customer_upload
        card.accept_result(first_front)
        self.assertEqual(card.status.text(), "Đã nhận diện mặt trước")
        card.accept_result(back)
        self.assertEqual(card.status.text(), "")
        card.accept_result(new_front)
        self.assertEqual(card.front_zone.path, Path("front-new.jpg"))
        self.assertEqual(card.back_zone.path, Path("back.jpg"))
        self.assertEqual(len(card.paths()), 2)

    def test_unified_upload_can_start_with_back_side_only(self):
        card = self.window.customer_upload
        card.accept_result(
            OCRFileResult(Path("back.jpg"), CardSide.BACK, {}, "", "OCR test")
        )
        self.assertEqual(card.status.text(), "Đã nhận diện mặt sau")
        self.assertIsNone(card.front_zone.path)
        self.assertEqual(card.back_zone.path, Path("back.jpg"))

    def test_front_back_name_conflict_produces_risk_warning(self):
        files = [
            OCRFileResult(
                Path("front.jpg"), CardSide.FRONT,
                {"full_name": "Nguyễn Văn A", "id_number": "001090001234"}, "", "OCR test",
            ),
            OCRFileResult(
                Path("back.jpg"), CardSide.BACK,
                {"full_name": "Trần Văn B", "id_number": "001090009999"}, "", "OCR test",
            ),
        ]
        result = combine_file_results(files)
        self.assertTrue(any("Nguy cơ ảnh CCCD không hợp lệ" in item for item in result.warnings))

    def test_new_ocr_rebuilds_identity_instead_of_leaving_old_fields(self):
        self.window.customer_tab.form.fields["full_name"].set_value("Khách cũ")
        self.window.customer_tab.form.fields["address"].set_value("Địa chỉ cũ")
        file_result = OCRFileResult(
            Path("front.jpg"), CardSide.FRONT, {"full_name": "Khách mới"}, "Khách mới", "OCR test"
        )
        self.window._ocr_total_count["customer"] = 1
        self.window._ocr_done_count["customer"] = 0

        self.window._ocr_file_completed("customer", file_result)

        self.assertEqual(self.window.customer_tab.form.fields["full_name"].value(), "Khách mới")
        self.assertEqual(self.window.customer_tab.form.fields["address"].value(), "")

    def test_two_images_resolve_independently_not_in_submission_order(self):
        """The slower image (back) is submitted first but the faster one
        (front) finishes OCR first — the UI must reflect front's result
        immediately rather than waiting for back."""
        front = OCRFileResult(Path("front.jpg"), CardSide.FRONT, {"full_name": "Nguyen Van A"}, "", "OCR test")
        back = OCRFileResult(Path("back.jpg"), CardSide.BACK, {"issue_date": "01/01/2021"}, "", "OCR test")
        self.window._ocr_total_count["customer"] = 2
        self.window._ocr_done_count["customer"] = 0
        self.window._ocr_batch_results["customer"] = []

        self.window._ocr_file_completed("customer", front)

        self.assertEqual(self.window.customer_tab.form.fields["full_name"].value(), "Nguyen Van A")
        self.assertTrue(self.window.customer_upload.front_zone.isVisible() or self.window.customer_upload.front_zone.path)
        self.assertFalse(self.window._ocr_busy())  # no real threads were started in this test

        self.window._ocr_file_completed("customer", back)

        self.assertEqual(self.window.customer_tab.form.fields["issue_date"].value(), "01/01/2021")


if __name__ == "__main__":
    unittest.main()
