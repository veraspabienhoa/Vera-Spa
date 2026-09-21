# Kiến trúc Quản lý Đào tạo & Đánh giá nhân viên

## 1. Tổng quan

Module dùng FastAPI + SQLAlchemy Core ở backend và React ở frontend. Dữ liệu nhân sự tiếp tục dùng bảng `employees` hiện hữu; trạng thái làm việc được đọc từ `payload."Trạng thái làm việc"` hoặc `payload.employment_status`. Chỉ `Đang làm việc`/`active` được đưa vào danh sách thao tác.

Quy tắc thẩm quyền được kiểm tra ở backend, không dựa vào dữ liệu do giao diện gửi:

| Người thực hiện | Nhóm được đào tạo/đánh giá |
|---|---|
| `leader` | `nhanvien` |
| `quanly` | `letan`, `locker`, `tapvu` |
| `admin` | Có quyền vận hành trực tiếp và thiết lập hệ thống |

## 2. Lược đồ dữ liệu

Các bảng được tạo idempotent bởi `_schema()` trong `vera_web_v2_training.py`.

| Bảng | Mục đích | Khóa/liên kết chính |
|---|---|---|
| `employees` | Tài khoản, vai trò, trạng thái nhân sự | `username`; `role`; trạng thái trong `payload` |
| `vera_training_session` | Nhật ký đào tạo hằng ngày | `employee_username`, `trainer_username`, ngày/giờ, thái độ, điểm A+–E, nhận xét, `status` |
| `vera_evaluation_cycle` | Đợt đánh giá tổng hợp | `status`: draft/active/closed |
| `vera_evaluation_assignment` | Phiếu giao cho từng cặp người đánh giá–nhân viên | FK `cycle_id`; unique theo cycle/employee/evaluator |
| `vera_employee_evaluation` | Điểm chi tiết của phiếu tổng hợp | PK/FK `assignment_id`; 7 tiêu chí 1–5; nhận xét |
| `vera_training_notification_recipient` | Người nhận bổ sung do Admin cấu hình | PK `username`, `active` |
| `vera_training_notification` | Hộp thư thông báo và deep-link | recipient, reference type/id, read state; unique recipient/reference |
| `vera_training_audit` | Nhật ký thay đổi | entity/action/actor/detail JSONB |

`reference_type` của thông báo nhận một trong hai giá trị `daily_training` hoặc `comprehensive_evaluation`; `reference_id` trỏ đến session hoặc assignment tương ứng.

## 3. API và kiểm soát quyền

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/v2/training/bootstrap` | Danh sách active theo phạm vi vai trò, sessions, assignments, evaluators và inbox |
| POST/PUT | `/v2/training/sessions` | Tạo/cập nhật đào tạo hằng ngày và kiểm tra đúng cặp vai trò |
| POST | `/v2/training/cycles` | Tạo đợt; chỉ sinh các assignment hợp lệ theo ma trận vai trò |
| PUT | `/v2/training/evaluations/{id}` | Lưu nháp hoặc hoàn thành đánh giá tổng hợp |
| GET | `/v2/training/reports/{employee}?evaluator_role=...` | Lịch sử hợp nhất, tiến độ kỹ năng và radar; lọc all/leader/quanly |
| PUT | `/v2/training/notification-recipients` | Admin thay danh sách người nhận bổ sung |
| GET | `/v2/training/notifications` | Hộp thư của tài khoản hiện tại |
| GET | `/v2/training/notifications/{id}/detail` | Đánh dấu đã đọc và trả nội dung để mở modal |

Mọi truy vấn chi tiết thông báo ràng buộc `recipient_username` với danh tính đăng nhập, nên không thể đổi ID để đọc thông báo của người khác.

## 4. Luồng hoàn thành và thông báo

1. Backend lưu bản ghi hoàn thành trong cùng transaction.
2. Dispatcher hợp nhất ba nhóm người nhận: tất cả Admin đang hoạt động, tài khoản được cấu hình, tài khoản nhân viên được đánh giá.
3. `UNIQUE(recipient_username, reference_type, reference_id)` và `ON CONFLICT DO NOTHING` bảo đảm gửi idempotent.
4. Frontend polling inbox mỗi 30 giây và hiển thị badge/toast.
5. Click thông báo gọi endpoint detail, đánh dấu đã đọc và mở modal ngay tại ứng dụng.

## 5. Thành phần giao diện

- `TrainingPage.jsx`: nhập đào tạo, phiếu đánh giá, lịch sử hợp nhất, bộ lọc evaluator, thiết lập người nhận và inbox.
- `PopupNotifications.jsx`: nhận thông báo toàn cục kể cả khi người dùng đang ở menu khác; click để mở chi tiết.
- `TrainingPage.css` và `styles.css`: timeline, badge phân loại, danh sách inbox và modal responsive.
