import cv2
import numpy as np
import os
import sys

# --- FIX LỖI DLL WINDOWS ---
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE" 

from qrdet import QRDetector
from pyzbar.pyzbar import decode, ZBarSymbol
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QListWidget, QListWidgetItem, QTextEdit, QSplitter, QPushButton, QApplication)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QPixmap, QIcon, QImage

class ImagePageView(QWidget):
    signal_files_dropped = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        
        # --- KHỞI TẠO MODEL QRDET ---
        print("⏳ Đang khởi tạo QRDetector...")
        try:
            self.detector = QRDetector(model_size='s')
            print("✅ QRDetector sẵn sàng!")
        except Exception as e:
            print(f"❌ Lỗi khởi tạo detector: {e}")
            self.detector = None

        # --- Biến Camera ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_camera_frame)
        self.cap = None
        self.is_scanning = False
        
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        self.lbl_instruction = QLabel("📥 Kéo thả ảnh CCCD (Chế độ Deep Scan)")
        self.btn_scan = QPushButton("📷 Bật Camera")
        self.btn_scan.setCheckable(True)
        self.btn_scan.clicked.connect(self.toggle_camera)
        
        header_layout.addWidget(self.lbl_instruction)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_scan)
        main_layout.addLayout(header_layout)

        # Splitter
        main_splitter = QSplitter(Qt.Horizontal)

        # 1. List
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(50, 50))
        self.list_widget.setMinimumWidth(200)
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        main_splitter.addWidget(self.create_wrapper("1. Danh sách", self.list_widget))

        # 2. Viewer
        self.lbl_image_viewer = QLabel("Chưa chọn ảnh")
        self.lbl_image_viewer.setAlignment(Qt.AlignCenter)
        self.lbl_image_viewer.setStyleSheet("background: #2b2b2b; color: #aaa;")
        self.lbl_image_viewer.setScaledContents(True) 
        self.lbl_image_viewer.setMinimumSize(320, 240)
        main_splitter.addWidget(self.create_wrapper("2. Ảnh gốc", self.lbl_image_viewer))

        # 3. Kết quả (Chia dọc)
        right_splitter = QSplitter(Qt.Vertical)
        
        self.lbl_cropped_qr = QLabel("Vùng QR")
        self.lbl_cropped_qr.setAlignment(Qt.AlignCenter)
        self.lbl_cropped_qr.setStyleSheet("background: #444; color: #ccc; border: 1px solid #555;")
        self.lbl_cropped_qr.setScaledContents(True)
        self.lbl_cropped_qr.setMinimumHeight(150)
        right_splitter.addWidget(self.create_wrapper("3a. AI nhìn thấy", self.lbl_cropped_qr))

        self.txt_result = QTextEdit()
        right_splitter.addWidget(self.create_wrapper("3b. Dữ liệu đọc được", self.txt_result))

        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([200, 450, 350])
        right_splitter.setSizes([200, 400])

        main_layout.addWidget(main_splitter)
        self.setLayout(main_layout)

    def create_wrapper(self, title, widget):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #0078d7; font-weight: bold; margin-bottom: 3px;")
        layout.addWidget(lbl)
        layout.addWidget(widget)
        return container

    def convert_cv2_to_pixmap(self, cv_img):
        if cv_img is None or cv_img.size == 0: return QPixmap()
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        return QPixmap.fromImage(QImage(rgb_image.data, w, h, ch*w, QImage.Format_RGB888))

    # ========================================================
    # LOGIC XỬ LÝ ẢNH NÂNG CAO (DEEP SCAN)
    # ========================================================
    def scan_image_for_qr(self, file_path):
        if not self.detector: return "❌ Lỗi: Detector chưa sẵn sàng.", None

        # 1. Đọc ảnh (Unicode Safe)
        try:
            stream = open(file_path, "rb")
            bytes_arr = bytearray(stream.read())
            numpy_arr = np.asarray(bytes_arr, dtype=np.uint8)
            img = cv2.imdecode(numpy_arr, cv2.IMREAD_COLOR)
            stream.close()
        except Exception as e:
            return f"❌ Lỗi đọc file: {str(e)}", None

        if img is None: return "❌ File ảnh lỗi.", None

        # 2. AI Detect
        detections = self.detector.detect(image=img, is_bgr=True)
        
        if not detections:
            # Fallback: Nếu AI không bắt được, thử đọc toàn bộ ảnh bằng pyzbar (cơ hội cuối)
            print("⚠️ AI detect fail, thử quét toàn bộ ảnh...")
            decoded_fallback = self.force_decode_image(img)
            if decoded_fallback:
                 return self.parse_cccd_data(decoded_fallback), self.convert_cv2_to_pixmap(img)
            return "⚠️ AI không tìm thấy mã QR nào.", None

        # 3. Duyệt các kết quả detect
        for detection in detections:
            x1, y1, x2, y2 = detection['bbox_xyxy']
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            
            # --- CẢI TIẾN 1: PADDING RỘNG HƠN ---
            # QR Code cần vùng trắng xung quanh (Quiet Zone) để decode
            h_img, w_img = img.shape[:2]
            
            # Tính kích thước QR để padding theo tỷ lệ
            w_qr = x2 - x1
            h_qr = y2 - y1
            pad_x = int(w_qr * 0.2) # Padding 20% kích thước
            pad_y = int(h_qr * 0.2)

            x1_safe = max(0, x1 - pad_x)
            y1_safe = max(0, y1 - pad_y)
            x2_safe = min(w_img, x2 + pad_x)
            y2_safe = min(h_img, y2 + pad_y)

            cropped_qr = img[y1_safe:y2_safe, x1_safe:x2_safe]

            # --- CẢI TIẾN 2: THỬ GIẢI MÃ NHIỀU CÁCH ---
            # Thử đọc ảnh gốc cắt ra
            decoded_text = self.force_decode_image(cropped_qr)
            
            if decoded_text:
                return self.parse_cccd_data(decoded_text), self.convert_cv2_to_pixmap(cropped_qr)
            else:
                # Nếu cắt ra mà vẫn không đọc được -> Trả về ảnh đó để user biết AI đã bắt đúng chỗ
                # nhưng ảnh quá mờ/xấu
                return "⚠️ AI bắt được khung nhưng không đọc được chữ (Ảnh mờ/lóa).", self.convert_cv2_to_pixmap(cropped_qr)

        return "⚠️ Không tìm thấy QR hợp lệ.", None

    def force_decode_image(self, img_chunk):
        """
        Hàm này cố gắng 'cứu' ảnh bằng mọi giá để đọc ra chữ
        """
        # Cách 1: Đọc thô (Raw)
        decoded = decode(img_chunk, symbols=[ZBarSymbol.QRCODE])
        for obj in decoded:
            if "|" in obj.data.decode("utf-8"): return obj.data.decode("utf-8")

        # Cách 2: Chuyển xám (Grayscale)
        gray = cv2.cvtColor(img_chunk, cv2.COLOR_BGR2GRAY)
        decoded = decode(gray, symbols=[ZBarSymbol.QRCODE])
        for obj in decoded:
            if "|" in obj.data.decode("utf-8"): return obj.data.decode("utf-8")

        # Cách 3: Nhị phân hóa (Thresholding) - Trị ảnh bóng/lóa
        # Dùng Otsu's binarization tự động tìm ngưỡng tối ưu
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        decoded = decode(binary, symbols=[ZBarSymbol.QRCODE])
        for obj in decoded:
            if "|" in obj.data.decode("utf-8"): return obj.data.decode("utf-8")
            
        # Cách 4: Phóng to ảnh (Upscale) - Trị ảnh QR quá nhỏ
        # Nếu ảnh nhỏ hơn 100px, phóng to gấp đôi
        h, w = gray.shape
        if h < 150 or w < 150:
            zoomed = cv2.resize(gray, (w*2, h*2), interpolation=cv2.INTER_CUBIC)
            decoded = decode(zoomed, symbols=[ZBarSymbol.QRCODE])
            for obj in decoded:
                if "|" in obj.data.decode("utf-8"): return obj.data.decode("utf-8")

        return None

    # --- SỰ KIỆN CLICK ---
    def on_item_clicked(self, item):
        if self.is_scanning: self.stop_camera()
        file_path = item.data(Qt.UserRole)
        cached_data = item.data(Qt.UserRole + 1) 

        # Load ảnh gốc
        pixmap_full = QPixmap(file_path)
        if not pixmap_full.isNull():
            self.lbl_image_viewer.setPixmap(pixmap_full.scaled(
                self.lbl_image_viewer.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))

        if cached_data:
            self.txt_result.setText(cached_data.get("text", ""))
            crop_pixmap = cached_data.get("pixmap")
            if crop_pixmap:
                self.lbl_cropped_qr.setPixmap(crop_pixmap.scaled(
                    self.lbl_cropped_qr.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
            else:
                 self.lbl_cropped_qr.setText("Không có ảnh cắt")
        else:
            self.txt_result.setText("🧠 Đang dùng AI Deep Scan...")
            self.lbl_cropped_qr.setText("Đang phân tích...")
            self.txt_result.repaint()
            self.lbl_cropped_qr.repaint()
            
            result_text, crop_pixmap = self.scan_image_for_qr(file_path)
            
            item.setData(Qt.UserRole + 1, {"text": result_text, "pixmap": crop_pixmap})
            self.txt_result.setText(result_text)
            
            if crop_pixmap:
                 self.lbl_cropped_qr.setPixmap(crop_pixmap.scaled(
                    self.lbl_cropped_qr.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
            else:
                 self.lbl_cropped_qr.setText("Không detect được")

            if result_text and "Không tìm thấy" not in result_text and "Lỗi" not in result_text and "không đọc được" not in result_text:
                if not item.text().startswith("✅"):
                     item.setText(f"✅ {item.text()}")

    # --- UTILS ---
    def parse_cccd_data(self, raw):
        try:
            p = raw.split('|')
            if len(p) >= 6:
                return (f"🆔 Số: {p[0]}\n👤 Tên: {p[2]}\n🎂 Sinh: {self._fmt(p[3])}\n🏠 ĐC: {p[5]}")
            return raw
        except: return raw

    def _fmt(self, d):
        return f"{d[:2]}/{d[2:4]}/{d[4:]}" if len(d)==8 else d

    # --- CAMERA ---
    def toggle_camera(self):
        if self.btn_scan.isChecked():
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                self.btn_scan.setChecked(False); return
            self.is_scanning = True
            self.btn_scan.setText("🛑 Dừng Camera")
            self.lbl_image_viewer.clear()
            self.lbl_cropped_qr.clear()
            self.timer.start(30)
        else: self.stop_camera()

    def stop_camera(self):
        self.timer.stop()
        if self.cap: self.cap.release()
        self.is_scanning = False
        self.btn_scan.setChecked(False)
        self.btn_scan.setText("📷 Bật Camera")

    def update_camera_frame(self):
        if not self.cap: return
        ret, frame = self.cap.read()
        if not ret: return
        
        # Detect
        detections = self.detector.detect(image=frame, is_bgr=True)
        frame_vis = frame.copy()

        for detection in detections:
            x1, y1, x2, y2 = detection['bbox_xyxy']
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            cv2.rectangle(frame_vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Crop + Padding cho Camera
            pad = 20
            h, w = frame.shape[:2]
            cx1, cy1 = max(0, x1-pad), max(0, y1-pad)
            cx2, cy2 = min(w, x2+pad), min(h, y2+pad)
            
            crop_cv = frame[cy1:cy2, cx1:cx2]
            decoded_text = self.force_decode_image(crop_cv) # Dùng hàm force decode cho mạnh
            
            if decoded_text:
                self.txt_result.setText(self.parse_cccd_data(decoded_text))
                self.lbl_cropped_qr.setPixmap(self.convert_cv2_to_pixmap(crop_cv).scaled(
                        self.lbl_cropped_qr.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                ))
                self.stop_camera()
                return

        self.lbl_image_viewer.setPixmap(self.convert_cv2_to_pixmap(frame_vis).scaled(
             self.lbl_image_viewer.size(), Qt.KeepAspectRatio, Qt.FastTransformation
        ))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.accept()
        else: e.ignore()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        for p in paths:
            item = QListWidgetItem(QIcon(p), os.path.basename(p))
            item.setData(Qt.UserRole, p)
            item.setData(Qt.UserRole + 1, None) 
            self.list_widget.addItem(item)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImagePageView()
    window.setWindowTitle("Deep Scan QR Detection")
    window.resize(1200, 750)
    window.show()
    sys.exit(app.exec_())