from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QListWidget, QListWidgetItem, QTextEdit, QSplitter)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QIcon

class ImagePageView(QWidget):
    # Signal gửi ra ngoài cho Controller bắt
    signal_files_dropped = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True) # Cho phép kéo thả
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Header ---
        self.lbl_instruction = QLabel("📥 Kéo thả ảnh vào danh sách bên dưới")
        self.lbl_instruction.setStyleSheet("font-weight: bold; padding: 5px; background: #e1e1e1;")
        main_layout.addWidget(self.lbl_instruction)

        # --- Main Splitter (Chia 3 cột) ---
        splitter = QSplitter(Qt.Horizontal)

        # 1. Cột Danh Sách (List)
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(50, 50))
        self.list_widget.setMinimumWidth(200)
        splitter.addWidget(self.create_wrapper("1. Danh sách ảnh", self.list_widget))

        # 2. Cột Xem Ảnh (Image Viewer)
        self.lbl_image_viewer = QLabel("Chưa chọn ảnh")
        self.lbl_image_viewer.setAlignment(Qt.AlignCenter)
        self.lbl_image_viewer.setStyleSheet("background: #333; color: #fff;")
        self.lbl_image_viewer.setScaledContents(False) # Để False, ta tự scale trong logic cho đẹp
        splitter.addWidget(self.create_wrapper("2. Xem trước", self.lbl_image_viewer))

        # 3. Cột Kết Quả (Text Output)
        self.txt_result = QTextEdit()
        self.txt_result.setPlaceholderText("Kết quả OCR sẽ hiện tại đây...")
        splitter.addWidget(self.create_wrapper("3. Kết quả text", self.txt_result))

        # Tỷ lệ chia cột: 20% - 40% - 40%
        splitter.setSizes([200, 400, 400])
        main_layout.addWidget(splitter)
        
        self.setLayout(main_layout)

    def create_wrapper(self, title, widget):
        """Hàm helper để tạo khung có tiêu đề cho đẹp"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        lbl = QLabel(title)
        lbl.setStyleSheet("color: blue; font-weight: bold;")
        layout.addWidget(lbl)
        layout.addWidget(widget)
        return container

    # --- Sự kiện Kéo Thả (Drag & Drop) ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        # Lọc lấy đường dẫn file local
        file_paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if file_paths:
            self.signal_files_dropped.emit(file_paths)

    # --- Các hàm cập nhật giao diện (được gọi từ Controller) ---
    def add_item_to_list(self, file_path, file_name):
        item = QListWidgetItem(QIcon(file_path), file_name)
        item.setData(Qt.UserRole, file_path)   # Lưu đường dẫn ảnh
        item.setData(Qt.UserRole + 1, "")      # Lưu kết quả text (ban đầu rỗng)
        self.list_widget.addItem(item)

    def update_item_status(self, file_path, text_result):
        """Tìm item theo path và cập nhật kết quả"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == file_path:
                item.setText(f"✅ {item.text()}")
                item.setData(Qt.UserRole + 1, text_result) # Lưu kết quả vào item
                
                # Nếu đang chọn item này thì update luôn khung text
                if self.list_widget.currentItem() == item:
                    self.txt_result.setText(text_result)
                break

    def show_selected_image(self, file_path, text_content):
        """Hiển thị ảnh và text lên 2 khung bên phải"""
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            # Scale ảnh cho vừa khung nhìn nhưng giữ tỷ lệ
            scaled = pixmap.scaled(self.lbl_image_viewer.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_image_viewer.setPixmap(scaled)
        
        self.txt_result.setText(text_content if text_content else "Đang xử lý...")