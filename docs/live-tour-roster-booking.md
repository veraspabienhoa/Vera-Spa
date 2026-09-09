# Live Tour: danh sách nhân viên, booking và thanh toán

## Danh sách từ dữ liệu nhân viên trên server

- Tên trên Live Tour lấy từ `employees.username` (trường **Tên nhân viên**), không lấy `full_name` (Họ tên đầy đủ).
- Chỉ lấy vai trò `leader`, `nhanvien`, còn trạng thái Đang làm việc và chưa xóa. Nhân viên mới vào danh sách ở trạng thái Nghỉ, chưa vào ca; quản lý vẫn phải cho đi làm/vào ca.
- Mỗi lần đọc Live Tour, hệ thống đối chiếu danh sách nhân viên bằng một truy vấn chung. Dữ liệu không thay đổi thì không ghi lại hoặc tăng revision.
- Dòng cũ được nối theo username; dòng nhập cũ chưa có username chỉ nối theo tên khi tìm thấy đúng một người. Giữ ID, thứ tự, số tua, VIP, trạng thái ẩn, ca và phiên đang phục vụ.
- Tài khoản ngoài phạm vi bị loại khỏi bảng, số lượng và xuất danh sách. Phiên cũ đang mở vẫn giữ phòng và được đưa vào khu vực xử lý riêng để hoàn tất, kết thúc nghỉ hoặc thanh toán. Không tự hủy công việc hay viết lại hóa đơn đã thanh toán.
- Xóa một nhân viên rảnh khỏi Live Tour được ghi nhận để lần đồng bộ sau không tự thêm lại. Khi thêm lại phải chọn từ danh sách Leader/Nhân viên hợp lệ.

## Booking từ phòng hoặc tên nhân viên

- Bấm thẻ phòng hoặc tên nhân viên để mở booking. Nhân viên trong bộ chọn phải đang đi làm, đã vào ca, không ẩn và không nghỉ giữa ca. Sắp xếp rảnh trước, sắp xong sau, rồi đang thực hiện; thời gian còn lại tăng dần trong từng nhóm. Lịch đang chờ nằm cuối danh sách.
- Booking mới để trống khách hàng, dịch vụ, phòng/giường và yêu cầu. Khách hàng trống là Khách lẻ. Bấm thẻ phòng hiển thị ngữ cảnh phòng nhưng vẫn yêu cầu chọn phòng/giường cụ thể.
- Các bộ chọn tìm được theo chữ có hoặc không dấu. Có thể chọn nhiều dịch vụ, sửa số lượng và bỏ dịch vụ.
- Giá, thời lượng và số vé luôn lấy từ danh mục phía server, nhân theo số lượng. Phiên lưu danh sách dịch vụ có ID và snapshot, nên tên dịch vụ chứa ký tự `&` vẫn tính đúng và combo trừ đúng thành phần.
- Đặt lịch tạo trạng thái chờ; Thực hiện bắt đầu dịch vụ. Khi sửa phiên đang thực hiện, giữ mốc bắt đầu và số tua đã ghi nhận; không đổi loại YC sau khi bắt đầu.
- Hoàn thành lưu các chỉnh sửa còn trên form, hoàn tất dịch vụ và chuyển sang Chờ thanh toán trong cùng một thao tác nguyên tử. Nhân viên và phòng được giải phóng để nhận khách tiếp theo. Dữ liệu sai làm toàn bộ thao tác thất bại, không mất phiên đang phục vụ.
- `finish_to_pending` yêu cầu idempotency key và được bảo vệ khi gửi lại. API `complete` cũ vẫn giữ hành vi cũ để tương thích client trước đây.

## Thanh toán và in hóa đơn

- Tiền dịch vụ lấy từ snapshot danh mục theo số lượng; giữ luồng nhập giá vé cho dữ liệu cũ chưa có giá.
- TIP nhập số tiền hoặc chọn nhiều thẻ TIP. Admin cấu hình tên, mệnh giá và danh sách thẻ trên server. Hóa đơn giữ mệnh giá đã dùng dù cấu hình thay đổi sau đó.
- Giảm giá theo số tiền hoặc phần trăm từ 0–100%, tối đa hai số thập phân; số tiền giảm làm tròn half-up đến đồng. Server kiểm tra giới hạn và tự tính tổng.
- Tiền mặt là phương thức mặc định; chuyển khoản và các phương thức hiện có được giữ lại. Combo thành phần tiếp tục kiểm tra số dư, trừ đúng số lượng và không thu lại phần dịch vụ đã trả trước.
- Sau thanh toán có thể xem/in hóa đơn. Admin có thể bật tự động mở hộp thoại in; mặc định tắt, và người thanh toán có thể chọn cho từng hóa đơn. In sử dụng hộp thoại trình duyệt/hệ điều hành, không gửi lệnh âm thầm tới máy in.
- Báo cáo tài chính, hóa đơn, cấu hình TIP và booking được lưu cùng dữ liệu Live Tour trên server. Không thêm kết nối Excel, XLSB hoặc Google Sheets; không cần migration schema.
- Quyền vận hành, thanh toán và quản trị vẫn tách riêng; nhập/sửa thông tin khách hàng cần quyền thanh toán. Phản hồi cho người chỉ có quyền vận hành được che thông tin khách hàng.

## Kiểm tra

Chạy tại thư mục repository:

```sh
python -m pytest -q tests/test_live_tour*.py tests/test_spa_management.py tests/test_service_catalog.py tests/test_global_open_new_tab.py tests/test_tour_room_availability.py tests/test_tour_leave_sync.py --tb=short
```

Chạy tại `web-v2`:

```sh
npm run lint
npm run build
```

Các kiểm tra gồm đối chiếu tên/vai trò trên dữ liệu đã lưu, bảo toàn phiên và lịch sử, xuất danh sách, quyền HTTP, nhiều dịch vụ/số lượng, combo, thao tác hoàn thành nguyên tử và gửi lại, giảm giá/TIP, cùng các helper trình duyệt chạy bằng Node.

Kết quả: 281 test đạt; lint không có lỗi (3 cảnh báo có sẵn ở `VeraDateInput.jsx` và `PayrollPageEnhanced.jsx`); build thành công, còn cảnh báo kích thước chunk có sẵn.

Chưa kiểm thử trực tiếp trên production hoặc máy in thực tế. Sau triển khai cần nghiệm thu bằng tài khoản có quyền phù hợp: danh sách thực tế, booking từ phòng/tên, sửa dịch vụ rồi Hoàn thành, thanh toán và hộp thoại in.
