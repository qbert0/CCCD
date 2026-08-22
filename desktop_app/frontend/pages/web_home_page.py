from __future__ import annotations

from PyQt5.QtCore import QUrl
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QMainWindow

from desktop_app.backend.paths import resource_path
from desktop_app.frontend.web_bridge import WebBridge


class WebHomePage(QMainWindow):
    """The application's only window: a single QWebEngineView hosting the
    HTML/CSS/JS view layer, driven by WebBridge over QWebChannel. All
    business logic (OCR, validation, document generation, field layout)
    lives in desktop_app/backend and desktop_app/frontend/web_bridge -- this
    class only wires the view into a native window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CCCD Report · Đọc căn cước và tạo tài liệu")
        self.resize(1400, 900)

        self.view = QWebEngineView()
        self.setCentralWidget(self.view)

        self.bridge = WebBridge(self)
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        index = resource_path("desktop_app", "frontend", "web", "index.html")
        self.view.load(QUrl.fromLocalFile(str(index)))

    def closeEvent(self, event) -> None:
        self.view.page().runJavaScript(
            "JSON.stringify(CCCD.reportDataSnapshot())",
            lambda state_json: self.bridge.persist_operator_fields(state_json) if state_json else None,
        )
        super().closeEvent(event)
