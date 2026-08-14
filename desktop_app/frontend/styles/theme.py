"""Cursor-inspired desktop tokens adapted from baseDesign/cursor.md."""

from desktop_app.backend.paths import resource_path

_CHEVRON_DOWN = resource_path("desktop_app", "assets", "chevron-down.png").as_posix()
_CHECKMARK = resource_path("desktop_app", "assets", "checkmark.png").as_posix()

APP_STYLE = """
QWidget {
    font-family: "Inter", "Helvetica Neue", "Noto Sans", "Segoe UI", sans-serif;
    font-size: 14px;
    font-weight: 400;
    color: #26251e;
}
QMainWindow, #pageRoot { background: #f7f7f4; }

#headerCard {
    background: #f7f7f4;
    border: 0;
    border-bottom: 1px solid #e6e5e0;
    border-radius: 0;
}
#brandTitle {
    color: #f54e00;
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.3px;
}
#headerCard #mutedText { color: #807d72; font-size: 13px; }
#engineBadge {
    color: #5a5852;
    background: #e6e5e0;
    border-radius: 10px;
    padding: 5px 10px;
    font-family: "JetBrains Mono", "Noto Sans Mono", monospace;
    font-size: 10px;
}

#uploadCard, #ocrCard, #contentCard {
    background: #ffffff;
    border: 1px solid #e6e5e0;
    border-radius: 12px;
}
#sectionTitle {
    color: #26251e;
    font-size: 19px;
    font-weight: 600;
    letter-spacing: -0.15px;
}
#documentTitle {
    color: #26251e;
    font-size: 18px;
    font-weight: 400;
    letter-spacing: -0.15px;
    padding: 4px 2px 6px 2px;
}
#subsectionTitle {
    color: #26251e;
    font-size: 14px;
    font-weight: 600;
    padding-top: 5px;
}
#sectionEyebrow {
    color: #807d72;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
    padding-top: 6px;
}
#dialogTitle { color: #26251e; font-size: 24px; font-weight: 400; letter-spacing: -0.3px; }
#fieldLabel { color: #5a5852; font-size: 12px; font-weight: 600; }
#fieldError { color: #cf2d56; font-size: 11px; }
#mutedText { color: #807d72; font-size: 12px; }
#microText { color: #a09c92; font-size: 10px; }
#emptyState { color: #26251e; font-size: 17px; font-weight: 600; }
#emptyStateHint { color: #a09c92; font-size: 13px; }
#uploadStatus {
    color: #807d72;
    background: #f7f7f4;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 10px;
}
#uploadStatus[invalid="true"] { color: #cf2d56; background: #fff0f3; }

QLineEdit, QComboBox, QTextEdit {
    background: #ffffff;
    color: #26251e;
    border: 1px solid #cfcdc4;
    border-radius: 8px;
    padding: 10px 13px;
    selection-background-color: #26251e;
    selection-color: #ffffff;
}
QLineEdit, QComboBox { min-height: 22px; }
QLineEdit:hover, QComboBox:hover, QTextEdit:hover { border-color: #a09c92; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border: 2px solid #807d72; }
QLineEdit[invalid="true"] { border: 2px solid #cf2d56; background: #fff9fa; }
QTextEdit[readOnly="true"] {
    background: #fafaf7;
    border-color: #efeee8;
    font-family: "JetBrains Mono", "Noto Sans Mono", monospace;
    font-size: 11px;
}
QComboBox::drop-down {
    border-left: 1px solid #e6e5e0;
    width: 26px;
}
QComboBox::down-arrow {
    image: url(__CHEVRON_DOWN__);
    width: 10px;
    height: 10px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #26251e;
    border: 1px solid #e6e5e0;
    border-radius: 8px;
    padding: 4px;
    outline: 0;
    selection-background-color: #26251e;
    selection-color: #f7f7f4;
}
QCheckBox { spacing: 8px; color: #5a5852; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #cfcdc4;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:hover { border-color: #807d72; }
QCheckBox::indicator:checked {
    image: url(__CHECKMARK__);
    background: #26251e;
    border-color: #26251e;
}

QPushButton {
    background: #ffffff;
    color: #26251e;
    border: 1px solid #cfcdc4;
    border-radius: 8px;
    padding: 9px 16px;
    min-height: 20px;
    font-size: 13px;
    font-weight: 500;
}
QPushButton:hover { background: #fafaf7; border-color: #a09c92; }
QPushButton:pressed { background: #efeee8; }
#primaryButton { background: #f54e00; color: #ffffff; border-color: #f54e00; }
#primaryButton:hover { background: #e2480a; border-color: #e2480a; }
#primaryButton:pressed { background: #d04200; border-color: #d04200; }
#secondaryButton, #neutralButton { background: #ffffff; color: #26251e; border-color: #cfcdc4; }
#successButton { background: #26251e; color: #f7f7f4; border-color: #26251e; }
#refreshButton {
    background: transparent;
    color: #5a5852;
    border-color: #cfcdc4;
}
#refreshButton:pressed { background: #efeee8; }
#successButton:hover { background: #3a382e; border-color: #3a382e; }
#successButton:pressed { background: #171610; border-color: #171610; }
#primaryButton:disabled, #secondaryButton:disabled, #neutralButton:disabled, #successButton:disabled {
    background: #efeee8;
    color: #a09c92;
    border-color: #e6e5e0;
}
#disclosureButton {
    background: transparent;
    border: 0;
    color: #26251e;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: -0.1px;
    padding: 0;
    min-height: 0;
    text-align: left;
}
#disclosureButton:hover, #disclosureButton:pressed { background: transparent; color: #5a5852; }

#imageDropZone {
    background: #fafaf7;
    border: 1px solid #e6e5e0;
    border-radius: 8px;
}
#imageDropZone:hover { border-color: #cfcdc4; background: #f5f4ef; }
#imageDropZone[dragActive="true"] { border: 2px solid #f54e00; background: #fff8f4; }
#imageDropZone[invalid="true"] { border: 2px solid #cf2d56; background: #fff9fa; }
#dropTitle { color: #26251e; font-size: 14px; font-weight: 600; }
#imagePreviewSlot {
    background: #fafaf7;
    border: 1px solid #e6e5e0;
    border-radius: 8px;
}
#imagePreview { background: transparent; border: 0; color: #807d72; font-size: 12px; }
#uploadNote {
    color: #5a5852;
    background: #f5f4ef;
    border-radius: 7px;
    padding: 7px 9px;
    font-size: 11px;
}
#uploadNote[invalid="true"] { color: #a3183d; background: #fff0f3; }
#sideBadge {
    color: #5a5852;
    background: #e6e5e0;
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.6px;
}
#sideBadge[detected="true"] { color: #ffffff; background: #1f8a65; }

QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #efeee8;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background: #f7f7f4;
    color: #807d72;
    border: 1px solid #e6e5e0;
    border-bottom: 0;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 15px;
    margin-right: 4px;
}
QTabBar::tab:selected { background: #26251e; color: #f7f7f4; border-color: #26251e; }
QTabBar::tab:hover:!selected { background: #efeee8; color: #26251e; }
QScrollArea { background: transparent; border: 0; }
QScrollArea > QWidget > QWidget { background: #ffffff; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #cfcdc4; min-height: 28px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { border-left: 1px solid #e6e5e0; margin: 0 6px; }
QStatusBar {
    background: #f7f7f4;
    color: #807d72;
    border-top: 1px solid #e6e5e0;
    font-size: 11px;
}
QMessageBox, QDialog { background: #f7f7f4; }

#datePickerPopup {
    background: #ffffff;
    border: 1px solid #e6e5e0;
    border-radius: 10px;
}
QCalendarWidget { background: #ffffff; border: 0; }
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: #fafaf7;
    border-bottom: 1px solid #e6e5e0;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}
QCalendarWidget QToolButton {
    color: #26251e;
    background: transparent;
    border: 0;
    border-radius: 6px;
    font-weight: 600;
    font-size: 13px;
    padding: 6px 8px;
}
QCalendarWidget QToolButton:hover { background: #efeee8; }
QCalendarWidget QToolButton::menu-indicator { image: none; }
QCalendarWidget QSpinBox {
    background: #ffffff;
    color: #26251e;
    border: 1px solid #cfcdc4;
    border-radius: 6px;
    padding: 2px 4px;
}
QCalendarWidget QAbstractItemView {
    background: #ffffff;
    color: #26251e;
    selection-background-color: #f54e00;
    selection-color: #ffffff;
    outline: 0;
    font-size: 13px;
    gridline-color: transparent;
}
QCalendarWidget QTableView { border: 0; }
"""

APP_STYLE = APP_STYLE.replace("__CHEVRON_DOWN__", _CHEVRON_DOWN).replace("__CHECKMARK__", _CHECKMARK)
