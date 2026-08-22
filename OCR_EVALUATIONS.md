# Đánh giá các nguồn OCR bên ngoài

Nhật ký các thư viện/model OCR bên thứ ba đã được xem xét để đọc CCCD, cùng lý do chấp nhận hoặc từ chối. Mục đích: tránh phải điều tra lại từ đầu nếu sau này có ai đề xuất lại cùng một nguồn.

## 2026-08-13 — `ntvuongg/vnese-id-extractor` (v1 và v2)

**Đề xuất:** dùng làm engine đọc CCCD thay thế/bổ sung cho pipeline hiện tại (QR + PaddleOCR + Tesseract).

**Kết luận: Từ chối cả hai bản — không tích hợp.**

### Bản v1 (https://github.com/ntvuongg/vnese-id-extractor)

Loại ngay từ bước rà soát, chưa cần chạy thử:

- Không có file LICENSE — về pháp lý là "giữ toàn quyền", không có quyền sử dụng rõ ràng cho một app thương mại.
- README của chính tác giả ghi rõ **"không còn bảo trì"**, khuyên chuyển sang v2.
- Dùng TensorFlow 1.14 + Keras 2.3.0 (2019) — không cài được trên Python 3.11 hiện tại của `.venv-desktop`; cần dựng riêng một môi trường Python 3.7 cũ chỉ để chạy thư viện này.
- Weight model không nằm trong repo, phải tải qua Google Drive cá nhân của tác giả (không rõ nguồn/kiểm định).

### Bản v2 (https://github.com/ntvuongg/vnese-id-extractor-v2)

Vượt qua bước rà soát ban đầu (có LICENSE Apache 2.0, dùng PyTorch hiện đại, weight có sẵn trong repo ~130MB) nên đã thử nghiệm thực tế trong một venv riêng (`uv venv`, cài PyTorch bản CPU-only để tránh kéo theo hàng loạt gói CUDA không cần thiết), chạy trực tiếp trên `desktop_app/data/source/samples/cccd_front.jpg` và `cccd_back.jpg`.

**Vướng mắc kỹ thuật gặp phải khi setup (đã xử lý được, không phải lý do từ chối):**
- Gói `yolov5==7.0.14` dùng `pkg_resources` mà `setuptools` mới đã bỏ → phải ghim `setuptools<81`.
- Checkpoint `.pt` lưu theo định dạng cũ (đóng gói cả class model, không chỉ trọng số) nên bị PyTorch 2.6+ chặn bởi `weights_only=True` mặc định. Đã dùng `pickletools` để dò toàn bộ opcode `GLOBAL` trong pickle trước khi nạp — chỉ thấy các class chuẩn của `torch.nn.*` và kiến trúc YOLOv5 gốc (`models.yolo.Model`, `models.common.Conv/C3/SPPF`...), không có global đáng ngờ (`os.system`, `subprocess`, `eval`...) → an toàn để nạp với `weights_only=False` trong venv thử nghiệm.

**Lý do từ chối — kết quả thực nghiệm (lý do chính, quyết định):**

| Bước | Ảnh mặt trước (`cccd_front.jpg`) | Ảnh mặt sau (`cccd_back.jpg`) |
|---|---|---|
| Nhận diện 4 góc thẻ (`corner.pt`) | OK (đúng 4 góc) | **Fail** — phát hiện 6 vùng "góc" thay vì 4, không align được |
| Nhận diện field nội dung (`content.pt`) | **Fail** — chỉ nhận ra 1/9+ field bắt buộc (tên, số CCCD, ngày sinh, quê quán...) | Không tới bước này |

→ Model rõ ràng được train trên một **định dạng thẻ khác** với CCCD gắn chip (có QR) hiện dùng — nhiều khả năng CMND/CCCD đời cũ, phổ biến trong các bộ dữ liệu đồ án sinh viên (repo có logo UIT). Muốn dùng được sẽ phải train lại từ đầu trên dữ liệu CCCD hiện hành, không phải việc "tích hợp thư viện có sẵn".

**Rủi ro/chi phí khác nếu vẫn cố tích hợp (không còn liên quan sau khi đã có kết quả thực nghiệm âm, nhưng ghi lại để tham khảo):**
- Output không có tên field, chỉ là danh sách text theo thứ tự vị trí — không có file ánh xạ class→tên field nào trong repo, phải tự dò.
- Kiến trúc gốc là một app web FastAPI đầy đủ (kèm SQLite feedback form, trang liên hệ...) — phải tách riêng phần lõi suy luận.
- Thêm ~130MB weight + một stack phụ thuộc nặng (torch, torchvision, yolov5, ultralytics, vietocr, fastapi...) trong khi pipeline hiện tại (PaddleOCR) đã nhẹ và hoạt động tốt.

**Quyết định:** Giữ nguyên pipeline hiện tại — QR (`qr.py`) → Chandra API (tùy chọn) → PaddleOCR offline (`paddle.py`, đã tinh chỉnh riêng cho CCCD tiếng Việt) → Tesseract (fallback). Pipeline này đã pass self-test chính xác trên đúng loại thẻ đang dùng.

**Nếu muốn cải thiện độ chính xác OCR trong tương lai**, hướng khả thi hơn là tinh chỉnh `backend/ocr/engines/paddle.py` / `backend/ocr/parser.py` hiện có, hoặc tìm một model được train riêng cho CCCD gắn chip đời mới — không phải quay lại hai repo này.

---

*Môi trường thử nghiệm (venv, repo đã clone, cache pip) đã được dọn sạch hoàn toàn sau khi đánh giá, không để lại dấu vết trong `.venv-desktop` hay `requirements.txt` của dự án.*
