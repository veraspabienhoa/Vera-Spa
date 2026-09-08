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

Kết quả sau cùng: **210 test đạt**; compile Python và `git diff --check` đạt; React lint không có lỗi (3 cảnh báo sẵn có ngoài Live Tour), build thành công. Không có thay đổi trong `TourPage.jsx` so với main.

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
- Chưa di chuyển lịch sử Report/KhachHang ở các file ngoài. `Bao_cao_mua_hang.bas` chỉ mở/activate `BaoCaoMuaHang.xlsb`; không chứa mã tính toán báo cáo đó. Live Tour mở trang đối chiếu mua hàng hiện có bằng quyền `revenue_view`. Cần file ngoài nếu muốn đối chiếu thêm các nghiệp vụ bên trong nó.
- Cột AF:AH dành cho nhật ký sửa hóa đơn không đủ để xác định quy trình sửa hóa đơn cũ; chưa thấy UserForm thực hiện quy trình đó trong 18 form đã trích xuất. Không coi các cột dự phòng là bằng chứng đã đọc được toàn bộ nghiệp vụ sửa bill.
- Cần chốt thiết kế lưu trữ/retention: hiện sử dụng JSON giao dịch trong `vera_app_setting`, chưa tách các sổ tài chính/khách hàng thành bảng chuyên biệt.
- Chưa chạy Deploy VPS Production. Chỉ xem xét merge/phát hành sau khi nghiệm thu các mục trên; không chạy song song Excel và Live Tour để thu tiền cho cùng một dịch vụ.

## Phần tiếp tục: báo cáo và nghỉ giữa ca

- Xuất bảng tùy chỉnh cho phép chọn các cột Bảng tua và phạm vi tất cả/đang hiển thị/đã chọn. Không chọn cột hoặc phạm vi không có nhân viên thì không xuất. Backend kiểm tra whitelist cột, dòng đã xóa/ẩn và quyền khôi phục dòng ẩn; không cho dùng bộ chọn này để xuất lẫn dữ liệu tài chính. Kiểm thử mở lại XLSX xác nhận đúng cột, đúng nhân viên và không thực thi chuỗi công thức.

- Hoàn thiện chuyển phiên quá hạn: Admin chọn ngưỡng 0–1440 phút (mặc định 15), xem trước nhân viên/dịch vụ/phòng/giờ kết thúc rồi xác nhận. Preview không ghi dữ liệu. Thay đổi revision hoặc có thêm phiên vừa quá hạn sẽ yêu cầu xem trước lại. Xác nhận chỉ chuyển trạng thái sang chờ thanh toán, giữ dịch vụ và không tạo doanh thu; gửi lại cùng mã yêu cầu không lặp cập nhật.

- Thêm nút **Mở báo cáo mua hàng** trong Live Tour; mở tab mới vào đúng khu vực đối chiếu của Doanh thu. Kiểm tra quyền cả khi hiện nút lẫn xử lý bấm; tài khoản chỉ có quyền xem Doanh thu cũng mở được tab Báo cáo.
- Admin xem lịch sử bắt đầu/vào lại, thời gian nghỉ, kết quả đúng giờ/quá 90 phút và người thao tác. Xuất Excel nghỉ giữa ca dùng cùng bộ lọc ngày/giờ và cần đồng thời quyền admin + export.
- Kiểm thử thực thi JavaScript đối chiếu ma trận quyền export: quyền xuất bảng không mở quyền xem lịch sử hoặc tài chính.
- Có bộ xem thử độc lập, dùng DTO thật và 12 nhân viên giả lập, phòng PR, danh sách phòng 4 người và lượt nghỉ 95 phút. Tất cả hàm API bị thay bằng dữ liệu chỉ đọc; các đường dẫn API chưa giả lập bị chặn. Không đưa bộ xem thử vào entry/build sản phẩm.

Chạy từ `web-v2`:

```sh
LIVE_TOUR_TEST_PYTHON=/path/to/python-with-project-dependencies node dev/live-tour-preview.mjs
```

Mở `http://127.0.0.1:5174/preview`, thêm `?role=viewer` để kiểm tra người chỉ xem, hoặc `/preview-mobile` cho khung 390px. Thêm `--check` vào lệnh để kiểm tra server phục vụ HTML/JS/DTO và chặn API; bước này đã đạt. Trình duyệt kiểm thử của phiên làm việc chặn localhost (`ERR_BLOCKED_BY_CLIENT`), nên chưa có kết quả tương tác/ảnh desktop-mobile; không dùng kiểm tra server làm bằng chứng giao diện đã đạt.
