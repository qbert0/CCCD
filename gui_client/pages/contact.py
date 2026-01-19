from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit
from PyQt5.QtCore import Qt

class ContactPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        lbl_title = QLabel("HƯỚNG DẪN & LIÊN HỆ")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignCenter)

        content = QTextEdit()
        content.setReadOnly(True)
        content.setHtml("""
        <h3>Cách sử dụng phần mềm:</h3>
        <ul>
            <li><b>Bước 1:</b> Vào trang Dashboard để xem ngày giờ.</li>
            <li><b>Bước 2:</b> Vào trang Xử lý ảnh.</li>
            <li><b>Bước 3:</b> Mở thư mục trên máy tính, bôi đen 100 ảnh và kéo vào phần mềm.</li>
        </ul>
        <hr>
        <p>Liên hệ admin: admin@example.com</p>
        """)

        layout.addWidget(lbl_title)
        layout.addWidget(content)
        self.setLayout(layout)