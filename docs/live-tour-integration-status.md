# Live Tour — bàn giao tích hợp ngày 08/09/2026

## Nền mã

Nhánh Live Tour được ghép từ `main` tại commit `873ecbb` (Update employee schedule and timekeeping controls). Các cập nhật chấm công, lịch nghỉ, lương và tìm nhân viên trên main được giữ nguyên. Không sửa `TourPage.jsx`, không thay thế Bảng tua gốc.

Live Tour là trang vận hành riêng: booking đơn/nhanh/nhiều nhân viên, bắt đầu/hoàn thành, thêm/đổi dịch vụ, nghỉ giữa ca, chờ thanh toán, thanh toán/combo, lịch sử khách hàng, báo cáo và danh mục. Bản đối chiếu VBA đầy đủ nằm trong `live-tour-vba-parity.md`, bao gồm 55 module và 18 UserForm.

## Các chặn an toàn mới

- Nhập danh sách từ Bảng tua phải xem trước và xác nhận đúng phiên bản/nguồn. Chỉ lần khởi tạo đầu tiên lấy trạng thái dịch vụ; lần nhập sau không khôi phục dịch vụ đã thu tiền.
- Không khôi phục bản sao khi bản hiện tại hoặc bản sao có dịch vụ, khoản chờ thanh toán hoặc nghỉ giữa ca.
- Không đổi/xóa quy tắc dịch vụ hoặc phòng còn gắn với khoản chưa thanh toán.
- Mỗi thay đổi mới cần revision và mã chống ghi trùng; phản hồi thanh toán và mã đồng bộ được giữ để đối soát.
- Doanh thu dự kiến chưa xuất bill tách khỏi doanh thu đã thu, cả trên giao diện và Excel.
- Bộ đếm chuyển ngày lúc 10:00; ngày tài chính chuyển lúc 11:10 theo giờ Việt Nam.

## Kiểm chứng

Chạy nhóm kiểm thử `test_live_tour*.py`, `test_tour_leave_sync.py`, `test_global_open_new_tab.py`, `test_tour_room_availability.py`; đồng thời compile Python, kiểm tra whitespace, lint và build React.

Kết quả sau cùng: **186 test đạt**; compile Python và `git diff --check` đạt; React lint không có lỗi (3 cảnh báo sẵn có ngoài Live Tour), build thành công. Không có thay đổi trong `TourPage.jsx` so với main.

Khi chạy suite rộng hơn (bỏ hai file mua hàng do môi trường thiếu `pyxlsb`), 380 test đạt trước khi dừng ở 5 lỗi. Đã chạy đúng 5 test đó trên worktree sạch của `main` tại `873ecbb` và chúng cũng thất bại:

1. `test_direct_break_return_penalty.py::test_timesoft_sync_runs_break_return_penalty_directly`
2. `test_leave_submit_refresh_error.py::test_successful_leave_create_is_not_reclassified_when_refresh_fails`
3. `test_violation_unlimited.py::test_violation_type_is_not_grouped_as_khong_phep`
4. `test_web_v2_auth_gateway.py::test_login_is_exchanged_server_side_and_never_returns_bridge_password`
5. `test_web_v2_auth_gateway.py::test_invalid_credentials_are_returned_without_a_token_exchange`

Hai lỗi auth yêu cầu cấu hình PostgreSQL chưa có trong môi trường kiểm thử. Không sửa các chức năng không liên quan chỉ để làm suite xanh.

## Chưa xác nhận hoàn tất 100% VBA

- Chưa nghiệm thu đa trình duyệt, tài khoản thật và khóa giao dịch trên PostgreSQL thật.
- Chưa so ảnh responsive/pixel với Excel/Bảng tua đang vận hành.
- Chưa di chuyển lịch sử Report/KhachHang ở các file ngoài, chưa tái tạo nguyên mẫu báo cáo MuaDo và quy trình sửa hóa đơn cũ.
- Cần chốt thiết kế lưu trữ/retention: hiện sử dụng JSON giao dịch trong `vera_app_setting`, chưa tách các sổ tài chính/khách hàng thành bảng chuyên biệt.
- Chưa chạy Deploy VPS Production. Chỉ xem xét merge/phát hành sau khi nghiệm thu các mục trên; không chạy song song Excel và Live Tour để thu tiền cho cùng một dịch vụ.
