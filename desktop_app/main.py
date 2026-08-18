from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Must run before QtWebEngineWidgets is imported anywhere (Chromium reads it
# at sandbox-init time): a known PyInstaller+QtWebEngine gotcha on restricted/
# non-root machines where the frozen build would otherwise show a blank
# window. Only for the frozen case -- running from source under a normal
# user session doesn't need it.
if getattr(sys, "frozen", False):
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from desktop_app.backend.documents import DocumentRegistry
from desktop_app.backend.domain.models import DocumentType, PersonData, ReportData
from desktop_app.backend.ocr import OCRService
from desktop_app.backend.ocr.service import _log_error
from desktop_app.backend.paths import source_data_dir
from desktop_app.frontend.pages.web_home_page import WebHomePage
from desktop_app.frontend.styles import APP_STYLE


def self_test(full: bool = False) -> int:
    try:
        samples = source_data_dir() / "samples"
        front = samples / "cccd_front.jpg"
        back = samples / "cccd_back.jpg"
        result = OCRService().scan_files([front, back] if full else [front])
        if result.fields.get("id_number") != "001099999999":
            _log_error("Self-test OCR", f"{result.fields}\n{result.raw_text}")
            return 2
        if full:
            sides = {item.side.value for item in result.files or []}
            if not {"front", "back"}.issubset(sides):
                _log_error("Self-test sides", f"Không nhận đủ hai mặt: {sides}")
                return 3
            expected_back = {"issue_date": "01/01/2021", "expiry_date": "01/01/2036"}
            if any(result.fields.get(key) != value for key, value in expected_back.items()):
                _log_error("Self-test back fields", f"{result.fields}\n{result.raw_text}")
                return 5
            vietnamese_labels = ("Ngày, tháng, năm", "Đặc điểm nhận dạng")
            if not all(label in result.raw_text for label in vietnamese_labels):
                _log_error("Self-test Vietnamese back", result.raw_text)
                return 6
        sample = ReportData(
            document_type=DocumentType.BEAUTIFUL_NUMBER,
            customer=PersonData(full_name="NGUYỄN VĂN TEST", id_number="001099999999"),
            subscriber_number="0925123456",
            monthly_fee="500.000 đồng",
        )
        output = DocumentRegistry().for_data(sample).preview(
            sample, Path(tempfile.gettempdir()) / "CCCDReportSelfTest"
        )
        return 0 if output.exists() else 4
    except Exception as exc:
        _log_error("Self-test", exc)
        return 1


def main() -> int:
    if "--self-test" in sys.argv or "--self-test-full" in sys.argv:
        return self_test("--self-test-full" in sys.argv)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("CCCD Report")
    app.setOrganizationName("CCCDReport")
    app.setStyleSheet(APP_STYLE)  # still styles the native QFileDialog/QMessageBox the web bridge opens
    window = WebHomePage()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
