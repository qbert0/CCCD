from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, QDate

class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Tiêu đề
        lbl_title = QLabel("DASHBOARD")
        lbl_title.setStyleSheet("font-size: 24px; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignCenter)

        # Ngày hiện tại
        current_date = QDate.currentDate().toString("dd/MM/yyyy")
        lbl_date = QLabel(f"Hôm nay là: {current_date}")
        lbl_date.setStyleSheet("font-size: 18px; color: #2980b9;")
        lbl_date.setAlignment(Qt.AlignCenter)

        layout.addStretch()
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_date)
        layout.addStretch()
        
        self.setLayout(layout)