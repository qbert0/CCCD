# Hướng dẫn dự án CCCD Report

CCCD Report là ứng dụng desktop Python/PyQt đọc mặt trước và mặt sau CCCD, cho phép người dùng kiểm tra dữ liệu rồi tạo bốn loại tài liệu DOCX/PDF. Phiên bản hiện tại chạy OCR offline và không cần Docker.

## 1. Cấu trúc ở thư mục gốc

```text
CCCD/
├── desktop_app/             # Toàn bộ mã nguồn ứng dụng hiện tại
├── runtime_models/          # Model PaddleOCR chạy offline
├── product/                 # Sản phẩm đã đóng gói để sử dụng
├── build/                   # File trung gian khi chạy PyInstaller
├── .venv-desktop/           # Môi trường Python phát triển/build
├── .uv-cache/               # Cache các package do uv tải về
├── README.md                # Giới thiệu và lệnh chạy nhanh
└── DESKTOP_APP_GUIDE.md     # Tài liệu chi tiết này
```

Không còn thư mục `legacy/`. GUI cũ, Docker backend cũ, project OCR cũ và môi trường `.venv-ocr/` đã được xóa hoàn toàn.

### `desktop_app/`

Đây là mã nguồn duy nhất cần quan tâm khi phát triển tính năng. Mọi thay đổi giao diện, OCR, validation hoặc cách sinh tài liệu đều thực hiện tại đây.

### `runtime_models/`

```text
runtime_models/paddle/
├── det/                     # Phát hiện vị trí dòng chữ
├── cls/                     # Xác định chiều của dòng chữ
└── rec/                     # Nhận dạng vùng ảnh thành văn bản
```

Không sửa tên hoặc di chuyển ba thư mục model nếu chưa cập nhật `backend/ocr/config.py`. Model này được đưa vào `product/` trong quá trình build.

### `product/`

```text
product/CCCDReport/
├── CCCDReport               # File chạy ứng dụng trên Linux
└── _internal/               # Python, thư viện, model và file mẫu đã đóng gói
```

Không chỉnh sửa mã hoặc biểu mẫu trực tiếp trong `_internal/`, vì chúng sẽ bị ghi đè ở lần build tiếp theo. Hãy sửa trong `desktop_app/`, sau đó chạy `desktop_app/build.sh`.

### `build/`

Chứa file trung gian của PyInstaller. Có thể xóa và tạo lại; đây không phải mã nguồn và không phải sản phẩm giao cho người dùng.

### `.venv-desktop/`

Chứa Python 3.11 và toàn bộ thư viện dùng để chạy, kiểm thử và đóng gói. Nếu xóa, chạy lại `desktop_app/install.sh` để cài môi trường.

### `.uv-cache/`

Chỉ là cache tải package. Có thể xóa để giải phóng dung lượng, nhưng lần cài sau sẽ phải tải lại thư viện.

## 2. Cấu trúc `desktop_app/`

```text
desktop_app/
├── frontend/                # Giao diện người dùng
├── backend/                 # OCR, validation và sinh tài liệu
├── data/                    # Dữ liệu nguồn và output phát triển
├── tests/                   # Kiểm thử tự động
├── assets/                  # Icon của ứng dụng
├── main.py                  # Điểm khởi động
├── requirements.txt         # Danh sách thư viện Python
├── CCCDReportApp.spec       # Cấu hình đóng gói PyInstaller
├── install.sh               # Cài môi trường phát triển
├── run.sh                   # Chạy từ mã nguồn
├── build.sh                 # Tạo sản phẩm trong product/
├── install_product.sh       # Đăng ký ứng dụng vào menu hệ điều hành
└── cccd-report.desktop      # Cấu hình launcher Linux
```

## 3. Frontend

Frontend được tổ chức theo hướng tương tự Nuxt: có trang, tab, giao diện riêng theo tài liệu và component dùng chung.

```text
frontend/
├── pages/
│   └── home_page.py
├── tabs/
│   ├── identity_tab.py
│   └── document_tab.py
├── documents/
│   ├── base.py
│   ├── transfer_form.py
│   ├── aftersale_form.py
│   ├── beautiful_number_form.py
│   └── prepaid_contract_form.py
├── components/
│   ├── field_input.py
│   ├── person_form.py
│   ├── image_upload_card.py
│   ├── action_bar.py
│   └── review_dialog.py
├── styles/
│   └── theme.py
└── baseDesign/
    ├── cursor.md            # Đặc tả Cursor dùng làm nguồn thiết kế
    └── DESIGN.md            # Design system đã áp dụng cho sản phẩm
```

### `frontend/pages/home_page.py`

Đây là trang duy nhất của ứng dụng. File này chịu trách nhiệm:

- Ghép các component và tab thành cửa sổ chính.
- Mở hộp thoại chọn ảnh.
- Chạy OCR trong thread riêng để giao diện không bị treo.
- Nhận kết quả OCR và điền vào form.
- Điều phối kiểm tra, xem trước, xuất file và mở file để in.

Không đặt thuật toán OCR hoặc code điền PDF/DOCX trong file này; các xử lý đó thuộc backend.

### `frontend/tabs/`

- `identity_tab.py`: khung tab thông tin một người; được tái sử dụng cho chủ hiện tại và chủ mới.
- `document_tab.py`: các trường chung của tài liệu và khu vực hiển thị form riêng theo loại tài liệu.

### `frontend/documents/`

Mỗi tài liệu có một form riêng:

- `transfer_form.py`: phần giao diện biên bản chuyển chủ quyền.
- `aftersale_form.py`: dịch vụ yêu cầu và điện thoại dự phòng.
- `beautiful_number_form.py`: thời gian và cước cam kết.
- `prepaid_contract_form.py`: sê-ri SIM, ngày hòa mạng và số hợp đồng.
- `base.py`: hành vi dùng chung cho các form tài liệu.

Khi bổ sung tài liệu thứ năm, cần tạo thêm một form trong thư mục này và đăng ký nó trong `tabs/document_tab.py`.

### `frontend/components/`

- `field_input.py`: ô nhập dùng chung, dấu `*`, viền đỏ và thông báo lỗi.
- `person_form.py`: toàn bộ trường CCCD của một người.
- `image_upload_card.py`: khung chọn, xem và hiển thị trạng thái ảnh hai mặt.
- `action_bar.py`: các nút Kiểm tra, Xem trước, Tạo tài liệu và Mở để in.
- `review_dialog.py`: cửa sổ xác nhận dữ liệu lần cuối.

Ví dụ, muốn thay cách hiển thị lỗi của tất cả form, chỉ sửa `components/field_input.py`. Muốn thêm một trường CCCD dùng chung, sửa danh sách `PERSON_FIELDS` trong `components/person_form.py` và model tương ứng ở backend.

### `frontend/styles/theme.py`

Chứa stylesheet dùng chung cho toàn bộ ứng dụng: màu sắc, font, input, button, tab, scrollbar và trạng thái lỗi. Thay đổi tại đây sẽ áp dụng đồng thời cho mọi giao diện.

`frontend/baseDesign/DESIGN.md` là bản đặc tả đã áp dụng từ `cursor.md`: nền kem ấm, chữ near-black, card trắng bo 12 px, input/nút bo 8 px, hairline không đổ bóng và Cursor Orange chỉ dành cho tên sản phẩm cùng hành động chính.

## 4. Backend

```text
backend/
├── domain/
│   └── models.py
├── validation/
│   └── rules.py
├── ocr/
│   ├── config.py
│   ├── service.py
│   ├── parser.py
│   └── engines/
│       ├── registry.py
│       ├── qr.py
│       ├── chandra.py
│       ├── paddle.py
│       └── tesseract.py
├── documents/
│   ├── base.py
│   ├── registry.py
│   ├── renderer.py
│   ├── transfer/
│   ├── aftersale/
│   ├── beautiful_number/
│   └── prepaid_contract/
└── paths.py
```

### `backend/domain/models.py`

Định nghĩa dữ liệu chuẩn được dùng giữa frontend và backend:

- `PersonData`: thông tin một người trên CCCD.
- `ReportData`: thông tin người, thuê bao, cửa hàng và tài liệu.
- `DocumentType`: định danh bốn loại tài liệu.
- `DOCUMENT_NAMES`: tên hiển thị của từng loại.

Khi thêm một trường mới, nên thêm vào model trước, sau đó cập nhật form, validation và module tài liệu cần sử dụng trường đó.

### Validation theo từng tài liệu

Không còn một schema tài liệu tập trung. Mỗi module sở hữu validation của chính nó, giống cách một schema Zod đi kèm feature:

```text
documents/transfer/schema.py
documents/aftersale/schema.py
documents/beautiful_number/schema.py
documents/prepaid_contract/schema.py
```

`backend/validation/rules.py` chỉ giữ các primitive thực sự dùng chung như `valid_date`, `valid_phone`, `person_errors`, `required_errors` và kiểu `FieldError`; file này không quyết định tài liệu nào bắt buộc trường nào. Schema trong từng module trả về đường dẫn trường và nội dung lỗi, ví dụ:

```text
customer.id_number -> CCCD/CMND phải gồm đúng 9 hoặc 12 chữ số
customer.issue_date -> Ngày cấp không thể trước ngày sinh
monthly_fee -> Cước cam kết tối thiểu là thông tin bắt buộc
```

Các schema hiện kiểm tra:

- Trường bắt buộc theo từng loại tài liệu.
- CCCD/CMND 9 hoặc 12 chữ số.
- Định dạng ngày `DD/MM/YYYY` và ngày có thực.
- Quan hệ ngày sinh, ngày cấp và ngày hết hạn.
- Độ dài số thuê bao và số điện thoại.
- Thông tin chủ mới khi chuyển chủ quyền.
- Thời gian/cước cam kết đối với số đẹp.

### `backend/ocr/`

`service.py` chỉ quản lý pipeline ảnh và phiên OCR:

1. Đọc ảnh Unicode bằng NumPy/OpenCV.
2. Tìm biên thẻ và hiệu chỉnh phối cảnh.
3. Gọi registry để chạy các engine theo thứ tự cấu hình.
4. Tự phân loại mặt trước, mặt sau hoặc chưa xác định.
5. Gộp QR mặt trước với OCR/MRZ mặt sau; ưu tiên QR cho dữ liệu định danh và dùng mặt sau để bổ sung ngày cấp, nơi cấp, ngày hết hạn.

Nếu một ảnh lỗi nhưng ảnh còn lại đọc được, kết quả thành công vẫn được giữ và ảnh lỗi có cảnh báo riêng.

Mỗi ảnh cũng mang theo vị trí người dùng đã chọn (`MẶT TRƯỚC` hoặc `MẶT SAU`). Nếu OCR xác định ảnh không đúng vị trí, khung ảnh chuyển đỏ, ứng dụng báo rõ mặt nhận dạng được, không gộp dữ liệu từ ảnh sai và chặn kiểm tra/xem trước/tạo tài liệu cho đến khi ảnh được thay đúng.

`ocr/engines/registry.py` là nơi duy nhất đăng ký và sắp xếp toàn bộ model:

1. `qr.py`: ZXing-C++ rồi OpenCV, đọc QR mặt trước.
2. `chandra.py`: Chandra OCR 2 thông qua API khi có `CCCD_OCR_API_URL`.
3. `paddle.py`: tự xoay đúng chiều cả khung ảnh (0/90/180/270°, xem `PaddleEngine._correct_orientation`) rồi dò khung chữ bằng PaddleOCR (det+cls, không phụ thuộc ngôn ngữ), nhưng bước *đọc ký tự* dùng VietOCR thay vì bộ nhận dạng "vi" gốc của PaddleOCR — bộ đó thực chất dùng chung dictionary "latin" (185 ký tự, cho tiếng Pháp/Đức/Ba Lan...), không có ơ/ư và không có nguyên âm mang dấu thanh nào, nên trước đây gần như không đọc được tiếng Việt có dấu (xem `PaddleEngine`/`_VietOCRLineRecognizer` trong `paddle.py`). PaddleOCR vẫn lo việc dò khung + cắt dòng + chỉnh góc; VietOCR chỉ nhận input là ảnh dòng chữ đã cắt sẵn.
4. `tesseract.py`: fallback cuối, tự dùng `vie+eng` nếu máy có gói tiếng Việt.

Thứ tự mặc định là `qr,chandra,paddle,tesseract`. Có thể đổi bằng `CCCD_OCR_ENGINE_ORDER`; model Paddle bằng `CCCD_PADDLE_MODEL_DIR`; ngưỡng nhận dạng bằng `CCCD_PADDLE_CONFIDENCE`; trọng số/cấu hình VietOCR bằng `CCCD_VIETOCR_WEIGHTS`/`CCCD_VIETOCR_CONFIG` (mặc định `runtime_models/vietocr/`). Giao diện hiển thị các engine thực sự sẵn sàng trên máy. Trọng số VietOCR (~150MB) vượt giới hạn 100MB của một blob Git nên không commit trực tiếp như model Paddle — `install.sh`/`build.sh` tự tải về `runtime_models/vietocr/vgg_transformer.pth` trong lần cài đầu tiên (xem `.gitignore`).

Mặt sau không chỉ được đọc bằng ZXing/OpenCV. PaddleOCR dò khung + VietOCR đọc chữ tiếng Việt, parser đọc ba dòng MRZ, và bộ hậu xử lý phục hồi các nhãn ổn định như “Ngày, tháng, năm”, “Đặc điểm nhận dạng”, “Ngón trỏ trái/phải”. MRZ vốn theo chuẩn ASCII nên tên trong riêng ba dòng MRZ không có dấu; dữ liệu họ tên có dấu vẫn lấy từ QR mặt trước.

VietOCR chạy tuần tự trên CPU (~0.5-1s mỗi dòng chữ) nên một ảnh nhiều dòng (mặt trước CCCD ~20 dòng) tốn khoảng 15-25s thay vì 1-5s như bộ nhận dạng PaddleOCR gốc — đánh đổi tốc độ lấy độ chính xác tiếng Việt.

Trước khi có `_correct_orientation`, một ảnh chụp lệch ~90° (điện thoại không cầm ngang) vẫn qua được `normalize_card()` (hàm này chỉ chỉnh phối cảnh + kiểm tra thô ngang/dọc) mà không được xoay đúng chiều — PaddleOCR's `cls` khi đó chỉ chỉnh được *từng dòng chữ* cho dễ đọc, còn *thứ tự* các dòng (sắp theo toạ độ điểm ảnh gốc, xảy ra trước cls) thì vẫn sai, khiến parser thấy giá trị đứng trước nhãn hoặc có dòng đọc ngược hẳn — không liên quan gì đến watermark như một ghi chú cũ ở đây từng nói nhầm. `_correct_orientation` xoay lại cả khung ảnh trước khi OCR nên vấn đề này đã được xử lý ở gốc.

### `backend/ocr/parser.py`

Chuyển QR hoặc văn bản OCR thành các trường chuẩn:

- Số CCCD và CMND cũ.
- Họ tên, ngày sinh, giới tính, quốc tịch.
- Quê quán và địa chỉ thường trú.
- Ngày cấp, nơi cấp và ngày hết hạn.
- Dòng MRZ ở mặt sau.

### `backend/documents/`

- `base.py`: vòng đời dùng chung `check()`, `preview()`, `generate()` và `print_document()`.
- `registry.py`: ánh xạ `DocumentType` sang đúng module.
- `renderer.py`: fill placeholder trong DOCX mà không làm phẳng định dạng các `run`, hoặc chèn lớp dữ liệu Unicode lên PDF.

### Placeholder trong mẫu Word

Ba mẫu Word trong `documents/transfer/`, `documents/aftersale/` và `documents/prepaid_contract/` dùng token có dạng `{{ customer_name }}`, `{{ customer_id_number }}` và `{{ subscriber_number }}`. Có thể mở file DOCX bằng Word hoặc LibreOffice để sửa bố cục, font, cỡ chữ, căn lề và nội dung cố định. Không đổi tên hoặc xóa token nếu trường đó vẫn cần xuất hiện trong tài liệu.

Riêng biên bản chuyển quyền, file thiết kế người dùng chỉnh sửa là `documents/transfer/Biên bản chuyển chủ quyền 2025.docx`. Hàm `migrate_transfer()` trong `scripts/migrate_docx_placeholders.py` chỉ đổi tên token theo ngữ nghĩa rồi xuất thành `documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx`; không dựng lại hoặc thay bố cục thiết kế.

Renderer chỉ thay phần token ngay trong `run` chứa nó nên không còn thay tên giả, số CCCD giả hay viết lại toàn bộ đoạn văn như cơ chế cũ. Nếu Word tự chia một token thành nhiều `run`, renderer vẫn ghép và nhận diện được. Token sai tên hoặc chưa được fill sẽ làm quá trình tạo tài liệu báo lỗi thay vì âm thầm xuất ra một tài liệu thiếu dữ liệu.

Mỗi module DOCX khai báo danh sách placeholder bắt buộc ngay trong `module.py`. Trước khi tạo file, ứng dụng đối chiếu danh sách này với token thực tế trong mẫu. Vì vậy, nếu sửa mẫu Word và vô tình xóa hoặc viết sai một token, ứng dụng báo rõ token thiếu/sai thay vì tạo tài liệu nhìn có vẻ hoàn chỉnh nhưng mất trường dữ liệu.

Định dạng đầu ra đã được kiểm tra với dữ liệu đầy đủ:

- `transfer`: 2 trang, hỗ trợ cả Bên A/Bên C là cá nhân hoặc tổ chức.
- `aftersale`: 1 trang A4; chỉ nội dung của dịch vụ được chọn nhận dữ liệu, ba cột chữ ký được giữ nguyên.
- `prepaid_contract`: 2 trang; tự điền đúng khu vực cá nhân hoặc tổ chức và bảng thuê bao/SIM/hòa mạng.

Mẫu `beautiful_number/*.pdf` là PDF nền, không phải Word và không có trường form. Nó tiếp tục được fill bằng lớp chữ theo tọa độ trong `renderer.py`; thay bố cục PDF có thể yêu cầu cập nhật lại tọa độ.

Bốn module tài liệu:

```text
documents/transfer/
├── 00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx
├── schema.py
└── module.py

documents/aftersale/
├── 00_MAU_CAM_KET_SAU_BAN_HANG.docx
├── schema.py
└── module.py

documents/beautiful_number/
├── 00_MAU_PHU_LUC_CAM_KET_SO_DEP.pdf
├── schema.py
└── module.py

documents/prepaid_contract/
├── 00_MAU_HOP_DONG_TRA_TRUOC.pdf
├── schema.py
└── module.py
```

File mẫu có tiền tố `00_MAU_` để luôn nằm đầu thư mục. Muốn đổi nội dung hoặc bố cục mẫu:

1. Thay file `00_MAU_...` nhưng giữ nguyên tên; hoặc
2. Đổi tên file rồi cập nhật thuộc tính `template` trong `module.py` cùng thư mục.

Sau khi thay mẫu PDF, có thể cần điều chỉnh tọa độ điền dữ liệu trong `documents/renderer.py`.

### Bốn tài liệu và dữ liệu đã đối chiếu từ mẫu gốc

1. **Biên bản chuyển quyền sử dụng dịch vụ thông tin di động mặt đất và thanh lý hợp đồng**: ngày lập, hình thức thanh toán, số/ngày hợp đồng hoặc ngày Phiếu đăng ký dịch vụ, giờ/ngày chuyển quyền có hiệu lực, số thuê bao; thông tin Bên A và Bên C gồm cá nhân/tổ chức, trụ sở, đăng ký doanh nghiệp, đại diện/ủy quyền, CCCD, ngày/nơi cấp, ngày sinh, địa chỉ và quốc tịch.
2. **Giấy cam kết – Dành cho các giao dịch sau bán hàng**: ngày, cửa hàng, địa chỉ/điện thoại cửa hàng, nhân viên; khách hàng, CCCD, ngày/nơi cấp, địa chỉ, điện thoại; giấy tờ kèm theo, giao dịch cập nhật/thay SIM/chuyển chủ, thuê bao, hai số phối hợp. Chỉ khi chọn “Chuyển chủ quyền” mới cần CCCD chủ mới.
3. **Phụ lục số 01 – Cam kết sử dụng sản phẩm số đẹp**: ngày, họ tên, CCCD, số thuê bao, thời gian cam kết, cước tối thiểu/tháng và ghi chú trong bảng sản phẩm.
4. **Hợp đồng cung cấp và sử dụng dịch vụ thông tin di động mặt đất Vietnamobile – Hình thức thanh toán trả trước**: số hợp đồng/mã thuê bao; thông tin cá nhân hoặc tổ chức. Tổ chức có riêng số và nơi/ngày cấp giấy đăng ký, người đại diện, chức vụ, giấy ủy quyền và CCCD người đại diện. Ngoài ra có điểm cung cấp dịch vụ, nhân viên, địa chỉ/điện thoại điểm giao dịch, thời gian đăng ký, số thuê bao, sê-ri SIM và ngày hòa mạng.

### `backend/paths.py`

Giải quyết đường dẫn ở hai chế độ:

- Chạy trực tiếp từ mã nguồn.
- Chạy từ binary PyInstaller.

File này cũng xác định thư mục output mặc định của người dùng.

## 5. Dữ liệu

```text
data/
├── source/
│   ├── original_documents/        # Dữ liệu gốc do người dùng cung cấp
│   └── samples/                   # Ảnh CCCD dùng cho self-test
└── output/
    └── .gitkeep
```

- `source/` được xem là dữ liệu đầu vào, không ghi đè khi tạo báo cáo.
- `samples/cccd_front.jpg` và `samples/cccd_back.jpg` giúp kiểm tra QR, PaddleOCR và phân loại hai mặt sau mỗi lần build.
- `output/` dành cho output khi phát triển. Khi sử dụng giao diện, người dùng được chọn thư mục lưu riêng.
- `.gitkeep` giữ thư mục `output/` tồn tại trong Git dù chưa có file kết quả.

## 6. Tests

`desktop_app/tests/` kiểm tra:

- Sinh đủ bốn loại tài liệu.
- Nội dung DOCX/PDF sau khi điền.
- Parse QR và MRZ.
- Nhận diện mặt trước/mặt sau.
- Không bỏ qua mặt sau khi mặt trước có QR.
- Giữ dữ liệu khi chỉ một mặt đọc thành công.
- Validation CCCD, ngày và điện thoại.
- Hiển thị lỗi ngay dưới input trên giao diện.
- Schema bắt buộc riêng của từng tài liệu.
- Trạng thái nạp ảnh trước, chưa chọn tài liệu và giữ dữ liệu khi đổi mẫu.
- Khôi phục nhãn tiếng Việt trên mặt sau.
- Tự đưa ảnh vào khung xem mặt trước hoặc mặt sau; ảnh mới cùng mặt thay ảnh cũ.
- So sánh họ tên và số định danh đọc được từ hai mặt, cảnh báo đỏ nếu có nguy cơ không cùng CCCD.

Chạy toàn bộ test:

```bash
QT_QPA_PLATFORM=offscreen \
  .venv-desktop/bin/python -m unittest discover -s desktop_app/tests -v
```

Chạy self-test OCR thật và sinh tài liệu:

```bash
QT_QPA_PLATFORM=offscreen \
  .venv-desktop/bin/python -m desktop_app.main --self-test-full
```

Kiểm tra trực tiếp bản đã đóng gói:

```bash
QT_QPA_PLATFORM=offscreen \
  ./product/CCCDReport/CCCDReport --self-test-full
```

## 7. Chạy, build và cài ứng dụng

Cài môi trường:

```bash
./desktop_app/install.sh
```

Chạy từ mã nguồn:

```bash
./desktop_app/run.sh
```

Đóng gói lại sản phẩm:

```bash
./desktop_app/build.sh
```

Cài hoặc cập nhật launcher trong menu ứng dụng:

```bash
./desktop_app/install_product.sh
```

## 8. Quy trình sử dụng

 1. Chọn hoặc kéo một ảnh vào vùng **Thả một ảnh CCCD vào đây**; không cần chọn trước đó là mặt nào.
 2. Ứng dụng tự nhận biết và đưa ảnh vào khung xem **Mặt trước** hoặc **Mặt sau**. Lặp lại để nạp mặt còn lại.
 3. Chọn một trong bốn mẫu tài liệu. Ảnh và dữ liệu OCR vẫn được giữ khi đổi mẫu.
 4. Riêng mẫu **Chuyển quyền & thanh lý hợp đồng**, vùng ảnh chính là CCCD của **Bên C / chủ thuê bao mới**. Bên A được tự điền từ hồ sơ cục bộ nên mẫu này không hiện vùng tải ảnh thứ hai.
 5. Nhấn **Thông tin mặc định Bên A** trên thanh đầu trang để cập nhật hồ sơ doanh nghiệp dùng chung. Dữ liệu được lưu trên máy và tự áp dụng cho mọi hồ sơ chuyển quyền sau đó.
 6. Bổ sung các ô có dấu `*` của riêng tài liệu đang chọn.
 7. Nhấn **Kiểm tra thông tin**, **Xem trước** hoặc **Tạo tài liệu**.
 8. Sửa các ô có thông báo màu đỏ ngay bên dưới, nếu có.
 9. Xác nhận thông tin tại cửa sổ kiểm tra cuối.
10. Lưu DOCX/PDF, đổi sang mẫu khác để tạo tiếp nếu cần, rồi chọn **Mở để in**.

### Hồ sơ mặc định Bên A của biên bản chuyển quyền

Ứng dụng có một hồ sơ cục bộ riêng cho Bên A, ban đầu chỉ là chỗ trống gợi ý ("Tên công ty của bạn"...) — mỗi cửa hàng cài đặt ứng dụng tự điền thông tin thật của mình vào **Thông tin mặc định Bên A**. Hồ sơ này vẫn xuất hiện đầy đủ trong tab **Chủ hiện tại (Bên A)** để người dùng kiểm tra trước khi tạo tài liệu.

Nút **Thông tin mặc định Bên A** mở trang chỉnh sửa riêng. Khi lưu, thông tin mới được ghi bằng `QSettings` của hệ điều hành, không sửa mẫu DOCX và không bị xóa khi nhấn **Hồ sơ mới**. Việc thay đổi có hiệu lực ngay trên hồ sơ chuyển quyền đang mở và cho các lần chạy ứng dụng tiếp theo.

### Làm liên tục nhiều hồ sơ

Sau khi hoàn thành một khách hàng, nhấn **Hồ sơ mới** ở góc dưới trái hoặc dùng `Ctrl+N`. Ứng dụng sẽ:

- Xóa ảnh hai mặt của người đang xử lý; với biên bản chuyển quyền đây là ảnh của Bên C.
- Xóa kết quả OCR, lỗi sai mặt và toàn bộ dữ liệu định danh.
- Xóa số thuê bao cùng dữ liệu giao dịch của bốn biểu mẫu.
- Vô hiệu hóa file đã tạo trước đó để tránh mở/in nhầm.
- Giữ nguyên loại biểu mẫu đang chọn, hồ sơ mặc định Bên A, tên/địa chỉ/điện thoại cửa hàng và nhân viên giao dịch.

Khi nạp ảnh mới, OCR tự xác định mặt. Nếu khung xem đã có ảnh cùng mặt, ảnh mới sẽ **thay đúng ảnh cùng mặt đó**; mặt còn lại được giữ. Khung xem chỉ giữ tối đa hai ảnh. Khi có đủ hai mặt, ứng dụng so sánh họ tên và số định danh đọc được; dữ liệu khác nhau sẽ tạo cảnh báo đỏ về nguy cơ ảnh không hợp lệ.

Thay ảnh không xóa số thuê bao hay các trường nghiệp vụ, vì thao tác này còn được dùng để thay một ảnh mờ trong cùng hồ sơ. Khi chuyển sang khách hàng khác vẫn nên dùng **Hồ sơ mới** để không mang dữ liệu giao dịch của khách trước sang khách sau.

Ảnh được xử lý hoàn toàn trên máy khi không đặt `CCCD_OCR_API_URL`. Nhật ký lỗi kỹ thuật nằm tại `/tmp/CCCDReport.log`.