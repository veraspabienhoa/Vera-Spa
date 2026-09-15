# Live Tour — giữ cột Vào ca đến 02:00 sáng hôm sau

## Phạm vi và nền mã

Yêu cầu: dữ liệu cột **Vào ca** của ngày D phải giữ qua 00:00, đến trước
02:00 ngày D+1; từ 02:00 mới bỏ ca của ngày D. Áp dụng theo giờ Việt Nam.

Nền mã đã đối chiếu với GitHub `main` tại thời điểm bắt đầu sửa:
`0ee77b0378371d98341c04fba40f9795fa676aa6` (đã gồm PR #130).
Toàn bộ cây tệp của bản ZIP sau khi khôi phục quyền executable gốc trùng với
Git tree `73e3018d2340f3651a8eeade41e7db0a3c1b064d` của commit này.

Trạng thái bản sửa: **cục bộ; chưa push, chưa tạo PR, chưa merge, chưa deploy**.
Không đọc/ghi dữ liệu nhân viên hoặc tài chính trên production.

## Quy tắc đã thực hiện

| Mốc thời gian ví dụ | Cột Vào ca của ngày 15/09/2026 |
| --- | --- |
| 23:59:59 ngày 15/09 | Giữ Ca 1/Ca 2 |
| 00:00:00 ngày 16/09 | Vẫn giữ ca ngày 15/09 |
| 01:59:59.999999 ngày 16/09 | Vẫn giữ ca ngày 15/09 |
| 02:00:00 ngày 16/09 | Bỏ ca cũ; để trống nếu chưa có xác nhận ca mới hợp lệ |
| Có check-in hợp lệ trong ngày mới | Hiển thị ca mới theo hồ sơ/ngày hiệu lực |

Nhân viên nghỉ phép hoặc bị Admin chủ động đổi trạng thái vẫn tuân thủ
các quy tắc hiện có; bản sửa không cưỡng ép mở ca cho người đang nghỉ.

`shift_day(now)` tính ngày riêng cho cột Vào ca bằng giờ Việt Nam trừ 2 giờ.
Hàm được dùng đồng nhất ở truy vấn snapshot TimeSoft, projection vào ca,
reconcile roster, ca Admin ghi đè, đồng bộ thủ công/tự động và kiểm tra booking.
Trước 02:00 truy vấn snapshot có khóa ngày D dù alias TimeSoft `today` đã đổi
sang D+1; không chỉ giữ dữ liệu trong bộ nhớ trình duyệt.

Ca Admin chọn riêng trong ngày cũng giữ đến 02:00. Nếu chọn lúc 01:00, ca đó
thuộc ngày ca trước và hết hiệu lực lúc 02:00. Kiểm tra thanh toán nhanh có
booking từ chối ca Admin đã hết hiệu lực ngay cả khi đọc snapshot chưa được
scheduler làm mới. Quyền Admin không bị mở rộng và không tạo FaceID giả.

Giữ bản sửa ưu tiên ca hồ sơ theo ngày hiệu lực/chu kỳ của PR #130. Không áp
dụng sớm ca mới hoặc chu kỳ mới cho phần ca cũ kéo dài qua nửa đêm.

Không thay mốc tự thực hiện booking 00:15, điều chỉnh giờ booking, mốc cập nhật
lịch nghỉ 05:00, ngày hóa đơn/doanh thu, quy tắc chấm công hoặc giờ tính lương.
Không xóa bản ghi TimeSoft, lịch sử, dịch vụ đang thực hiện, phòng, thời gian
bắt đầu, hóa đơn, khách hàng hoặc combo.

## Cập nhật tự động và nhiều thiết bị

Không thêm job hay khóa mới. Dùng scheduler hiện có, kiểm tra mỗi 15 giây và
cùng luồng projection với tải lại/làm mới trang. Sau mốc 02:00, tick thành công
kế tiếp ghi revision mới; thiết bị đang poll nhận revision đó. Vì có chu kỳ
scheduler/poll, giao diện không được cam kết đổi đúng từng mili-giây lúc 02:00.
Nếu scheduler đang nhường khóa cho một thao tác, tick sau hoặc làm mới trang
sẽ áp dụng. Việc xóa ca là idempotent, không tăng revision liên tục.

## Kiểm chứng cục bộ

- Bộ mới `tests/test_live_tour_shift_rollover.py`: **57/57 đạt**. Chạy đúng bộ này
  trên nền mã trước sửa: **28 thất bại, 29 đạt**.
- Nhóm 12 tệp kiểm thử trọng tâm: **300/300 đạt**, gồm rollover, ngày hiệu lực,
  check-in, backend, giờ booking/lịch nghỉ, booking/thanh toán nhanh, phân quyền
  ca Admin, server persistence, scheduler lifespan, đọc đồng thời và phạm vi khóa.
- Toàn bộ pytest: **1.030 đạt, 9 thất bại, 24 lỗi collection**. Những thất bại/lỗi
  collection đều do thiếu `gspread` hoặc `google.auth`. Chạy lại nền mã sạch:
  **973 đạt, cùng 9 thất bại và 24 lỗi collection**; tập test lỗi giống hệt nhau.
- **291 tệp Python** phân tích cú pháp thành công; `git diff --check` không lỗi.
- JavaScript: **39 test đạt**; **11 tệp test không nạp được** vì thiếu `esbuild`
  hoặc `jsdom`. Không sửa frontend và không khẳng định build React/toàn bộ CI đạt.

Bộ mới kiểm tra biên 00:00/01:59:59/02:00, UTC/Vietnam/naive time, giao tháng/năm/
năm nhuận, phạm vi truy vấn TimeSoft, luân phiên và ngày hiệu lực, không có
check-in/scan checkout/ca quá cũ, booking và thanh toán nhanh, override không
FaceID, làm mới/khởi tạo lại ứng dụng, scheduler không có người mở trình duyệt,
poll revision và bảo toàn dữ liệu dịch vụ/tài chính.

## Tệp thay đổi

`vera_web_v2_live_tour_checkin.py`, `vera_web_v2_live_tour_daily.py`,
`vera_web_v2_live_tour.py`, `tests/test_live_tour_shift_rollover.py`,
`docs/live-tour-shift-rollover-0200.md`.

## Kiểm tra sau triển khai

Khi có yêu cầu push/PR/merge, đối chiếu lại `main` và chạy CI trước khi merge.
Chỉ chạy **Deploy VPS Production** sau khi người dùng yêu cầu. Trên môi trường
đã triển khai, kiểm tra một ca hợp lệ trước/sau nửa đêm, làm mới trang/thiết bị
thứ hai, và xác nhận từ 02:00 ca cũ được làm trống mà dịch vụ vẫn nguyên vẹn.
