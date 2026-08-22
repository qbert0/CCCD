from __future__ import annotations

import re
from datetime import datetime

from PyQt5.QtCore import QDate, QEvent, QLocale, QRegularExpression, Qt, pyqtSignal
from PyQt5.QtGui import QRegularExpressionValidator
from PyQt5.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

DATE_FORMAT = "dd/MM/yyyy"


class FieldInput(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        label: str,
        path: str,
        required: bool = False,
        placeholder: str = "",
        input_kind: str = "text",
        helper: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.path = path
        self._label_text = label
        self._required = required
        self._input_kind = input_kind
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(5)
        self.label = QLabel()
        self.label.setObjectName("fieldLabel")
        self.input = QLineEdit()
        # Placeholder is a format hint, not a label stand-in: for free text
        # it echoes the field name, but a date field's own name never tells
        # you the expected format, so it shows the pattern instead.
        self.input.setPlaceholderText(placeholder or (DATE_FORMAT.casefold() if input_kind == "date" else f"Nhập {label.casefold()}"))
        self.input.textChanged.connect(self._on_changed)
        if input_kind == "number":
            self.input.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9 ]*"), self.input))
        if input_kind == "date":
            # No separate "choose" button: clicking anywhere in the field
            # itself opens the calendar, right below it. Typing still works
            # (via keyboard focus/Tab) so the field can stay empty or hold
            # a value the calendar can't produce.
            self.input.setCursor(Qt.PointingHandCursor)
            self.input.installEventFilter(self)
            self.input.editingFinished.connect(self._validate_date)

        self.helper = QLabel(helper)
        self.helper.setObjectName("fieldHelper")
        self.helper.setWordWrap(True)
        self.helper.setVisible(bool(helper))

        self.error = QLabel()
        self.error.setObjectName("fieldError")
        self.error.setVisible(False)
        self.error.setWordWrap(True)
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.helper)
        layout.addWidget(self.error)
        self.set_required(required)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.input and event.type() == QEvent.MouseButtonPress:
            self._open_calendar()
            # Let QLineEdit receive the same click so the caret can be placed
            # and the date can still be typed manually while the picker is
            # available.
            return False
        return super().eventFilter(obj, event)

    def _open_calendar(self) -> None:
        self.input.setFocus()
        popup = QWidget(self, Qt.Popup)
        popup.setObjectName("datePickerPopup")
        popup_layout = QVBoxLayout(popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        calendar = QCalendarWidget(popup)
        calendar.setObjectName("datePickerCalendar")
        calendar.setLocale(QLocale(QLocale.Vietnamese, QLocale.Vietnam))
        calendar.setGridVisible(False)
        calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        calendar.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        current = QDate.fromString(self.input.text().strip(), DATE_FORMAT)
        calendar.setSelectedDate(current if current.isValid() else QDate.currentDate())
        calendar.clicked.connect(lambda date: self._pick_date(date, popup))
        popup_layout.addWidget(calendar)

        # Always open directly below the field itself -- never let the
        # window manager flip it above, only nudge it sideways if it would
        # otherwise run off the right edge of the screen.
        anchor = self.input.mapToGlobal(self.input.rect().bottomLeft())
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            popup_width = max(calendar.sizeHint().width(), 260)
            x = min(anchor.x(), available.right() - popup_width)
            anchor.setX(max(x, available.left()))
        popup.move(anchor)
        popup.show()

    def _pick_date(self, date: QDate, popup: QWidget) -> None:
        self.input.setText(date.toString(DATE_FORMAT))
        popup.close()

    def _on_changed(self) -> None:
        value = self.input.text().strip()
        if self._input_kind == "date" and len(value) >= 10:
            self._validate_date()
        elif value:
            self.clear_error()
        self.changed.emit()

    @staticmethod
    def _parsed_date(value: str):
        for date_format in ("%d/%m/%Y",):
            try:
                return datetime.strptime(value, date_format)
            except ValueError:
                pass
        return None

    def _validate_date(self) -> None:
        value = self.input.text().strip()
        if not value:
            self.clear_error()
            return
        parsed = self._parsed_date(value)
        if parsed is None or not re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value):
            self.set_error("Ngày không hợp lệ. Hãy nhập đúng DD/MM/YYYY.")
            return
        normalized = parsed.strftime("%d/%m/%Y")
        if normalized != value:
            self.input.setText(normalized)
        self.clear_error()

    def set_required(self, required: bool) -> None:
        self._required = required
        star = ' <span style="color:#cf2d56">*</span>' if required else ""
        self.label.setText(f"{self._label_text}{star}")

    def is_required(self) -> bool:
        return self._required

    def value(self) -> str:
        return self.input.text().strip()

    def set_value(self, value: str) -> None:
        self.input.setText(str(value or "").strip())

    def set_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(True)
        # The error message replaces the helper hint rather than stacking
        # under it -- two gray/red lines competing under one input reads as
        # noise, and the error is strictly the more urgent of the two.
        self.helper.setVisible(False)
        self.input.setProperty("invalid", True)
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)

    def clear_error(self) -> None:
        self.error.clear()
        self.error.setVisible(False)
        self.helper.setVisible(bool(self.helper.text()))
        self.input.setProperty("invalid", False)
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)
