# Sự cố đăng nhập và tải dữ liệu ngày 13/09/2026

Người dùng đã xác nhận sau bản sửa: **đăng nhập được và dữ liệu đã hiển thị**.
Hồ sơ này được lưu theo yêu cầu của người dùng để tránh lặp lại lỗi.

## Triệu chứng và bằng chứng

- Trước đó xuất hiện “Không xác minh được phiên đăng nhập PostgreSQL”. Sau khi
  phần xác thực hoạt động lại, Live Tour vẫn báo HTTP 500; lịch nghỉ, hóa đơn và
  danh sách nhân viên không tải được.
- `/v2/auth/health` vẫn trả HTTP 200 nhưng `/v2/health`, dùng nhóm kết nối nghiệp
  vụ, bị timeout. Hai kết quả phải được kiểm tra riêng.
- Log runtime ghi nhận `sqlalchemy.exc.TimeoutError`: nhóm kết nối thực tế có
  `size=5`, `overflow=5`, hết thời gian chờ sau 30 giây. Đây là cấu hình quan sát
  tại thời điểm sự cố, không phải giá trị mặc định cần sao chép cho mọi môi trường.
- PostgreSQL ghi nhận **9 kết nối cùng chờ advisory lock** và một giao dịch đang
  giữ kết nối trong trạng thái `idle in transaction`. Các yêu cầu khác không lấy
  được kết nối để đọc dữ liệu.
- Kiểm tra trực tiếp vẫn đọc được **723 bản ghi lịch nghỉ** và 67 hồ sơ nhân viên.
  Đây là số liệu lúc kiểm tra, không phải tiêu chí cố định cho các lần deploy sau.

## Nguyên nhân và bản sửa

Live Tour giữ giao dịch và khóa trạng thái bảng tua khi gọi chuỗi tính chấm công.
Hai phần xử lý `vera_web_v2_outside_leave_rule.py` và
`vera_web_v2_break_return_penalty.py` lại mở thêm kết nối để đọc nội quy, ghi phạt
và gửi thông báo. Khi các kết nối còn lại đang chờ cùng khóa bảng tua, việc lấy
thêm kết nối làm cạn nhóm kết nối dùng chung. Vì vậy cả màn hình không liên quan
như lịch nghỉ cũng bị ảnh hưởng.

[PR #95](https://github.com/veraspabienhoa/Vera-Spa/pull/95) đã:

1. Dùng lại `conn` của giao dịch hiện tại khi đọc nội quy và ghi phạt.
2. Dùng `conn.begin_nested()` để cô lập lỗi ghi phạt bằng savepoint, giúp giao
   dịch bên ngoài vẫn sử dụng được khi một lần ghi phạt thất bại.
3. Cho giao dịch đọc chấm công thành công commit các bản ghi sự kiện và hàng đợi
   thông báo; cập nhật cả route snapshot gốc và route thay thế trong operations.
4. Bỏ gửi thông báo đồng bộ trong chuỗi đọc. Tác vụ TimeSoft hiện có gửi các
   thông báo đã commit theo lịch nền, giữ cơ chế thử lại và chống trùng.
5. Bổ sung kiểm tra `/v2/health` khi deploy, bên cạnh kiểm tra xác thực.

Giữ nguyên cơ chế nhóm kết nối xác thực riêng trong `vera_web_v2_auth_pool.py`:
giới hạn số kết nối/thời gian chờ, dùng cùng cơ sở dữ liệu và SSL, vẫn kiểm tra
thu hồi phiên và khóa tài khoản từ PostgreSQL. Không dùng cache danh tính hoặc
bỏ qua xác thực để che lỗi truy cập cơ sở dữ liệu.

Tăng số kết nối hoặc restart đơn thuần không loại bỏ nguyên nhân mở kết nối lồng
nhau. Không thay đổi quy tắc tính phạt, cơ chế chống trùng hoặc số tiền hóa đơn
để giải quyết lỗi hiệu năng này.

## Kiểm chứng phục hồi

- **1.019 kiểm thử Python đạt**, bao gồm kiểm thử hai luồng ghi phạt khi chỉ có
  một kết nối và khả năng rollback riêng lần ghi lỗi.
- Kiểm tra backend, React và hàng đợi thông báo trên GitHub đều đạt trước merge.
- Commit production: `bbb0894e4cdce23050a53e7314106230fc13e08c`.
- [Lần deploy thành công](https://github.com/veraspabienhoa/Vera-Spa/actions/runs/34749729221).
- Sau deploy, `/v2/health` và `/v2/auth/health` đều trả HTTP 200 với `ok=true`.
  Lần chụp trạng thái PostgreSQL sau deploy không còn kết nối chờ khóa.
- Sau đó người dùng xác nhận đăng nhập và hiển thị dữ liệu đã hoạt động.

## Chẩn đoán đúng khi có sự cố mới

1. Ghi nhận thao tác lỗi, URL API, mã HTTP và thời điểm; phân biệt không đăng nhập
   được với đã đăng nhập nhưng không tải được dữ liệu. Số liệu đang hiện có thể
   là cache của lần tải trước.
2. Xác minh máy chủ đang chạy bản ứng dụng. Trong sự cố này, DNS Cloudflare của
   `app`, `api`, `admin.veraspa.vn` trỏ về `160.236.192.51`. VPS `.65` người dùng
   từng SSH vào chạy một website khác, không phải runtime VERA. Cần đối chiếu lại
   cấu hình hiện hành trước mọi lần thay đổi; không đổi DNS chỉ từ IP được cung cấp.
3. Ưu tiên kênh SSH triển khai đã được cấu hình và cho phép. Không yêu cầu người
   dùng gửi mật khẩu root/PostgreSQL vào cuộc trò chuyện. Kết nối DB thành công
   từ máy cá nhân không chứng minh tiến trình API trên VPS dùng đúng cấu hình.
4. Dùng `vera_vps_runtime_diagnostics.py` để thu thập log của đúng systemd unit
   và trạng thái PostgreSQL. Script chỉ xuất loại lỗi, vị trí stack và số liệu
   tổng hợp; kết nối chẩn đoán chỉ đọc, có giới hạn thời gian. Không chỉ lọc log
   “local auth”, vì cách đó bỏ sót lỗi nghiệp vụ.
5. Đối chiếu timestamp của log, lần khởi động và SHA deploy. Giờ VPS và runner có
   thể lệch; traceback trong cửa sổ 20 phút có thể thuộc tiến trình trước restart.
6. Lỗi Actions “job was not started … failed to be acquired (5 attempts)” và
   “internal error” xảy ra trước khi job chạy không chứng minh code deploy lỗi.
   Kiểm tra runner, concurrency và SHA; chỉ chạy lại sau khi hiểu trạng thái run.
7. Sau sửa, kiểm tra cả hai API health, dữ liệu nghiệp vụ và màn hình người dùng.
   Chỉ kết luận những gì đã kiểm chứng; không dùng trạng thái workflow xanh làm
   bằng chứng duy nhất rằng toàn bộ ứng dụng hoạt động.

Các lỗi `DefaultCredentialsError`/`JSONDecodeError` ở tác vụ đối soát Google và
`ProgrammingError` tại phần đọc vault cũng từng xuất hiện trong log. Chúng cần
chẩn đoán cấu hình riêng nếu tái diễn; bản sửa nhóm kết nối không chứng minh các
cấu hình tích hợp đó đã được khắc phục. Không gộp chúng với lỗi hết kết nối.

## Kiểm tra hồi quy cần giữ

```bash
python -m pytest -q tests/test_attendance_connection_reuse.py tests/test_auth_pool.py tests/test_auto_penalty_employee_notifications.py tests/test_vps_runtime_diagnostics.py
```

- `test_attendance_connection_reuse.py`: hai luồng phải hoàn tất với một kết nối;
  ghi thành công được lưu và lỗi ghi riêng không làm hỏng giao dịch bên ngoài.
- `test_auth_pool.py`: xác thực vẫn dùng được khi nhóm kết nối nghiệp vụ bị chiếm
  hết; giữ giới hạn kết nối và chính sách SSL.
- `test_auto_penalty_employee_notifications.py`: hàng đợi vẫn thử lại/chống trùng;
  tác vụ nền gửi thông báo, chuỗi đọc không gửi ngay khi đang giữ giao dịch.
- `test_vps_runtime_diagnostics.py`: giữ thông tin chẩn đoán hữu ích nhưng không
  làm lộ dữ liệu riêng trong log.

Workflow thông báo cần đủ phụ thuộc cho các module chấm công được kiểm thử,
bao gồm `requests` và `gspread`. Giữ kiểm tra hồi quy khi đổi thiết kế; cập nhật
kiểm tra hành vi cũ cho đúng ranh giới giao dịch, không chỉ tắt một kiểm tra đỏ.
