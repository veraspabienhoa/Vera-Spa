# Kiến trúc Đào tạo, Đánh giá & Nhân sự V2

## 1. Kiến trúc tổng quan

Hệ thống giữ nguyên hai nguồn dữ liệu đang vận hành:

- `employees` là danh mục tài khoản và vai trò; mọi tên hiển thị trong module đào tạo dùng `username`.
- `vera_phase14_record(dataset='long_leave')` là nguồn chuẩn của đơn Phép năm/Nghỉ dài hạn.
- `vera_dataset_cache(timesoft_employee_checkin_*)` là nguồn chứng cứ chấm công TimeSoft.

Các bảng mới là projection/index và audit. Chúng không thay thế nguồn chuẩn, nhờ đó tương thích với ứng dụng cũ nhưng vẫn cho phép truy vấn heatmap và xử lý sự kiện nhanh.

## 2. Data models

### Đào tạo và đánh giá

| Model nghiệp vụ | Bảng triển khai | Index chính |
|---|---|---|
| `evaluation_periods` | `vera_evaluation_cycle` | `(start_date, end_date)` |
| Assignment | `vera_evaluation_assignment` | `(employee_username, status)`, `(evaluator_username, status)` |
| `evaluations` | `vera_employee_evaluation` | `submitted_at DESC` |
| Daily training | `vera_training_session` | `(employee_username, training_date DESC)`, `(trainer_username, training_date DESC)` |
| Notification | `vera_training_notification` | recipient/read/created |

Xếp loại được tính thống nhất:

- Đào tạo: A+/A = Xuất sắc, B = Tốt, C = Trung bình, D/E = Yếu.
- Tổng hợp: trung bình ≥4.5 = Xuất sắc; ≥3.5 = Tốt; ≥2.5 = Trung bình; còn lại = Yếu.

### Nghỉ phép và chấm công

| Model nghiệp vụ | Bảng triển khai | Vai trò |
|---|---|---|
| `leaves` | `vera_phase14_record` + `vera_hr_leave_period` | Phase-14 là nguồn chuẩn; HR period là projection ngày chuẩn hóa |
| `attendance_logs` | `vera_hr_attendance_log` | Nhật ký check-in idempotent, unique username/time/source |
| Return audit | `vera_hr_leave_return_audit` | Lưu trước/sau, nguồn và attendance event |

`vera_hr_leave_period` có index username/created, department/date-range và status/date-range để heatmap không phải quét JSON mỗi lần.

## 3. Backend services và API

### Lịch sử đánh giá

`GET /v2/training/reports/{username}` hỗ trợ:

- `q`: tiêu đề đợt, ghi chú, nhận xét hoặc username người đánh giá.
- `date_from`, `date_to`.
- `rating`: `excellent|good|average|weak`.
- `evaluator_role`: `all|leader|quanly`.
- `page`, `page_size`.

`GET /v2/training/evaluations/{assignment_id}/export.pdf|png` tạo tài liệu phía server. Cả hai định dạng chứa thông tin chung, xếp loại, nhận xét và biểu đồ cột 7 tiêu chí.

Khi tạo cycle, dispatcher gửi một thông báo idempotent đến tập hợp username nhân viên và người đánh giá. Thông báo `evaluation_cycle` mở được modal chi tiết như thông báo kết quả.

### Check-in và tự kết thúc nghỉ

`record_checkin()` thực hiện trong một transaction:

1. Insert `vera_hr_attendance_log` với unique key chống xử lý lặp.
2. Tìm kỳ nghỉ đã duyệt chứa ngày check-in.
3. Nếu chưa có manual override, cập nhật `Ngày quay lại làm việc`, trạng thái `Đã kết thúc`, nguồn và timestamp trong bản ghi chuẩn.
4. Cập nhật projection và ghi audit.

`POST /v2/hr/attendance/check-in` cho phép Admin/Quản lý đẩy một event chuẩn hóa. Luồng đọc cache TimeSoft cũng gọi cùng service, nên dữ liệu thực tế tự hội tụ mà không phụ thuộc người dùng mở form nghỉ phép.

Manual return-to-work ghi `Nguồn kết thúc kỳ nghỉ=manual`; lần đồng bộ sau không ghi đè điều chỉnh rõ ràng của Admin.

### Phân tích trùng lịch

`GET /v2/hr/leaves/overlap?start=...&end=...&department_id=...&threshold=0.2`

Kết quả trả theo từng ngày và bộ phận: headcount, số người nghỉ, tỷ lệ, usernames, request metadata và cờ vượt ngưỡng. Khoảng truy vấn tối đa 93 ngày.

## 4. Frontend components

- `UsernameAutocomplete`: tìm username/role, dùng được single và multiple selection.
- `TrainingPage`: bộ lọc lịch sử kết hợp; badge xếp loại; nút tải PDF/PNG cho từng đánh giá.
- `LongLeaveAdminPanel`: heatmap theo ngày/bộ phận, ngưỡng tùy chỉnh và cảnh báo ngay trong card đơn chờ duyệt.

## 5. Tính nhất quán và an toàn

- Backend luôn kiểm tra cặp vai trò, không tin dữ liệu lọc từ frontend.
- Export tuân theo quyền xem báo cáo hiện hữu.
- Notification và attendance event đều có unique constraint để retry an toàn.
- Check-in, đóng kỳ nghỉ và audit cùng transaction PostgreSQL.
- Projection có thể tái tạo từ dữ liệu chuẩn bằng `sync_leave_periods()`.
