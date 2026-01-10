import cv2
import numpy as np
from paddleocr import PaddleOCR
from ultralytics import YOLO
import os

# Khởi tạo các model (chỉ chạy 1 lần khi server start)
# Model YOLO để phát hiện vùng thẻ CCCD
try:
    model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'yolov8n.pt')
    yolo_model = YOLO(model_path)
except Exception as e:
    print(f"Lỗi tải model YOLO: {e}. Đảm bảo file yolov8n.pt đã có.")
    yolo_model = None

# Model PaddleOCR (tự động tải model tiếng Việt lần đầu chạy)
# use_angle_cls=True để tự xoay ảnh nghiêng
ocr_reader = PaddleOCR(use_angle_cls=True, lang='vi', show_log=False)

def run_pipeline(original_image_np, enhancer_func):
    """
    Quy trình: Phát hiện thẻ -> Cắt -> Làm nét -> Đọc chữ
    """
    processed_image = original_image_np
    
    # BƯỚC 1: Dùng YOLO phát hiện và cắt vùng thẻ CCCD (Nếu có model)
    if yolo_model:
        results = yolo_model(original_image_np, verbose=False)
        for r in results:
            boxes = r.boxes
            for box in boxes:
                # Giả sử class 0 là đối tượng cần tìm (hoặc lọc theo tên class nếu train riêng)
                # Ở đây dùng model pre-train, nó sẽ detect nhiều thứ, 
                # ta lấy box có độ tin cậy cao nhất và diện tích lớn nhất làm thẻ.
                # *Lưu ý*: Để chính xác nhất, bạn nên train lại YOLO chỉ để detect CCCD.
                # Đoạn code này giả định box đầu tiên là thẻ để đơn giản hóa.
                x1, y1, x2, y2 = box.xyxy[0]
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                
                # Cắt vùng ảnh chứa thẻ
                cropped_card = original_image_np[y1:y2, x1:x2]
                if cropped_card.size > 0:
                    processed_image = cropped_card
                break # Chỉ lấy 1 đối tượng

    # BƯỚC 2: Làm nét ảnh đã cắt
    enhanced_image = enhancer_func(processed_image)
    
    # BƯỚC 3: Đưa vào PaddleOCR để đọc
    result = ocr_reader.ocr(enhanced_image, cls=True)
    
    extracted_texts = []
    if result and result[0]:
        for line in result[0]:
            text = line[1][0]
            confidence = line[1][1]
            # Chỉ lấy kết quả có độ tin cậy > 70% để giảm nhiễu
            if confidence > 0.7:
                extracted_texts.append(text)
                
    return extracted_texts