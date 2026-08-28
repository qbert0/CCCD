# Đặc tả nghiệp vụ 5 dịch vụ và bộ tài liệu

## 1. Phạm vi và thuật ngữ

Một **bộ hồ sơ** là một thư mục ảnh được đánh số. Ứng dụng đọc hồ sơ, nhận dạng CCCD, cho người làm thủ tục bổ sung dữ liệu nghiệp vụ, tạo trọn bộ tài liệu của dịch vụ rồi lưu kết quả JPG trở lại thư mục.

Trong tài liệu này:

| Ký hiệu nguồn | Ý nghĩa |
| --- | --- |
| **FILE** | Người dùng bắt buộc cung cấp ảnh trong bộ hồ sơ. |
| **OCR** | Ứng dụng đọc từ ảnh CCCD; người dùng chỉ sửa khi OCR sai hoặc thiếu. |
| **COMPANY** | Nạp từ hồ sơ công ty/điểm giao dịch đã lưu một lần. |
| **REP** | Nạp từ hồ sơ người đại diện công ty đã lưu một lần. |
| **CLERK** | Nạp từ giao dịch viên được phân công cho dịch vụ; mỗi dịch vụ chỉ thuộc một người. |
| **SERVICE** | Giá trị cố định do loại dịch vụ quyết định. |
| **AUTO** | Ứng dụng tự tính, thường là ngày/giờ hiện tại hoặc số thứ tự file. |
| **INPUT** | Người dùng phải nhập cho từng bộ hồ sơ. |
| **OPTIONAL** | Không bắt buộc; được phép sửa hoặc để trống. |

Nếu một giá trị OCR/COMPANY/REP/CLERK không có hoặc không hợp lệ, giao diện phải cho sửa tay trước khi tạo. Mọi trường không được liệt kê là bắt buộc trong đặc tả này đều là **OPTIONAL** và có thể tùy chỉnh.

## 2. Quy ước thư mục hồ sơ

### 2.1. Ảnh đầu vào

| File | Nội dung | Dịch vụ áp dụng |
| --- | --- | --- |
| `1.jpg` | Mặt trước CCCD: chủ mới với dịch vụ tổ chức → cá nhân; chủ cũ với dịch vụ cá nhân → cá nhân; người yêu cầu với thay SIM | 1–5 |
| `2.jpg` | Mặt sau CCCD của đúng người tại vị trí 1 | 1–5 |
| `3.jpg` | Ảnh chân dung của đúng người tại vị trí 1 | 1–5 |
| `4.jpg` | Mặt trước CCCD của chủ mới | Chỉ dịch vụ cá nhân → cá nhân (2–3) |
| `5.jpg` | Mặt sau CCCD của chủ mới | Chỉ dịch vụ cá nhân → cá nhân (2–3) |
| `6.jpg` | Ảnh chân dung chủ mới | Chỉ dịch vụ cá nhân → cá nhân (2–3) |

Phần mở rộng đầu vào có thể là JPG/JPEG/PNG/BMP/WEBP, nhưng số đứng trước phần mở rộng là định danh của ảnh. Với dịch vụ 1 và 4, pháp nhân chủ cũ cùng người đại diện được nạp từ **Thiết lập mặc định**, nên ảnh 1–3 dành cho chủ mới và không cần ảnh 4–6.

### 2.2. Ảnh kết quả

- Tài liệu được tạo theo đúng thứ tự của tổ hợp dịch vụ và chuyển thành JPG liên tục từ `7.jpg`.
- Một tài liệu nhiều trang chiếm nhiều số liên tiếp. Vì vậy số lượng file kết quả có thể lớn hơn số lượng loại tài liệu.
- Khi tạo lại, toàn bộ kết quả cũ từ số 7 trở đi được **thay thế** bằng lần tạo mới; không nối thêm vào 12, 13, ...
- Hệ thống tạo và chuyển đổi trong vùng tạm trước. Chỉ khi toàn bộ lô thành công mới thay kết quả cũ, tránh bộ hồ sơ nửa mới nửa cũ.
- Nếu chọn thư mục kết quả khác, ứng dụng sao chép ảnh nguồn 1–6 cần thiết sang đó rồi ghi kết quả từ số 7.

## 3. Phân loại tài liệu

### 3.1. Biên bản chuyển quyền và thanh lý hợp đồng (`transfer`)

Mục đích: ghi nhận chủ hiện tại chuyển quyền sử dụng các số thuê bao cho chủ mới và xác định thời điểm chuyển quyền.

| Nhóm trường | Nguồn | Bắt buộc/nguyên tắc |
| --- | --- | --- |
| Chủ hiện tại là cá nhân: họ tên, CCCD, ngày/nơi cấp, ngày sinh, địa chỉ, quốc tịch | OCR 1–2 | Bắt buộc theo mẫu và phải sửa nếu OCR thiếu. |
| Chủ hiện tại là tổ chức: tên, trụ sở, số ĐKKD; thông tin cá nhân người đại diện | COMPANY + REP | Toàn bộ pháp nhân và đại diện lấy từ Thiết lập mặc định; không lấy từ ảnh hồ sơ. |
| Chủ mới: họ tên, CCCD, ngày/nơi cấp, ngày sinh, địa chỉ, quốc tịch | OCR 1–2 hoặc 4–5 | Dịch vụ tổ chức dùng ảnh 1–2; dịch vụ cá nhân dùng ảnh 4–5. |
| Danh sách số thuê bao | INPUT | Ít nhất một số, 9–12 chữ số. |
| Hình thức thanh toán | SERVICE | Mặc định `Trả trước` cho bốn dịch vụ chuyển quyền hiện tại; cho phép sửa trong tab Giao dịch khi hồ sơ thực tế khác. |
| Ngày lập, ngày hiệu lực | AUTO | Mặc định ngày hiện tại, cho phép sửa. |
| Giờ chuyển quyền | AUTO | Mặc định giờ hiện tại, cho phép sửa; nếu có phải từ 0–23. |
| Số/ngày hợp đồng gốc, ngày phiếu đăng ký dịch vụ | OPTIONAL | Chỉ điền khi có căn cứ giấy tờ tương ứng. |
| Thông tin ủy quyền, liên hệ, ghi chú | OPTIONAL | Được tùy chỉnh khi hồ sơ thực tế cần. |

### 3.2. Giấy cam kết giao dịch sau bán hàng (`aftersale`)

Mục đích: ghi nhận người yêu cầu, giấy tờ xuất trình và loại giao dịch sau bán hàng.

| Nhóm trường | Nguồn | Bắt buộc/nguyên tắc |
| --- | --- | --- |
| Người yêu cầu là cá nhân: họ tên, CCCD, ngày/nơi cấp, địa chỉ | OCR 1–2 | Bắt buộc. Đây là thông tin khách thực tế, không phải thông tin công ty mặc định. |
| Người yêu cầu là tổ chức: tên, số/ngày/nơi cấp ĐKKD, trụ sở | COMPANY | Bắt buộc cho dịch vụ tổ chức. |
| Chủ mới: họ tên, CCCD, ngày/nơi cấp | OCR 1–2 hoặc 4–5 | Dịch vụ tổ chức dùng ảnh 1–2; dịch vụ cá nhân dùng ảnh 4–5; không dùng khi thay SIM. |
| Danh sách số thuê bao | INPUT | Ít nhất một số. |
| Dịch vụ yêu cầu | SERVICE | `Chuyển chủ quyền` cho dịch vụ 1–4; `Thay SIM` cho dịch vụ 5. |
| Giấy tờ kèm theo | SERVICE/OPTIONAL | Mặc định chọn CCCD; SIM gốc và giấy tờ khác có thể chọn/ghi thêm. Phải có ít nhất một loại. |
| Giao dịch viên và ảnh chữ ký | CLERK | Nạp từ người được phân công cho dịch vụ đang làm. Ảnh chữ ký được chèn vào cột giao dịch viên. |
| Số liên hệ dự phòng và liên hệ bổ sung | OPTIONAL | Có thể lấy số liên hệ của khách làm giá trị gợi ý rồi sửa. |

### 3.3. Phụ lục cam kết sử dụng sản phẩm số đẹp (`beautiful_number`)

Mục đích: ràng buộc mức cước tối thiểu và thời gian cam kết đối với từng số đẹp sau khi chuyển quyền.

| Nhóm trường | Nguồn | Bắt buộc/nguyên tắc |
| --- | --- | --- |
| Bên sử dụng số đẹp | OCR 1–2 hoặc 4–5 | Là **chủ mới**: dịch vụ 4 dùng ảnh 1–2, dịch vụ 3 dùng ảnh 4–5. |
| Số thuê bao | INPUT | Ít nhất một số, 9–12 chữ số. |
| Thời gian cam kết | SERVICE + INPUT | Mặc định 12 tháng; người dùng có thể đổi cho từng số, phải là số nguyên dương. |
| Cước cam kết tối thiểu/tháng | INPUT | Bắt buộc cho từng số; nhập số nguyên dương, đơn vị trên giao diện là nghìn đồng. |
| Ngày lập | AUTO | Mặc định ngày hiện tại, cho phép sửa. |
| Ghi chú từng số | OPTIONAL | In trong bảng khi có. |

### 3.4. Hợp đồng thuê bao trả trước (`prepaid_contract`)

Mục đích: lập hợp đồng cung cấp và sử dụng dịch vụ trả trước cho chủ mới.

| Nhóm trường | Nguồn | Bắt buộc/nguyên tắc |
| --- | --- | --- |
| Thông tin doanh nghiệp cung cấp/đơn vị làm thủ tục | COMPANY | Tên, trụ sở, ĐKKD, ngày/nơi cấp và địa chỉ đơn vị cung cấp. |
| Người đại diện doanh nghiệp | REP | Họ tên, chức vụ, CCCD, ngày sinh, ngày/nơi cấp, địa chỉ; điện thoại/email là thông tin bổ sung. |
| Khách hàng sử dụng thuê bao | OCR 1–2 hoặc 4–5 | Chủ mới: dịch vụ 1 dùng ảnh 1–2, dịch vụ 2 dùng ảnh 4–5. |
| Số thuê bao | INPUT | Ít nhất một số; mẫu hiện có tối đa 5 dòng. |
| Ngày hòa mạng | AUTO | Mặc định ngày hiện tại cho từng số, cho phép sửa. |
| Số sê-ri SIM | OPTIONAL | Nhập khi có; để trống không chặn việc tạo tài liệu. |
| Địa điểm và điện thoại giao dịch | COMPANY | Mặc định từ địa chỉ/số điện thoại đã cấu hình, cho phép sửa theo ca. |
| Nhân viên giao dịch | CLERK | Dùng người được phân công cho dịch vụ đang làm. |
| Thời gian thực hiện | AUTO | Mặc định thời điểm hiện tại, cho phép sửa. |
| Mã hợp đồng, mã thuê bao, tên điểm cung cấp, ghi chú/liên hệ khác | OPTIONAL | Điền khi đơn vị có dữ liệu tương ứng. |

### 3.5. Phiếu cung cấp và thay đổi dịch vụ trả trước (`sim_change_form`)

Mục đích: ghi nhận thông tin thuê bao, seri SIM mới, lý do thay SIM và dữ liệu xác minh lịch sử sử dụng theo biểu mẫu tháng 09/2025.

Mẫu DOCX được dựng bằng nội dung Word nguyên bản: đoạn văn, bảng, ô chọn, đường viền và placeholder đều có thể chỉnh sửa. Không dùng ảnh chụp trang PDF hoặc ảnh nền; chỉ logo/dấu/chữ ký vốn là dữ liệu đồ họa mới được phép tồn tại dưới dạng ảnh.

| Nhóm trường | Nguồn | Bắt buộc/nguyên tắc |
| --- | --- | --- |
| Người yêu cầu: họ tên, CCCD, ngày/nơi cấp, địa chỉ | OCR 1–2 | Bắt buộc. |
| Số thuê bao, seri SIM mới | INPUT | Lấy từ dòng đầu của bảng thuê bao cố định; đều bắt buộc khi thay SIM. |
| Lý do thay SIM | SERVICE + INPUT | Mặc định `Mất SIM`; chọn `Hỏng SIM` hoặc `Lý do khác`, trường hợp khác phải mô tả. |
| Ngày yêu cầu | AUTO | Mặc định ngày hiện tại, cho phép sửa. |
| Năm số thường xuyên liên lạc, lần nạp gần nhất, hạn sử dụng, số dư, dịch vụ đổi gần nhất | OPTIONAL | Dùng khi cần xác minh lịch sử thuê bao. |
| Giao dịch viên và ảnh chữ ký | CLERK | Nạp từ người phụ trách dịch vụ thay SIM và điền vào khu vực giao dịch viên. |

## 4. Tổ hợp tài liệu của năm dịch vụ

| \# | Dịch vụ | Chủ cũ/người yêu cầu | Tài liệu tạo theo thứ tự | Ảnh bắt buộc | Trường phải nhập theo hồ sơ |
| --- | --- | --- | --- | --- | --- |
| 1 | Chuyển quyền trả trước, tổ chức → cá nhân | Tổ chức và đại diện lấy từ mặc định; ảnh 1–3 là chủ mới | Chuyển quyền → Cam kết sau bán hàng → Phụ lục số đẹp → Hợp đồng trả trước | 1–3 | Số thuê bao, cước cam kết/tháng. Các thiếu hụt OCR/cấu hình phải được bổ sung. |
| 2 | Chuyển quyền trả trước, cá nhân → cá nhân | Cá nhân chủ cũ | Chuyển quyền → Cam kết sau bán hàng → Phụ lục số đẹp → Hợp đồng trả trước | 1–6 | Số thuê bao, cước cam kết/tháng. |
| 3 | Chuyển quyền cam kết, cá nhân → cá nhân | Cá nhân chủ cũ | Chuyển quyền → Cam kết sau bán hàng → Phụ lục số đẹp → Hợp đồng trả trước | 1–6 | Số thuê bao và cước cam kết/tháng; tháng mặc định 12. |
| 4 | Chuyển quyền cam kết, tổ chức → cá nhân | Tổ chức và đại diện lấy từ mặc định; ảnh 1–3 là chủ mới | Chuyển quyền → Cam kết sau bán hàng → Phụ lục số đẹp → Hợp đồng trả trước | 1–3 | Số thuê bao và cước cam kết/tháng; tháng mặc định 12. |
| 5 | Thay SIM | Cá nhân yêu cầu thay SIM | Cam kết sau bán hàng → Phiếu cung cấp và thay đổi dịch vụ trả trước | 1–3 | Số thuê bao, seri SIM mới và lý do thay SIM. |

Trong **Thiết lập mặc định**, người dùng có thể thêm bao nhiêu giao dịch viên tùy nhu cầu. Mỗi hồ sơ gồm họ tên, ảnh chữ ký và các dịch vụ phụ trách. Năm dịch vụ phải được phân công đủ và không được trùng giữa bất kỳ hai người nào.

### 4.1. Cấu trúc form theo dịch vụ

Hệ thống có một **bộ đệm thông tin chung của hồ sơ** ở nội bộ, độc lập với dịch vụ. Bộ đệm này lưu người đọc từ ảnh 1–3 và người đọc từ ảnh 4–6 theo đúng vị trí file, chưa gán vai trò chủ cũ/chủ mới/người yêu cầu. Bộ đệm không hiển thị thành form riêng trên giao diện; người dùng chỉ thấy trạng thái `Đang đồng bộ ảnh…` hoặc `Đã đồng bộ` cạnh nút chọn folder. Vì vậy có thể chọn folder và hoàn tất OCR trước khi chọn dịch vụ.

Khi chọn dịch vụ, ứng dụng chỉ ánh xạ dữ liệu chung sang form nghiệp vụ. Dịch vụ tổ chức dùng người 1–3 làm chủ mới; dịch vụ cá nhân dùng người 1–3 làm chủ cũ và người 4–6 làm chủ mới; thay SIM dùng người 1–3 làm người yêu cầu. Form dịch vụ dùng trực tiếp đối tượng dữ liệu chung, không tạo bản sao dễ mất khi đổi dịch vụ.

Người dùng không chọn loại tài liệu và không nhập lại dữ liệu cho từng tài liệu. Form dịch vụ gồm các tab nghiệp vụ:

| Tab | Dịch vụ hiển thị | Nội dung |
| --- | --- | --- |
| Tổ chức / Chủ cũ / Người yêu cầu | 1–5 | Dịch vụ tổ chức nạp công ty và đại diện từ mặc định; dịch vụ cá nhân/thay SIM đọc ảnh 1–2. |
| Chủ mới | 1–4 | Đọc ảnh 1–2 với dịch vụ tổ chức hoặc ảnh 4–5 với dịch vụ cá nhân. |
| Đơn vị thực hiện | 1–4 | Đơn vị, người đại diện/điểm giao dịch và người làm thủ tục theo mặc định. |
| Giao dịch | 5 | Giấy tờ và thông tin ngắn gọn cho thao tác thay SIM. |

Bảng thuê bao nằm độc lập ngoài các tab và giống nhau cho cả năm dịch vụ: số thuê bao, tháng cam kết, cước tháng, seri SIM và ngày hòa mạng. Người dùng có thể nhập bảng này trước hoặc chọn folder trước; trường không dùng cho dịch vụ được phép để trống.

## 5. Quy tắc hợp nhất dữ liệu

1. Chọn thư mục mới luôn xóa dữ liệu OCR và đường dẫn ảnh của bộ hồ sơ trước; không được ghép một mặt CCCD mới với một mặt còn sót từ hồ sơ cũ.
2. Dịch vụ cá nhân → cá nhân phải giữ chủ cũ đọc từ ảnh 1–2. Thông tin công ty chỉ được đưa vào phần đơn vị cung cấp của hợp đồng trả trước, không được ghi đè chủ cũ.
3. Với dịch vụ tổ chức → cá nhân, COMPANY/REP cung cấp pháp nhân và người đại diện; OCR 1–2 là chủ mới, tuyệt đối không ghi đè người đại diện tổ chức.
4. Chủ mới đọc từ ảnh 1–2 ở dịch vụ tổ chức hoặc ảnh 4–5 ở dịch vụ cá nhân được dùng đồng thời trong các tài liệu tương ứng.
5. Danh sách thuê bao là nguồn chuẩn dùng chung cho mọi tài liệu trong lô và luôn dùng cùng một cấu trúc nhập liệu.
6. Đổi dịch vụ phải tính lại bộ tài liệu và giá trị SERVICE, nhưng không âm thầm xóa dữ liệu OCR của cùng bộ hồ sơ.
7. Tạo lại cùng bộ hồ sơ phải thay kết quả từ `7.jpg`; chỉ xóa kết quả cũ sau khi lô mới đã tạo thành công.
8. Mỗi lượt đọc folder có một mã phiên tăng dần. Kết quả OCR từ phiên cũ trả về muộn phải bị bỏ qua và không được ghi vào form chung của folder mới.
9. Đồng bộ OCR chỉ đọc hai cặp CCCD `1–2` và `4–5` (nếu có), đồng thời có thể chạy hai cặp song song. Ảnh chân dung `3/6` chỉ được giữ đường dẫn để chèn tài liệu, không OCR, không tạo thumbnail và không sao chép trong bước đồng bộ.

## 6. Luồng nghiệp vụ chính

1. Ứng dụng nạp hồ sơ công ty, người đại diện và danh sách giao dịch viên đã phân công.
2. Người dùng chọn thư mục bộ hồ sơ và chọn một trong năm dịch vụ.
3. Chọn folder ảnh và nhập bảng thuê bao là hai việc độc lập, có thể thực hiện theo thứ tự bất kỳ.
4. Ngay khi nhận folder, ứng dụng đọc ảnh 1–3/4–6 vào bộ đệm thông tin chung nội bộ; bước này không chờ chọn dịch vụ.
5. Khi người dùng chọn hoặc đổi dịch vụ, ứng dụng ánh xạ form chung sang đúng vai trò và dựng các tab tối giản; không chạy OCR lại và không xóa dữ liệu chung.
6. Ứng dụng xác định tổ hợp tài liệu ở nội bộ, ghép COMPANY/REP/CLERK/OCR và áp dụng SERVICE/AUTO; người dùng không phải đổi tài liệu hoặc điền form riêng theo tài liệu.
7. Các trường bắt buộc thiếu/sai được chỉ rõ ngay trong tab nghiệp vụ tương ứng.
8. Ứng dụng tạo toàn bộ DOCX trong thư mục tạm, chuyển đổi cả lô sang JPG, rồi thay nguyên tử các ảnh từ số 7 tại thư mục đích.
9. Kết thúc, người dùng có thể chọn bộ hồ sơ khác hoặc tạo lại; lần tạo lại luôn đè kết quả cũ.

Sơ đồ có thể mở bằng công cụ BPMN tại `diagram.bpmn`.

## 7. Tiêu chí nghiệm thu tối thiểu

- Chọn từng dịch vụ trả đúng tổ hợp tài liệu trong bảng mục 4.
- Giao diện không có bộ chọn tài liệu, form theo tài liệu hoặc bản nháp riêng cho từng tài liệu.
- Dịch vụ tổ chức có các tab Tổ chức, Chủ mới, Đơn vị thực hiện; dịch vụ cá nhân có Chủ cũ, Chủ mới, Đơn vị thực hiện; thay SIM chỉ có Người yêu cầu và Giao dịch.
- Dịch vụ 2 không bao giờ thay chủ cũ cá nhân bằng hồ sơ công ty.
- Phụ lục của dịch vụ 3–4 in chủ mới.
- Giấy cam kết dịch vụ cá nhân/thay SIM in người yêu cầu thực tế, không in pháp nhân mặc định.
- Chọn folder mới không giữ lại mặt CCCD của folder trước.
- Có thể chọn folder khi chưa chọn dịch vụ; đổi qua lại giữa năm dịch vụ không làm mất dữ liệu chung.
- Kết quả OCR của folder cũ hoàn tất muộn không được ghi đè folder mới.
- Dịch vụ 1, 4 và 5 chỉ yêu cầu 1–3; dịch vụ 2–3 yêu cầu 1–6.
- Cước tháng chỉ bắt buộc cho dịch vụ 3–4; ngày hòa mạng mặc định hôm nay; số sê-ri SIM là tùy chọn.
- Tạo lại thay thế ảnh 7+; lỗi bất kỳ tài liệu nào không làm mất bộ kết quả cũ.
