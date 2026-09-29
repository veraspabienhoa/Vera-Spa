# Chuyển VERA sang FaceGate trực tiếp

Sau khi merge và CI đạt, chạy **Deploy VPS Production** trên `main`, bật
**retire_timesoft**. Workflow deploy mã, xác minh commit đang chạy, giữ lịch
archive hiện có và chuyển nguồn trong cùng lần chạy. Không cần cung cấp mật
khẩu hoặc token cho trợ lý.

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
