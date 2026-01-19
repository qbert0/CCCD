import os

class ImageModel:
    def __init__(self, file_path):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        # Có thể thêm các thuộc tính khác sau này (ví dụ: kích thước, ngày chụp...)