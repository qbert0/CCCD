from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from desktop_app.backend.ocr import CardSide, OCRFileResult


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class UnifiedDropZone(QFrame):
    """The single intake point; OCR decides which preview slot receives each image."""

    files_submitted = pyqtSignal(list)
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("imageDropZone")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 22, 16, 22)
        layout.setSpacing(6)
        title = QLabel("Gửi ảnh vào đây")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.casefold() in IMAGE_SUFFIXES:
            self.setProperty("dragActive", True)
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._clear_drag_state()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._clear_drag_state()
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if Path(url.toLocalFile()).suffix.casefold() in IMAGE_SUFFIXES
        ]
        if paths:
            self.files_submitted.emit(paths)
            event.acceptProposedAction()

    def _clear_drag_state(self) -> None:
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)


class ImagePreviewSlot(QFrame):
    def __init__(self, side: CardSide, parent=None):
        super().__init__(parent)
        self.side = side
        self.path: Path | None = None
        self.result: OCRFileResult | None = None
        self.setObjectName("imagePreviewSlot")
        self.setMaximumWidth(230)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)
        self.badge = QLabel("MẶT TRƯỚC" if side == CardSide.FRONT else "MẶT SAU")
        self.badge.setObjectName("sideBadge")
        self.preview = QLabel()
        self.preview.setObjectName("imagePreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(130)
        self.filename = QLabel()
        self.filename.setObjectName("microText")
        self.filename.setAlignment(Qt.AlignCenter)
        self.filename.setWordWrap(True)
        layout.addWidget(self.badge, 0, Qt.AlignLeft)
        layout.addWidget(self.preview)
        layout.addWidget(self.filename)
        self.hide()

    def set_result(self, result: OCRFileResult) -> None:
        self.result = result
        self.path = result.path
        pixmap = QPixmap(str(result.path))
        if pixmap.isNull():
            self.preview.setText("Không thể hiển thị ảnh")
        else:
            self.preview.setPixmap(
                pixmap.scaled(210, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        self.badge.setText(
            "✓ MẶT TRƯỚC"
            if self.side == CardSide.FRONT
            else "✓ MẶT SAU"
        )
        self.badge.setProperty("detected", True)
        self.filename.setText(f"{result.path.name} · {result.source}")
        self.show()
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def clear_file(self) -> None:
        self.path = None
        self.result = None
        self.preview.clear()
        self.filename.clear()
        self.hide()


class ImageUploadCard(QFrame):
    image_requested = pyqtSignal()
    files_submitted = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("uploadCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Not shown anymore -- the red note below already carries error
        # text, and the "ẢNH ĐÃ NHẬN DIỆN" eyebrow already carries progress/
        # success state, so this line was pure redundant clutter above the
        # drop zone. Kept as a live (but invisible) widget since the rest of
        # this class still updates its text/property as state changes.
        self.status = QLabel("Chưa có ảnh", self)
        self.status.setObjectName("uploadStatus")
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status.hide()

        self.drop_zone = UnifiedDropZone()
        self.drop_zone.clicked.connect(self.image_requested)
        self.drop_zone.files_submitted.connect(self._submit)
        layout.addWidget(self.drop_zone)

        self.preview_label = QLabel("ẢNH ĐÃ NHẬN DIỆN")
        self.preview_label.setObjectName("sectionEyebrow")
        self.preview_label.hide()
        layout.addWidget(self.preview_label)

        previews = QHBoxLayout()
        previews.setSpacing(10)
        self.front_zone = ImagePreviewSlot(CardSide.FRONT)
        self.back_zone = ImagePreviewSlot(CardSide.BACK)
        previews.addWidget(self.front_zone)
        previews.addWidget(self.back_zone)
        layout.addLayout(previews)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName("uploadNote")
        self.note.hide()
        layout.addWidget(self.note)

    def _submit(self, paths: list[Path]) -> None:
        if not paths:
            return
        self.status.setText("Đang đọc ảnh…" if len(paths) == 1 else f"Đang đọc {len(paths)} ảnh…")
        self.status.setProperty("invalid", False)
        self._refresh_status_style()
        self.files_submitted.emit(paths)

    def submit_file(self, path: Path) -> None:
        self._submit([path])

    def submit_files(self, paths: list[Path]) -> None:
        self._submit(paths)

    def accept_result(self, result: OCRFileResult) -> bool:
        if result.error or result.side == CardSide.UNKNOWN:
            self.status.setText("Chưa xác định được mặt CCCD")
            self.status.setProperty("invalid", True)
            self.note.setText(
                result.error
                or "Ảnh chưa đủ rõ để nhận biết mặt trước/mặt sau. Ảnh cũ vẫn được giữ nguyên."
            )
            self.note.setProperty("invalid", True)
            self.note.show()
            self._refresh_status_style()
            return False
        self._zone(result.side).set_result(result)
        self._update_summary()
        return True

    def _zone(self, side: CardSide) -> ImagePreviewSlot:
        return self.front_zone if side == CardSide.FRONT else self.back_zone

    def paths(self) -> list[Path]:
        return [zone.path for zone in (self.front_zone, self.back_zone) if zone.path]

    def file_results(self) -> list[OCRFileResult]:
        return [zone.result for zone in (self.front_zone, self.back_zone) if zone.result]

    def set_identity_warning(self, warning: str = "") -> None:
        if warning:
            self.status.setText("Nguy cơ ảnh không hợp lệ")
            self.status.setProperty("invalid", True)
            self.note.setText(warning)
            self.note.setProperty("invalid", True)
            self.note.show()
        else:
            self.note.clear()
            self.note.hide()
            self.note.setProperty("invalid", False)
            self._update_summary()
        self._refresh_status_style()

    def set_scan_progress(self, done: int, total: int) -> None:
        self.preview_label.setText(f"ĐANG NHẬN DIỆN ẢNH… {done}/{total}")
        self.preview_label.show()

    def clear_scan_progress(self) -> None:
        self.preview_label.setText("ẢNH ĐÃ NHẬN DIỆN")
        self._update_summary()

    def _update_summary(self) -> None:
        front, back = self.front_zone.path, self.back_zone.path
        self.preview_label.setVisible(bool(front or back))
        if front and back:
            # Both thumbnails are already visible below — no need to also
            # spell out "đã nhận diện đủ 2 mặt" in text.
            text = ""
        elif front:
            text = "Đã nhận diện mặt trước"
        elif back:
            text = "Đã nhận diện mặt sau"
        else:
            text = "Chưa có ảnh"
        self.status.setText(text)
        self.status.setProperty("invalid", False)
        self._refresh_status_style()

    def _refresh_status_style(self) -> None:
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.note.style().unpolish(self.note)
        self.note.style().polish(self.note)

    def set_busy(self, busy: bool) -> None:
        self.drop_zone.setEnabled(not busy)

    def clear_files(self) -> None:
        self.front_zone.clear_file()
        self.back_zone.clear_file()
        self.note.clear()
        self.note.hide()
        self.note.setProperty("invalid", False)
        self._update_summary()
