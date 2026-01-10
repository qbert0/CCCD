import cv2
import numpy as np

def enhance_image_for_ocr(image_np):
    """
    Nhận vào ảnh dạng numpy array, trả về ảnh đã được làm nét.
    """
    # 1. Chuyển sang ảnh xám
    gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
    
    # 2. Làm sắc nét ảnh (Unsharp Masking) để cứu ảnh mờ
    # Tạo một bản mờ
    gaussian = cv2.GaussianBlur(gray, (0, 0), 3.0)
    # Cộng ảnh gốc với hiệu của ảnh gốc và ảnh mờ
    unsharp_image = cv2.addWeighted(gray, 1.5, gaussian, -0.5, 0, gray)
    
    # 3. Tăng tương phản cục bộ (CLAHE) giúp chữ rõ hơn trên nền
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced_img = clahe.apply(unsharp_image)
    
    # PaddleOCR cần ảnh 3 kênh màu để xử lý tốt nhất
    enhanced_img_bgr = cv2.cvtColor(enhanced_img, cv2.COLOR_GRAY2BGR)
    
    return enhanced_img_bgr