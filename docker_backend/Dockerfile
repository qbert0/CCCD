# Sử dụng Python 3.10 slim để tối ưu dung lượng
FROM python:3.11-slim

# Đặt thư mục làm việc
WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết cho OpenCV chạy được
# (libgl1-mesa-glx và libgomp1 thường thiếu trong bản python slim)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements vài cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn backend vào container
COPY . .

# Tạo thư mục để PaddleOCR lưu model tải về (tránh lỗi quyền)
RUN mkdir -p /root/.paddleocr && chmod -R 777 /root/.paddleocr

# Mở cổng 8000 để giao tiếp với bên ngoài
EXPOSE 8000

# Lệnh chạy server API khi container khởi động
CMD ["uvicorn", "app_server:app", "--host", "0.0.0.0", "--port", "8000"]