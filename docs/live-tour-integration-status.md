# Live Tour — lưu trữ hoàn toàn trên máy chủ (08/09/2026)

## Phạm vi hiện tại

Theo yêu cầu mới nhất, Live Tour không liên kết, đọc, cập nhật hay đồng bộ bất kỳ file Excel/.xlsb/Google Sheets nào. Workbook VBA là tài liệu tham khảo nghiệp vụ. Các hướng dẫn cũ về nhập TourVera, đồng bộ Sheets, phục hồi Drive hoặc mở báo cáo mua hàng ngoài đã hết hiệu lực đối với Live Tour.

- Khởi tạo lần đầu từ danh sách KTV/Leader đang làm việc trong bảng `employees` trên PostgreSQL. Nhân viên trong Live Tour mặc định **Nghỉ**, chưa vào ca; người vận hành chọn trạng thái/ca trực tiếp. Lỗi truy vấn nhân viên hủy khởi tạo, không ghi một bảng rỗng thay thế.
- Booking, phòng/dịch vụ, trạng thái/ca/break, hóa đơn, khách hàng/combo, lịch sử và bản sao lưu đều nằm trong `vera_app_setting` (`live_tour/state`). Mỗi thay đổi dùng giao dịch PostgreSQL, khóa, revision và mã chống ghi trùng.
- Giữ dữ liệu Live Tour đã lưu, kể cả giao dịch, danh mục, ID và dấu vết nguồn cũ. Các dấu đồng bộ chưa hoàn tất chỉ còn dữ liệu lưu trữ; không chạy tiếp lên file ngoài.
- Gỡ API đồng bộ/merge file, trình tải/ghi Drive, cấu hình link TourVera, nút đồng bộ và đường dẫn báo cáo mua hàng ngoài. Tab cũ gọi các lệnh `sync_leaves`, `merge_current_tour`, `merge_current_tour_preview` nhận HTTP 410 trước khi đọc/ghi dữ liệu.
- Gỡ callback từ Bảng tua cũ sang Live Tour. Chức năng đồng bộ của Bảng tua cũ vẫn độc lập, không thay đổi Live Tour. `TourPage.jsx` giữ nguyên so với main `873ecbb`.
- Excel/PNG chỉ là bản xuất tải xuống từ dữ liệu máy chủ, không phải nguồn vận hành hoặc phương tiện lưu trữ chính. Nhập số dư combo cũ là nhập tay trên web.

## Chức năng đã có

Trang/menu riêng, tab mới/ẩn-hiện menu, lọc ca/nhân viên, phòng VIP/PR, booking đơn/nhanh/hàng loạt, bắt đầu/hoàn thành/thêm/đổi dịch vụ, nghỉ giữa ca, thanh toán/combo, lịch sử khách hàng, danh mục và sao lưu server. Báo cáo tách doanh thu đã thu với dự kiến chưa xuất bill. Xuất tùy chỉnh chọn cột và phạm vi nhân viên. Chuyển phiên quá hạn có ngưỡng 0–1440 phút, xem trước và xác nhận đúng danh sách/phiên bản.

## Kiểm chứng

**202 test đạt** trong nhóm `test_live_tour*.py`, `test_tour_leave_sync.py`, `test_global_open_new_tab.py`, `test_tour_room_availability.py`. Số lượng thay đổi so với 210 trước đó vì bỏ 17 kiểm thử chỉ dành cho các luồng file vừa gỡ, thêm 9 kiểm thử server-only. Không bỏ qua kiểm thử đang thất bại để thay thế bằng số đếm cũ.

Kiểm thử mới chặn yêu cầu mạng ngoài, kiểm tra khởi tạo/refresh từ DB, không ghi bảng rỗng khi DB lỗi, booking được đọc lại bởi một instance ứng dụng khác dùng cùng DB fixture, giữ dữ liệu cũ, và HTTP 410 cho tab cũ trước bất kỳ thao tác dữ liệu nào. Đây là kiểm thử hợp đồng SQL với DB fixture, chưa phải nghiệm thu PostgreSQL thật.

React lint: 0 lỗi, 3 cảnh báo sẵn có; build thành công. Python compile và whitespace đạt. Bộ xem thử chỉ đọc tại `web-v2/dev/live-tour-preview.mjs` vẫn dùng DTO thật và dữ liệu giả; không gọi API sản phẩm. Trình duyệt phiên làm việc chặn localhost nên chưa xác nhận ảnh/tương tác responsive.

Khi chạy suite rộng hơn (bỏ hai file mua hàng do môi trường thiếu `pyxlsb`), 380 test đạt trước khi dừng ở 5 lỗi. Đã chạy đúng 5 test đó trên worktree sạch của `main` tại `873ecbb` và chúng cũng thất bại:

1. `test_direct_break_return_penalty.py::test_timesoft_sync_runs_break_return_penalty_directly`
2. `test_leave_submit_refresh_error.py::test_successful_leave_create_is_not_reclassified_when_refresh_fails`
3. `test_violation_unlimited.py::test_violation_type_is_not_grouped_as_khong_phep`
4. `test_web_v2_auth_gateway.py::test_login_is_exchanged_server_side_and_never_returns_bridge_password`
5. `test_web_v2_auth_gateway.py::test_invalid_credentials_are_returned_without_a_token_exchange`

Hai lỗi auth yêu cầu cấu hình PostgreSQL chưa có trong môi trường kiểm thử. Không sửa các chức năng không liên quan chỉ để làm suite xanh.

## Còn cần nghiệm thu trước phát hành

- Giao diện desktop/mobile, phân quyền tài khoản thật và nhiều người cùng thao tác trên PostgreSQL thật.
- Cấu hình giá dịch vụ/combo phù hợp dữ liệu vận hành; giá chưa xác định không được coi là doanh thu đã thu.
- Backup/retention và hiệu năng aggregate JSON theo quy mô sử dụng; không cần file nguồn để vận hành.
- Chưa merge hoặc chạy Deploy VPS Production. Không kết luận đã hoàn tất 100% mọi nghiệp vụ VBA chỉ từ kiểm thử tự động.
