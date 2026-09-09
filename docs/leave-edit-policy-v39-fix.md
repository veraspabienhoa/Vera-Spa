# Sửa lỗi không lưu được thay đổi lý do nghỉ

API `PATCH /v2/leave/records/{record_uid}` gửi `allow_inactive_employee` cho mọi vai trò: `True` với Admin và `False` với các vai trò khác. Bộ kiểm tra chuẩn đã hỗ trợ tham số này, nhưng lớp bọc `validate_with_late_month_cap` của V3.9 chưa nhận và chuyển tiếp nó. Vì vậy thao tác sửa dừng với HTTP 500 trước khi cập nhật PostgreSQL, kể cả Admin.

Bản sửa bổ sung tham số với mặc định `False` và chuyển tiếp nguyên giá trị đến bộ kiểm tra chuẩn. Quyền sửa, kiểm tra dữ liệu, giới hạn nghỉ có phép của người bắt đầu/làm lại từ ngày 16 và cơ chế commit/rollback vẫn dùng đường xử lý hiện tại. Tạo lịch mới tiếp tục mặc định chỉ nhận nhân viên hoạt động.

## Kiểm chứng

Kiểm thử gọi endpoint sửa thật qua FastAPI và lớp bọc V3.9 đã cài; database, xác thực và bộ kiểm tra cơ sở được thay bằng dữ liệu kiểm thử. Trước sửa, tái hiện đúng `unexpected keyword argument 'allow_inactive_employee'` trong 13 trường hợp. Sau sửa, cả 15 trường hợp hồi quy đạt: 7 vai trò đã được phép sửa, ngoại lệ nhân viên ngừng hoạt động chỉ cho Admin, từ chối thiếu quyền/dữ liệu không hợp lệ, giới hạn 3 ngày nghỉ cuối tháng và mặc định tạo mới.

```sh
python -m pytest -q tests/test_leave_edit_policy_v39.py tests/test_leave_record_update_permissions.py tests/test_leave_update_google_fallback.py tests/test_admin_manager_leave_policy.py tests/test_dynamic_letan_leave_policy.py tests/test_employee_leave_self_service_policy.py tests/test_payroll_timesoft_upload_fix.py
```

Kết quả: 37 test đạt. Đây là kiểm thử với dữ liệu giả lập, chưa phải nghiệm thu trực tiếp production. Nhánh sửa xuất phát từ `main` tại `7d333c4`, không phụ thuộc PR #33. Không cần migration; sau merge cần chạy Deploy VPS Production để API nhận bản sửa.
