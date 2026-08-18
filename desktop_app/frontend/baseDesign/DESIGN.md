# CCCD Report — Cursor-inspired desktop design

## Visual direction

Giao diện dùng nền kem ấm `#f7f7f4`, chữ near-black `#26251e` và card trắng. Chiều sâu chỉ được tạo bằng hairline 1px; không dùng gradient hoặc đổ bóng. Cursor Orange `#f54e00` chỉ dành cho tên sản phẩm và hành động chính “Tạo tài liệu”.

## Typography

- Inter là font thay thế cho CursorGothic.
- Tiêu đề lớn giữ weight 400; tiêu đề component dùng 600.
- Văn bản OCR dùng JetBrains Mono hoặc monospace fallback.
- Label 12px, input và nội dung 14px, tiêu đề nhóm 18px.

## Components

- Card: nền trắng, viền `#e6e5e0`, radius 12px, không shadow.
- Input: cao tối thiểu 40px, radius 8px, viền `#cfcdc4`.
- Nút: radius 8px. Nút chính màu cam; nút mở/in dùng nền ink; nút phụ trắng.
- Validation: `#cf2d56`, hiển thị dưới đúng input.
- Tab: compact, selected dùng nền ink và chữ kem.
- Drop zone: một vùng nạp ảnh chung, radius 8px, nền `#fafaf7`; OCR tự phân loại vào tối đa hai khung xem trước/sau.

## Layout

- Header phẳng cao khoảng 52–64px, không hiển thị tiến trình hoặc đánh số thao tác.
- Workspace chia hai cột: CCCD/OCR bên trái, biểu mẫu bên phải.
- Các ô form reflow thành lưới hai cột liên tục; trường ẩn không để lại khoảng trống.
- Khung ảnh ưu tiên chiều ngang và giảm chiều cao để dành không gian cho form.
- Khi cần bên thứ hai, card CCCD bổ sung xuất hiện trong cùng cột trái.
- Cột trái nằm trong `QScrollArea` để không bị bó hẹp trên màn hình thấp khi có đủ 2 card CCCD.

## Tương tác và trạng thái

- Mọi input, nút, tab, checkbox và khung thả ảnh đều có trạng thái `:hover` riêng để phản hồi ngay khi rê chuột, trước khi bấm.
- Khung thả ảnh (`#imageDropZone`) bấm được trực tiếp để mở hộp thoại chọn file, không chỉ kéo-thả; con trỏ chuột đổi thành hình bàn tay.
- Icon mũi tên combobox và dấu tick checkbox là ảnh PNG nhỏ trong `desktop_app/assets/` (`chevron-down.png`, `checkmark.png`), nạp qua `backend/paths.resource_path()` nên hoạt động cả khi chạy từ mã nguồn lẫn bản đóng gói PyInstaller. Fusion style của Qt ẩn mũi tên native nếu `QComboBox::drop-down` bị tùy biến mà không có `image`, nên hai icon này là bắt buộc, không phải trang trí thêm.
- Panel "Kết quả OCR" thu gọn mặc định (nút dạng text link `#disclosureButton`, không viền, không nền) để nhường chỗ cho luồng chính; tự mở khi có kết quả OCR mới.
- Nút phụ dạng "ghost" (`#refreshButton`, nền trong suốt, viền hairline) dùng cho hành động ít dùng nhưng cần tách khỏi cụm nút chính — ví dụ "↻ Hồ sơ mới" nằm riêng ở đầu action bar, cách cụm nút chính bằng `addStretch()`.
- Trạng thái lỗi dùng thống nhất một màu `#cf2d56` ở mọi nơi: viền input, khung ảnh sai mặt (`#imageDropZone[invalid="true"]`), badge trạng thái (`#uploadStatus[invalid="true"]`), dấu `*` bắt buộc và `#fieldError`. Không dùng thêm mã đỏ nào khác.
- Tiêu đề nhóm trong "Biểu mẫu tài liệu" phân hai cấp: `#sectionEyebrow` (11px, uppercase, tracking rộng, màu muted) đứng trước để giới thiệu nhóm, còn tiêu đề riêng của từng tài liệu vẫn dùng `#subsectionTitle` (14px/600/ink) — tránh hai dòng tiêu đề cùng trọng lượng thị giác đứng liền nhau.
- Empty state (chưa chọn biểu mẫu, chưa có ảnh) luôn có hai tầng: dòng tiêu đề đậm + dòng phụ màu muted giải thích bước tiếp theo, thay vì một dòng xám đơn độc.
- Hộp thoại xác nhận (`ReviewDialog`) map nút "Thông tin chính xác" → `#primaryButton` (cam) và "Quay lại chỉnh sửa" → `#secondaryButton` (trắng), để đường đi tiếp tục luôn nổi bật hơn đường quay lại.

## Nhịp độ "editorial calm" (2026-08-12)

Sau phản hồi giao diện còn "chật", đã tăng khoảng trắng và tầng bậc tiêu đề trên toàn ứng dụng thay vì chỉ sửa từng lỗi nhỏ:

- Input/combobox/textarea: padding `8px 11px` → `10px 13px`.
- Card chính (`#contentCard`, `#uploadCard`, `#ocrCard`): margin nội dung tăng lên `20–24px` (trước `14–18px`), spacing nội bộ tăng theo tỉ lệ tương ứng.
- Lưới field 2 cột (`person_form.py`, `document_tab.py`, `documents/base.py`): vertical spacing `5px` → `11px`, horizontal `12px` → `16px` — các hàng input không còn dính sát nhau.
- `#sectionTitle` (tiêu đề card) tăng `18px` → `19px`, letter-spacing `-0.15px`, gần với `{typography.display-sm}` của cursor.md hơn.
- Header trang và action bar cũng giãn margin/spacing theo cùng tỉ lệ.
- Bỏ dòng thông báo "Chưa có mặt CCCD nào được nhận diện" trùng lặp với gợi ý sẵn có trong khung thả ảnh — một card chỉ nói "chưa có ảnh" một lần, không nhắc lại 2-3 lần bằng các câu khác nhau.

**Lưu ý khi tăng font-size tiêu đề trong hàng ngang có thêm phần tử khác** (ví dụ tiêu đề card CCCD đứng cạnh badge trạng thái): phải `setWordWrap(True)` và cho tiêu đề stretch-factor 1, badge `stretch-factor 0` — nếu không, Qt sẽ cắt cụt (clip) chữ khi nội dung tiêu đề dài (như "CCCD Bên C · Chủ thuê bao mới") thay vì tự xuống dòng.
