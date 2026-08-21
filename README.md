# CCCD Report

Ứng dụng desktop Python nhận một thư mục hồ sơ đánh số, đọc CCCD và tạo trọn bộ JPG cho 5 dịch vụ chuyển quyền/thay SIM. Ứng dụng chạy trực tiếp trên máy, không cần Docker.

Đặc tả nguồn dữ liệu, trường bắt buộc và tổ hợp bốn loại tài liệu nằm tại [doc/DAC_TA_5_DICH_VU.md](doc/DAC_TA_5_DICH_VU.md). Quy trình BPMN đã thiết kế lại nằm tại [doc/diagram.bpmn](doc/diagram.bpmn).

## Cấu trúc dự án

```text
desktop_app/
├── frontend/                       # Giao diện theo cấu trúc kiểu Nuxt
│   ├── pages/web_home_page.py      # Cửa sổ QWebEngine của ứng dụng
│   ├── web/                         # Giao diện HTML/CSS/Vue gọn theo bộ hồ sơ
│   ├── web_bridge/                  # Cầu nối giao diện với OCR/tạo tài liệu
│   ├── tabs/                       # Giao diện QWidget cũ, giữ để tương thích
│   ├── documents/                  # Form QWidget cũ; Web UI không gọi trực tiếp
│   ├── components/                 # Các component QWidget tương thích cũ
│   ├── styles/theme.py             # Toàn bộ giao diện dùng chung
│   └── baseDesign/                 # apple.md, SKILL.md và DESIGN.md đã áp dụng
├── backend/
│   ├── domain/models.py            # Kiểu dữ liệu nghiệp vụ
│   ├── validation/rules.py         # Primitive validation dùng chung
│   ├── ocr/engines/                # Registry QR/Chandra/Paddle/Tesseract
│   └── documents/                  # 4 module, mỗi module có schema.py riêng
│       ├── transfer/
│       ├── aftersale/
│       ├── beautiful_number/
│       └── prepaid_contract/
├── data/
│   ├── source/                     # Ảnh và tài liệu gốc, chỉ dùng làm nguồn
│   └── output/                     # Output khi phát triển
├── tests/
└── main.py                         # Điểm khởi động mỏng

product/CCCDReport/                 # Bản đã đóng gói cho Linux
runtime_models/paddle/              # Model OCR offline
```

Trong mỗi thư mục `backend/documents/<loại>/`, file mẫu có tiền tố `00_MAU_` để luôn xuất hiện đầu tiên và có thể tìm, thay thế dễ dàng.

Quy trình giao diện là **chọn folder hồ sơ + nhập bảng thuê bao theo thứ tự bất kỳ → chọn dịch vụ → rà soát các tab tối giản → tạo bộ JPG**. Không có bộ chọn hay form nhập theo từng tài liệu; các tài liệu đầu ra là chi tiết nội bộ do dịch vụ quyết định. Danh sách thuê bao là một bảng cố định và giống nhau cho cả năm dịch vụ.

- Dịch vụ tổ chức → cá nhân dùng ảnh 1–3 cho chủ mới; dịch vụ cá nhân → cá nhân dùng 1–3 cho chủ cũ và 4–6 cho chủ mới; thay SIM dùng 1–3 cho người yêu cầu.
- Ảnh tài liệu bắt đầu từ `7.jpg`.
- Tạo lại cùng hồ sơ thay toàn bộ kết quả cũ từ số 7; không nối thêm số mới.
- Tên công ty, người đại diện và hai giao dịch viên được lưu trong **Thiết lập mặc định**.

## Chạy và đóng gói

```bash
./desktop_app/install.sh
./desktop_app/run.sh
./desktop_app/build.sh
./desktop_app/install_product.sh
```

Kiểm thử:

```bash
QT_QPA_PLATFORM=offscreen .venv-desktop/bin/python -m unittest discover -s desktop_app/tests -v
QT_QPA_PLATFORM=offscreen .venv-desktop/bin/python -m desktop_app.main --self-test-full
```

Xem [DESKTOP_APP_GUIDE.md](DESKTOP_APP_GUIDE.md) để biết cách cài đặt/chạy và [doc/DAC_TA_5_DICH_VU.md](doc/DAC_TA_5_DICH_VU.md) để biết quy trình sử dụng hiện tại.
