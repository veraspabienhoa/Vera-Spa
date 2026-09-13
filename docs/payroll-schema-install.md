# Cài bảng lịch sử lương

Vite 6.4.3 đã có trong package.json. esbuild 0.25.12 được khai báo trực tiếp
vì các test import nó; package-lock.json được cập nhật bằng npm.
Chạy `npm ci` trong web-v2 để cài đúng phiên bản, sau đó `npm run build`.

`vera_vps_payroll_schema.py --apply` đọc cấu hình runtime giống công cụ
vera_vps_data_check.py, tạo đúng đoạn DDL payroll trong schema.sql khi bảng
chưa có. Có giới hạn thời gian khóa/truy vấn, giao dịch rollback khi lỗi và
RLS cho bảng mới. Không cấp quyền public, không backfill hoặc xóa dữ liệu.
Nếu bảng đã có nhưng sai kiểu/cột, dừng để rà soát thay vì sửa phá dữ liệu.
Chạy không có --apply chỉ kiểm tra, không tạo bảng.

Workflow Deploy VPS Production kiểm tra SHA rồi chạy migration trước bước
kiểm tra dữ liệu. Migration có thể thất bại nếu tài khoản runtime không có
quyền CREATE; không nâng quyền tự động. Không chạy toàn bộ schema.sql lên VPS.

Kiểm chứng cục bộ: 1047 Python tests, build và lint (1 warning cũ),
24 test auth frontend đạt. Chưa có PostgreSQL thử nghiệm trong môi trường này;
test migration là mô phỏng, chưa xác minh DDL trên database thật.
Chưa push/merge/deploy. Sau deploy cần PAYROLL SCHEMA: verified, không còn
payroll_history_rows=missing, rồi kiểm tra lưu/đọc kỳ lương bằng tài khoản có quyền.
