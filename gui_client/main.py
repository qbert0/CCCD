import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QStackedWidget, QFrame)
from pages.dashboard import DashboardPage
from pages.image_controller import ImageProcessingPage
from pages.contact import ContactPage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("My App - MVC Structure")
        self.resize(900, 600)

        # --- Layout chính: Chia làm 2 phần (Menu trái - Nội dung phải) ---
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_widget.setLayout(main_layout)
        self.central_widget = ImageProcessingPage()
        self.setCentralWidget(main_widget)

        # 1. MENU BÊN TRÁI
        self.menu_frame = QFrame()
        self.menu_frame.setStyleSheet("background-color: #2c3e50; color: white;")
        self.menu_frame.setFixedWidth(200)
        menu_layout = QVBoxLayout()

        # Các nút menu
        self.btn_dashboard = self.create_nav_button("Dashboard")
        self.btn_image = self.create_nav_button("Xử lý Ảnh")
        self.btn_contact = self.create_nav_button("Hướng dẫn")

        menu_layout.addWidget(self.btn_dashboard)
        menu_layout.addWidget(self.btn_image)
        menu_layout.addWidget(self.btn_contact)
        menu_layout.addStretch()
        self.menu_frame.setLayout(menu_layout)

        # 2. VÙNG NỘI DUNG BÊN PHẢI (StackedWidget)
        self.content_stack = QStackedWidget()
        
        # Khởi tạo các trang từ thư mục pages
        self.page_1 = DashboardPage()
        self.page_2 = ImageProcessingPage()
        self.page_3 = ContactPage()

        self.content_stack.addWidget(self.page_1) # Index 0
        self.content_stack.addWidget(self.page_2) # Index 1
        self.content_stack.addWidget(self.page_3) # Index 2

        # Ghép 2 phần vào layout chính
        main_layout.addWidget(self.menu_frame)
        main_layout.addWidget(self.content_stack)

        # --- Sự kiện chuyển trang ---
        self.btn_dashboard.clicked.connect(lambda: self.switch_page(0, self.btn_dashboard))
        self.btn_image.clicked.connect(lambda: self.switch_page(1, self.btn_image))
        self.btn_contact.clicked.connect(lambda: self.switch_page(2, self.btn_contact))

        # Mặc định chọn trang 1
        self.switch_page(0, self.btn_dashboard)

    def create_nav_button(self, text):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setStyleSheet("""
            QPushButton { border: none; padding: 15px; text-align: left; font-size: 16px; }
            QPushButton:hover { background-color: #34495e; }
            QPushButton:checked { background-color: #3498db; font-weight: bold;}
        """)
        return btn

    def switch_page(self, index, button_sender):
        # Chuyển stack sang trang tương ứng
        self.content_stack.setCurrentIndex(index)
        
        # Reset trạng thái các nút (để chỉ nút đang chọn sáng màu)
        self.btn_dashboard.setChecked(False)
        self.btn_image.setChecked(False)
        self.btn_contact.setChecked(False)
        button_sender.setChecked(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())