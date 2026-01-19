from PyQt5.QtCore import QThread, pyqtSignal
from modules.image_model import ImageModel

class ImageLoaderWorker(QThread):
    # Tín hiệu gửi ra ngoài: Gửi về 1 đối tượng ImageModel
    image_loaded_signal = pyqtSignal(object)

    def __init__(self, file_urls):
        super().__init__()
        self.file_urls = file_urls

    def run(self):
        """Giả lập việc đọc và xử lý ảnh nặng"""
        for url in self.file_urls:
            # Chuyển đổi QUrl sang đường dẫn local
            local_path = url.toLocalFile()
            
            # Kiểm tra xem có phải file ảnh không (đơn giản)
            if local_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                # Tạo model
                img_model = ImageModel(local_path)
                
                # Gửi tín hiệu đã xong file này
                self.image_loaded_signal.emit(img_model)
                
                # Giả lập độ trễ (nếu xử lý ảnh nặng)
                self.msleep(50)