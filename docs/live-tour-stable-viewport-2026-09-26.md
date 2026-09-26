# Live Tour: giữ vị trí khi thao tác — 26-09-2026

Video người dùng cho thấy mỗi lần lưu, thanh “Đang lưu thao tác Live Tour…”
xuất hiện phía trên phòng/bảng nhân viên rồi biến mất. Mã nguồn xác nhận thanh
này được thêm/bỏ khỏi luồng bố cục, làm dịch chuyển nội dung bên dưới. Các lỗi,
thông báo kết quả và nhắc hóa đơn cũng từng thay đổi chiều cao đầu bảng.

Bản sửa giữ sẵn vùng trạng thái có chiều cao cố định trên desktop/mobile;
nội dung dài cuộn trong vùng này, vẫn đọc được toàn bộ lỗi và kết quả. Vùng
nhắc hóa đơn giữ kích thước cả khi lời nhắc bị đóng. Live Tour không dùng
scroll anchoring tự động theo dòng nhân viên khi thứ tự bảng thay đổi. Hộp
thoại cũ nhận/trả focus với preventScroll, bao gồm các ô từng dùng autoFocus.

Không đặt lại scrollY sau khi API trả về, vì người dùng có thể chủ động cuộn
trong lúc chờ. Các nút chủ động chuyển đến hóa đơn/báo cáo và Về đầu trang vẫn
hoạt động. Không thay API, quy tắc xếp tua, quyền, idempotency hoặc giao dịch.

Kiểm thử giao diện bao gồm lưu chậm, lỗi giữ bản nháp, vùng báo trạng thái giữ
nguyên node/kích thước CSS, đóng nhắc hóa đơn và focus khi mở/đóng Gói Combo.
Các kiểm thử này chạy trong CI hiện có qua liveTourAppointments.test.mjs.
JSDOM không đo layout/cuộn thực của trình duyệt; cần xác minh lại video thực
tế sau khi frontend được triển khai. Không suy ra tốc độ API từ bản sửa bố cục.
