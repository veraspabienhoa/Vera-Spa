# Chuyển VERA sang FaceGate trực tiếp

Production đã chuyển sang FaceGate từ **29-09-2026**, xác minh lại sau
Deploy VPS Production #617. Những lần cập nhật tiếp theo chọn `main`, **không
bật retire_timesoft**, không chạy lại cutover `--apply`. Workflow vẫn yêu cầu
frontend và VPS đúng cùng commit: chạy Deploy VERA SPA Web V2 trước, rồi
Deploy VPS Production. Không xóa worker có tên TimeSoft: nó còn gửi thông báo
đã commit và xử lý đầu vào FaceGate theo cấu hình nguồn.

Chỉ khi thiết lập một hệ thống mới chưa chuyển nguồn mới dùng `retire_timesoft`
để chọn nguồn lần đầu, theo một quyết định vận hành riêng.

Kết quả thành công cần có `ok=true`, `source=facegate`,
`timesoft_network_enabled=false`, `cache_fresh=true`. `already_applied=true`
nghĩa là nguồn đã được chọn từ trước; ngày chuyển nguồn được giữ nguyên.
Các số `pending_employee_count` / `pending_reasons` vẫn thể hiện công chưa đủ
bằng chứng. Đây không phải lý do để tự điền giờ ra hoặc lương 0.

Sau chuyển đổi, mở **Thiết bị → Nguồn chấm công hiện tại → Kiểm tra nguồn**;
kiểm tra một lượt quét mới xuất hiện trong lịch sử và Chấm công, sau đó kiểm tra
Ca 1/Ca 2 tương ứng trên Live Tour. Lương hành chánh dùng nút tính từ Chấm công;
lương KTV tiếp tục dùng TIP Live Tour. Nhân viên chưa đăng ký ảnh hoặc chưa có
ánh xạ phải hoàn tất hồ sơ Face ID trong VERA trước khi tự nhận công.

Để đọc trạng thái trên VPS, chạy nguyên dòng sau trong PowerShell:

```powershell
ssh root@160.236.192.51 "cd /opt/vera-spa/current && /opt/vera-spa/.venv/bin/python -B vera_facegate_cutover.py"
```

Nếu workflow báo archive worker đang chạy hoặc attendance worker đang chạy,
chờ lần chạy đó kết thúc rồi chạy lại cùng release. Không tạo cron thứ hai,
không xóa khóa, không tắt worker gửi thông báo. Nếu nguồn quá hạn, kiểm tra
kết nối Tailscale/máy FaceGate và log archive; hệ thống không tự quay lại TimeSoft.

Lịch sử TimeSoft trong PostgreSQL, log gốc FaceGate, ngoại lệ được duyệt và lương
đã lưu được giữ lại. Không xóa tài khoản/dữ liệu TimeSoft như một phần chuyển đổi.
Không deploy phiên bản cũ không hiểu `attendance-source.json` khi đang dùng
FaceGate. Muốn khôi phục nguồn cũ cần một quyết định vận hành riêng và đối chiếu
công trong khoảng đã chuyển đổi.

Ngày 29-09, người vận hành đã xác minh chuyển nguồn lúc 21:15:59 và có lần
đồng bộ tiếp lúc 21:19:18. Với bản sửa định danh Gia Anh, deploy mã mới rồi
chạy lệnh chỉ đọc phía trên; không cần bật lại `retire_timesoft` hoặc chạy lại
`--apply`. Kết quả cần giữ `source=facegate`, `timesoft_network_enabled=false`,
`cache_fresh=true` và có `gia-anh-identity-2026-09-29-79335` trong
`applied_identity_review_ids` khi đọc ngày 29-09-2026. Có thể thêm
`--date 2026-09-29` nếu kiểm tra sau ngày này.

Ngoại lệ chỉ nhận diện lượt 79335 của Gia Anh theo xác nhận của người vận hành.
Giờ ra, ca còn mở, thiếu lịch hoặc nhân viên chưa ánh xạ vẫn cần xử lý riêng.

## Tạm ngừng công/lương theo xác nhận 29-09

Chính sách `temporary-attendance-payroll-suspension-2026-09-29` tạm bỏ
`admin`, `akamen`, `letan`, `Ms Tuyết` khỏi công từ ngày 29-09-2026 và các
lần tính/chốt bảng lương mới có kỳ giao với khoảng tạm ngừng. Không tính
một phần tháng cho các tài khoản này; lịch sử đã lưu giữ nguyên. Không thay
quyền đăng nhập hoặc xóa nhân viên. Khi cần tính lại, cập nhật `effective_until`
của đúng username trong `vera_attendance_participation.py` thành ngày bắt đầu
tham gia lại và deploy; giữ mốc bắt đầu cũ để lịch sử không bị tính lại.

Năm người chờ đăng ký Face ID vẫn hiện là thiếu ánh xạ và chưa đủ bằng chứng;
không tự loại họ khỏi lương và không cần bật lại TimeSoft để đăng ký sau.
Dùng Hồ sơ nhân viên/Face ID để đăng ký khi có ảnh được xác nhận đúng người.

Sau deploy chạy CLI inspect ở trên với `--date 2026-09-29`: cần có
`excluded_employee_count=4`, đúng bốn `excluded_usernames`, giữ review Gia Anh,
`source=facegate`, `timesoft_network_enabled=false` và cache mới. Số nhân viên
tham gia dự kiến 54 nếu danh sách 58 người chưa đổi; không cố định số pending
vì lượt quét và giờ đóng ca tiếp tục thay đổi. Kiểm tra thêm màn Chấm công và
bảng lương mới không có bốn tài khoản, lịch sử tiền đã lưu vẫn có thể đọc.

Lương hành chánh lấy Chấm công hoặc lựa chọn Lịch VERA hiện hữu; lương KTV
lấy TIP Live Tour. Endpoint tải TIP từ snapshot TimeSoft cũ trả 410 sau cutover.
Các module/định dạng Excel mang tên TimeSoft còn phục vụ đọc lịch sử và tương
thích nội bộ, không chứng minh còn kết nối nhà cung cấp. Không gỡ phần lịch sử.
