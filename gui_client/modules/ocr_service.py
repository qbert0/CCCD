import os
import cv2
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

# Biến toàn cục giữ engine
GLOBAL_OCR_ENGINE = None

class OCRWorker(QObject):
    # Trả về (file_path, text_result)
    finished_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()

    def read_image_safe(self, path):
        """Đọc ảnh an toàn với đường dẫn tiếng Việt"""
        try:
            stream = open(path, "rb")
            bytes_data = bytearray(stream.read())
            numpy_array = np.asarray(bytes_data, dtype=np.uint8)
            img = cv2.imdecode(numpy_array, cv2.IMREAD_UNCHANGED)
            return img
        except Exception as e:
            return None

    def preprocess_image(self, img_array):
        """Tiền xử lý: Scale x2 -> Grayscale -> Convert lại BGR"""
        try:
            # 1. Chuyển sang ảnh xám để xử lý
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
            else:
                gray = img_array

            # 2. Phóng to ảnh (Upscale) x2 lần
            height, width = gray.shape
            if width < 2000: 
                gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

            # 3. Khử nhiễu
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
            
            # --- [FIX LỖI QUAN TRỌNG] ---
            # PaddleOCR bắt buộc đầu vào phải là 3 kênh (BGR).
            # Dù là ảnh đen trắng, ta vẫn phải convert lại sang format BGR.
            processed_img_3_channels = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            
            return processed_img_3_channels
            
        except Exception as e:
            print(f"Lỗi preprocess: {e}")
            return img_array # Nếu lỗi thì trả về ảnh gốc

    @pyqtSlot(str)
    def process_image(self, file_path):
        global GLOBAL_OCR_ENGINE
        
        final_result = ""
        error_msg = None

        try:
            # --- 1. KHỞI TẠO ---
            if GLOBAL_OCR_ENGINE is None:
                from paddleocr import PaddleOCR
                GLOBAL_OCR_ENGINE = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    det_limit_side_len=1280,
                    det_db_thresh=0.3,
                    lang = "vi",
                    use_textline_orientation=False
                )

            # --- 2. XỬ LÝ ẢNH ---
            safe_path = file_path.replace("\\", "/")
            if not os.path.exists(safe_path):
                error_msg = "Lỗi: Không tìm thấy file"
            else:
                print(f"--- Running Predict: {os.path.basename(safe_path)} ---")
                
                # Đọc ảnh
                original_img = self.read_image_safe(safe_path)
                input_data = safe_path 

                if original_img is not None:
                    # Tiền xử lý (đã fix lỗi 3 channels)
                    input_data = self.preprocess_image(original_img)
                else:
                    print("Không đọc được ảnh bằng OpenCV, dùng đường dẫn gốc.")
                
                # --- 3. GỌI OCR ---
                results = GLOBAL_OCR_ENGINE.predict(input=input_data)

                # --- 4. BÓC TÁCH KẾT QUẢ (Logic cũ của bạn) ---
                extracted_texts = []

                if isinstance(results, dict) and 'rec_texts' in results:
                    extracted_texts = results['rec_texts']
                
                elif isinstance(results, list):
                    for res in results:
                        if isinstance(res, dict) and 'rec_texts' in res:
                            extracted_texts.extend(res['rec_texts'])
                        elif isinstance(res, list): 
                            try:
                                extracted_texts.append(res[1][0])
                            except: pass

                if extracted_texts:
                    final_result = "\n".join(extracted_texts)
                else:
                    final_result = "Không đọc được nội dung (hoặc không có text)."

        except Exception as e:
            print(f"Lỗi Runtime OCR: {e}")
            error_msg = f"Lỗi: {str(e)}"

        # --- 5. TRẢ KẾT QUẢ ---
        if error_msg:
            self.finished_signal.emit(file_path, error_msg)
        else:
            self.finished_signal.emit(file_path, final_result)