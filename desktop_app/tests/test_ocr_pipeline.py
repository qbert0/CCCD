import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from desktop_app.backend.ocr import CardSide, OCRService
from desktop_app.backend.ocr.engines.base import EngineResult
from desktop_app.backend.ocr.engines.paddle import restore_cccd_vietnamese
from desktop_app.backend.ocr.service import detect_side


class OCRPipelineTest(unittest.TestCase):
    def test_restores_vietnamese_labels_on_back_side(self):
        raw = (
            "Ngay,thang,nam/Date,month,year27/04/2021\n"
            "Dac diemnhan dang/ Personal identification.\n"
            "Ngon tro.träi\n"
            "QUAN LYHANH CHINH VE TRATTU'XA HOI\n"
            "CUC TRU'ONG CUC CANH SAT\n"
            "Seo cham ngay duoi mat phai"
        )
        restored = restore_cccd_vietnamese(raw)
        self.assertIn("Ngày, tháng, năm / Date, month, year: 27/04/2021", restored)
        self.assertIn("Đặc điểm nhận dạng / Personal identification", restored)
        self.assertIn("Ngón trỏ trái / Left index finger", restored)
        self.assertIn("QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI", restored)
        self.assertIn("CỤC TRƯỞNG CỤC CẢNH SÁT", restored)
        self.assertIn("Sẹo chấm ngay dưới mắt phải", restored)

    def test_detects_front_and_back(self):
        self.assertEqual(detect_side("001099999999|OLD|NAME", "QR CCCD"), CardSide.FRONT)
        self.assertEqual(
            detect_side("QUE QUAN Thanh Hoa\nNOI THUONG TRU Ha Noi", "PaddleOCR local"),
            CardSide.FRONT,
        )
        self.assertEqual(
            detect_side("NGUYEN<<VAN<A<<<<\nIDVNM001099999999<<", "PaddleOCR local"),
            CardSide.BACK,
        )
        self.assertEqual(
            detect_side("CĂN CƯỚC CÔNG DÂN\nHỌ VÀ TÊN: NGUYỄN VĂN A", "PaddleOCR local"),
            CardSide.FRONT,
        )

    @patch("desktop_app.backend.ocr.service.read_image")
    @patch("desktop_app.backend.ocr.service.normalize_card")
    def test_front_image_in_back_slot_is_rejected(self, normalize, read):
        image = np.zeros((50, 80, 3), dtype=np.uint8)
        read.return_value = image
        normalize.return_value = image
        registry = Mock()
        registry.recognize.return_value = EngineResult(
            {"id_number": "001099999999", "full_name": "Nguyễn Văn A"},
            "001099999999||NGUYEN VAN A|01012000|Nam|Ha Noi|01012021",
            "QR CCCD",
        )

        result = OCRService(registry).scan_files(
            [Path("front-used-as-back.jpg")],
            [CardSide.BACK],
        )

        self.assertTrue(result.files[0].side_mismatch)
        self.assertEqual(result.files[0].expected_side, CardSide.BACK)
        self.assertEqual(result.fields, {})
        self.assertIn("khung MẶT SAU", result.warnings[0])

    @patch("desktop_app.backend.ocr.service.read_image")
    @patch("desktop_app.backend.ocr.service.normalize_card")
    def test_same_front_file_in_both_slots_only_populates_front(self, normalize, read):
        image = np.zeros((50, 80, 3), dtype=np.uint8)
        read.return_value = image
        normalize.return_value = image
        registry = Mock()
        registry.recognize.return_value = EngineResult(
            {"id_number": "001099999999"},
            "001099999999||NGUYEN VAN A|01012000|Nam|Ha Noi|01012021",
            "QR CCCD",
        )
        path = Path("same-front.jpg")

        result = OCRService(registry).scan_files(
            [path, path],
            [CardSide.FRONT, CardSide.BACK],
        )

        self.assertFalse(result.files[0].side_mismatch)
        self.assertTrue(result.files[1].side_mismatch)
        self.assertEqual(result.fields["id_number"], "001099999999")

    @patch("desktop_app.backend.ocr.service.read_image")
    @patch("desktop_app.backend.ocr.service.normalize_card")
    def test_qr_does_not_skip_back_side(self, normalize, read):
        image = np.zeros((50, 80, 3), dtype=np.uint8)
        read.return_value = image
        normalize.return_value = image
        registry = Mock()
        registry.recognize.side_effect = [
            EngineResult(
                {"id_number": "001099999999"},
                "001099999999||NGUYEN VAN A|01012000|Nam|Ha Noi|01012021",
                "QR CCCD",
            ),
            EngineResult(
                {"id_number": "001099999999", "expiry_date": "01/01/2030"},
                "NGUYEN<<VAN<A<<<<\n010100M300101VNM",
                "PaddleOCR local",
            ),
        ]

        result = OCRService(registry).scan_files([Path("front.jpg"), Path("back.jpg")])

        self.assertEqual(registry.recognize.call_count, 2)
        self.assertEqual(result.fields["expiry_date"], "01/01/2030")
        self.assertEqual([item.side for item in result.files], [CardSide.FRONT, CardSide.BACK])

    @patch("desktop_app.backend.ocr.service.read_image")
    @patch("desktop_app.backend.ocr.service.normalize_card")
    def test_one_failed_side_keeps_successful_data(self, normalize, read):
        image = np.zeros((50, 80, 3), dtype=np.uint8)
        read.return_value = image
        normalize.return_value = image
        registry = Mock()
        registry.recognize.side_effect = [
            EngineResult({"id_number": "001099999999"}, "MẶT TRƯỚC", "PaddleOCR local"),
            RuntimeError("ảnh mặt sau quá mờ"),
        ]

        result = OCRService(registry).scan_files([Path("front.jpg"), Path("back.jpg")])

        self.assertEqual(result.fields["id_number"], "001099999999")
        self.assertEqual(len(result.warnings), 1)
        self.assertTrue(result.files[1].error)


if __name__ == "__main__":
    unittest.main()
