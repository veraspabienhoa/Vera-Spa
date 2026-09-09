# Dịch vụ đơn lẻ và dịch vụ combo

Vào **Cài đặt → Cài đặt dịch vụ → Thêm dịch vụ**. Chọn **Dịch vụ đơn lẻ** hoặc **Dịch vụ combo**. Danh sách có bộ lọc theo loại, tìm kiếm theo tên/nhóm và thao tác sửa, ngừng sử dụng, xóa.

## Các trường theo ảnh tham chiếu

- Chung: tên, nhóm dịch vụ (chọn nhóm đã có hoặc nhập mới), giá, ngày áp dụng, vô thời hạn hoặc ngày hết hạn, điểm tích lũy và mô tả.
- Đơn lẻ: số lượt mặc định 1, thời lượng mặc định 60 phút, lộ trình gồm các bước có tên/thời lượng và có thể đổi thứ tự. Các quy tắc PR, YC và định mức vé Live Tour nằm trong phần mở rộng.
- Combo: chọn các dịch vụ đơn lẻ, đặt số lượt cho từng dịch vụ. Tổng lượt do server tính. Không cho chọn trùng dịch vụ; tăng số lượt trên dòng đã có.

Trường ngày trong ảnh được đặt tên rõ là **Ngày áp dụng**, mặc định ngày hiện tại tại Việt Nam. Hạn dùng là ngày kết thúc cố định, bao gồm cả ngày đó. Ngày hiệu lực khi Admin lùi ngày thanh toán tuân theo ngày kinh doanh Live Tour (mốc 11:10).

`Số lượt` của dịch vụ đơn lẻ được lưu trong danh mục và dùng làm mặc định khi thêm dịch vụ đó vào combo. Một lần đặt dịch vụ trên Live Tour vẫn là một lần thực hiện. `Điểm tích lũy` được lưu làm cấu hình danh mục; thay đổi này chưa bổ sung ví điểm hay quy trình cộng/đổi điểm.

## Mua và dùng combo

Trong **Live Tour → Khách hàng & combo → Mua combo**, chọn gói vừa tạo. Gói khách mua lưu bản chụp hạn dùng và số lượt của từng dịch vụ; sửa danh mục sau đó không đổi quyền lợi đã mua.

Khi thanh toán bằng combo, mỗi lần thực hiện dịch vụ trừ một lượt đúng dịch vụ đó, bao gồm nhiều dịch vụ nối bằng `&`. Server kiểm tra khách hàng, ngày sử dụng và số lượt từng thành phần; không cho mượn lượt của dịch vụ khác. Đổi tên dịch vụ giữ nguyên liên kết qua ID. Lịch sử khách hiển thị số lượt còn lại của từng thành phần.

Doanh thu combo thành phần ghi nhận khi mua. Khi dùng lượt, hóa đơn lưu giá trị dịch vụ được combo thanh toán (`combo_covered_amount`), tổng tiền phát sinh chỉ gồm TIP; không giảm giá gói lần nữa. Báo cáo lưu đúng số lượt theo thành phần.

Các combo vé cũ vẫn dùng định mức `ticket_units` và cách ghi nhận tiền hiện có. Chức năng nhập combo cũ chỉ nhận combo vé, vì dữ liệu nhập cũ không có số lượt từng dịch vụ. Có thể chuyển danh mục combo vé sang combo thành phần qua Cài đặt; các lượt mua trước đó vẫn giữ điều khoản cũ.

## Lưu trữ và kiểm tra

Danh mục và số dư dùng PostgreSQL hiện có của Live Tour, không đọc Excel, XLSB hoặc Google Sheets; không cần migration. Các thao tác sử dụng quyền quản trị/thanh toán, khóa giao dịch, revision và idempotency hiện có. Chặn xóa dịch vụ còn trong combo hoặc còn lượt khách đã mua.

Kiểm tra tự động: `tests/test_service_catalog.py` cùng các bộ kiểm tra Live Tour, quản lý spa, phòng, nghỉ phép và mở tab. Giao diện được kiểm tra lint và build. Chưa kiểm tra thao tác trên trình duyệt production; chưa merge hoặc deploy thay đổi này.
