import os
from PyQt5.QtCore import QThread, Qt

# Import 2 file trên
from pages.image import ImagePageView
from modules.ocr_service import OCRWorker

class ImageProcessingPage(ImagePageView):
    def __init__(self):
        super().__init__()
        
        # 1. Setup Worker Thread (Chạy ngầm)
        self.worker_thread = QThread()
        self.ocr_worker = OCRWorker()
        self.ocr_worker.moveToThread(self.worker_thread)
        
        # Kết nối tín hiệu: Worker xong -> gọi hàm handle_ocr_result
        self.ocr_worker.finished_signal.connect(self.handle_ocr_result)
        
        self.worker_thread.start()

        # 2. Setup Giao diện Events
        # Khi drop file -> gọi logic xử lý input
        self.signal_files_dropped.connect(self.handle_new_files)
        # Khi click vào list -> hiển thị ảnh
        self.list_widget.itemClicked.connect(self.on_item_clicked)

    def handle_new_files(self, file_paths):
        """Logic khi có file mới được thả vào"""
        for path in file_paths:
            file_name = os.path.basename(path)
            
            # Thêm vào giao diện list
            self.add_item_to_list(path, file_name)
            
            # Đẩy việc cho worker xử lý (Sử dụng QMetaObject để an toàn thread)
            # Lưu ý: Ở đây ta gọi trực tiếp hàm process_image vì demo đơn giản. 
            # Trong thực tế nên dùng signal để kích hoạt worker.
            # Dưới đây là cách gọi an toàn qua lambda để đẩy task vào hàng đợi thread
            self.process_request(path)

    def process_request(self, path):
        """Gửi yêu cầu tới thread OCR"""
        # Gọi hàm process_image trong ngữ cảnh của worker_thread
        # Lưu ý: Đây là trick để chạy hàm trong thread khác mà không cần emit signal phức tạp
        from PyQt5.QtCore import QMetaObject, Q_ARG
        QMetaObject.invokeMethod(self.ocr_worker, "process_image", 
                                 Qt.QueuedConnection, 
                                 Q_ARG(str, path))

    def handle_ocr_result(self, file_path, text):
        """Logic khi OCR xong"""
        print(f"Xong file: {file_path}")
        # Cập nhật UI (View đã có hàm này)
        self.update_item_status(file_path, text)

    def on_item_clicked(self, item):
        """Logic khi user click vào 1 dòng"""
        path = item.data(Qt.UserRole)
        text = item.data(Qt.UserRole + 1)
        # Gọi View hiển thị
        self.show_selected_image(path, text)

    def closeEvent(self, event):
        """Dọn dẹp thread khi tắt app"""
        self.worker_thread.quit()
        self.worker_thread.wait()
        super().closeEvent(event)