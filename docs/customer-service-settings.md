# Khách hàng và Cài đặt

Yêu cầu ngày 08/09/2026, theo file đính kèm
`74583c4f5eb6426397d854979e30f2a889c78318.webarchive`:

- Thêm mục **Khách hàng** vào menu.
- Thêm mục **Cài đặt**, gồm **Cài đặt dịch vụ** và **Cài đặt khu vực dịch vụ**.
- Khu vực có ba loại: **Phòng** (một hoặc nhiều giường), **Giường**, **Bàn**.

## Sử dụng

**Khách hàng** cho phép tìm theo tên/điện thoại, thêm, sửa thông tin liên hệ,
xem lịch sử dịch vụ, combo còn lại, khoản chờ thanh toán và xuất danh sách Excel.
Mã khách hàng giữ nguyên khi sửa. Hóa đơn đã thanh toán giữ thông tin tại thời điểm
giao dịch; thông tin trên giao dịch đang mở được cập nhật để có thể thanh toán tiếp.
Không sửa số vé hoặc lịch sử tài chính qua biểu mẫu thông tin khách hàng.

**Cài đặt dịch vụ** cho phép thêm, sửa, xóa, cập nhật giá, thời lượng, định mức vé
combo, quy tắc PR/yêu cầu KTV và trạng thái sử dụng. Thêm trùng tên báo lỗi,
không ghi đè dịch vụ hiện có. Dịch vụ còn giao dịch chưa thanh toán giữ nguyên các
quy tắc nghiệp vụ theo cơ chế bảo vệ hiện có của Live Tour.

**Cài đặt khu vực dịch vụ** quản lý phòng cùng danh sách giường, hoặc giường/bàn
độc lập. Mỗi phòng có từ 1 đến 100 giường, tên giường không trùng trong cùng phòng.
Vị trí đã lưu có thể chọn trong Live Tour. PR khóa toàn bộ giường thuộc cùng phòng.
Khu vực còn giao dịch chưa thanh toán không được đổi hoặc xóa.

Hai trang dùng nút **Mở tab mới**, **Hiện menu / Ẩn menu** có sẵn trong AppShell.
Thay đổi trong biểu mẫu chỉ ghi vào hệ thống khi bấm **Lưu thay đổi**.

## Dữ liệu và phân quyền

Sử dụng cùng dữ liệu server của Live Tour, trong trạng thái `vera_app_setting`.
Không có nguồn Excel, XLSB hoặc Google Sheets. Xuất Excel chỉ tạo file tải xuống.

- Khách hàng: quyền `live_tour_payment`, xuất thêm quyền `live_tour_export`.
- Cài đặt: quyền `live_tour_admin`.
- API kiểm tra quyền trên cả đọc và ghi, không chỉ ẩn menu.
- API đọc riêng chỉ trả dữ liệu cần cho từng trang.
- Ghi dùng khóa giao dịch, phiên bản dữ liệu và khóa chống ghi trùng của Live Tour.

Phòng/giường đang có được nhóm từ danh mục hiện tại mà không thay đổi dữ liệu
khi mở trang. Khi sửa khu vực, bổ sung `area_id`, `area_name`, `area_kind` và
`bed_name` vào các vị trí tương ứng; giữ ID vị trí khi có thể. Không cần đổi schema.
Tên hiển thị khu vực là dữ liệu riêng, không suy ra nhóm bằng cách cắt tên mới
(ví dụ `Sen.1`). Danh mục bị xóa hết vẫn rỗng khi mở lại.

## Kiểm tra

- 21 trường hợp mới trong `tests/test_spa_management.py`: lưu/mở lại, quyền,
  xung đột phiên bản, ghi trùng, lịch sử khách hàng, trùng điện thoại/tên dịch vụ,
  ba loại khu vực, PR và giao dịch đang mở.
- Các kiểm tra Live Tour, mở tab mới, phòng và lịch nghỉ hiện có được chạy cùng.
- React lint và build được kiểm tra; ba cảnh báo lint có sẵn thuộc
  `VeraDateInput.jsx` và `PayrollPageEnhanced.jsx`.
- Fixture lưu server kiểm tra hợp đồng SQL qua FastAPI; chưa phải nghiệm thu
  trên trình duyệt production hoặc PostgreSQL thật với nhiều người dùng đồng thời.

Thay đổi được chuẩn bị trên nhánh `codex/customer-service-settings`, từ main
`ee081c7`. Chưa merge hoặc triển khai bản cập nhật menu này.
