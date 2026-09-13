# Đăng ký nghỉ tải chậm — 13/09/2026

## Bằng chứng

Kiểm tra mã `57af8d554eff6190ea589729e2b7bdf8ad421225`, cùng phiên bản được
hai workflow VPS và Web V2 triển khai thành công trước khi người dùng báo chậm.
Video cho thấy bảng ban đầu báo không có dữ liệu rồi mới xuất hiện lịch nghỉ.
Không có HAR hoặc thời gian xử lý API trong phiên của người dùng; không suy ra
độ trễ mạng hay kết luận sự cố hết kết nối PostgreSQL tái diễn từ video này.

- `reasons`, danh mục Admin, `reason-groups` và `reason-types` gọi
  `_reason_item` trong vòng lặp. Hàm này đọc lại toàn bộ Nội quy qua
  `_policy_rows` mỗi lần. Tái hiện bằng 60 lý do giả lập cho thấy **61 lượt
  đọc SQL Nội quy trên mỗi API danh mục**, chưa tính truy vấn phân quyền/cài đặt.
- Trang chờ cả thống kê → danh sách → lý do → nhân viên rồi mới đưa dữ liệu
  lên màn hình. Đổi một bộ lọc cũng gọi lại cả bốn API.
- Các lượt tải cũ không có cơ chế ngăn ghi đè kết quả của bộ lọc mới.

## Cách sửa

- API danh mục truyền cùng một danh sách Nội quy vào các lần tra lý do trong
  yêu cầu. Dữ liệu không lưu vào cache dùng chung hay sang yêu cầu sau.
  Tra lý do khi ghi vẫn đọc chính sách hiện hành qua kết nối của giao dịch.
  Giữ nguyên hạn chế ngày/vai trò và quyền xem tiền phạt; Admin vẫn xem toàn bộ.
- Bộ tải của trang thực hiện từng yêu cầu, đưa từng phần lên màn hình ngay khi
  hoàn tất và tiếp tục tải các phần khác nếu một phần thất bại.
- Tự động chỉ tải các phần thay đổi ngày/khoảng thời gian/nhân viên/tài khoản.
  Đổi thời gian thống kê có thể đồng thời đổi ngày đăng ký theo hành vi hiện có;
  khi đó danh mục ngày mới cũng phải được tải lại.
- Làm mới và làm mới sau ghi/sửa/xóa luôn đọc lại dữ liệu. Luồng sau khi lưu
  dùng bộ lọc đang mở, kể cả người dùng đổi bộ lọc trong lúc chờ lưu.
- Chỉ giữ khóa của dữ liệu đang hiển thị trong vòng đời trang; không lưu dữ
  liệu lịch nghỉ/nhân viên vào localStorage và không thay đổi xác thực.
- Bỏ kết quả cũ, bỏ lượt tải xếp hàng đã bị thay thế, và không cập nhật trang
  sau khi người dùng rời đi. Chỉ tải danh mục ngày khác của các dòng sửa được
  khi đợt tải chính kết thúc; không gọi lại danh mục đã có chỉ vì đổi thống kê.
- Hiển thị trạng thái đang tải/thất bại riêng cho từng bảng, không báo rỗng
  hoặc tiền phạt bằng 0 khi chưa có kết quả. Không cho sửa bằng danh mục chưa tải.

## Kiểm chứng cần giữ

- `tests/test_leave_catalog_read_budget.py`: 60 lý do chỉ đọc Nội quy **1 lần**
  cho mỗi API; yêu cầu kế tiếp thấy Nội quy vừa sửa; quyền/ngày/tiền phạt và
  tra lý do khi ghi giữ đúng hành vi.
- `web-v2/tests/leavePageLoader.test.mjs`: tuần tự, trả từng phần, chỉ tải phần
  thay đổi, làm mới cưỡng bức, lỗi từng phần, đổi bộ lọc nhanh/quay lại bộ lọc cũ
  và rời trang khi yêu cầu chưa xong.
- `web-v2/tests/leaveInlineEditor.test.mjs`: danh sách hiện trước danh mục;
  giữ quyền sửa các ngày của Admin/Lễ tân/Nhân viên; đổi thống kê không làm mất
  bản sửa đang nhập; lỗi thống kê không chặn danh sách.
- Giữ kiểm thử ghi thành công nhưng làm mới thất bại trong
  `tests/test_leave_submit_refresh_error.py` và các hồi quy nhóm kết nối ở
  [hồ sơ sự cố đăng nhập](production-incident-2026-09-13.md).

Số lần đọc trên là kết quả kiểm thử có kiểm soát, không phải thời gian tải đo
trên production. Sau deploy cần xác nhận lại cả hai health API và thao tác mở
Đăng ký nghỉ, đổi bộ lọc, sửa/lưu của tài khoản được phép.
