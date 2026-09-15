# PostgreSQL resource concurrency

## Phạm vi

Hệ thống không còn được xem như chỉ có một nút thắt Live Tour. Các miền ghi dữ
liệu được chia theo invariant nghiệp vụ:

| Miền | Khóa nhỏ nhất | Ràng buộc giữ lại |
| --- | --- | --- |
| Nhân viên | `employee:<username>` | Một tài khoản không bị sửa đồng thời |
| Lịch nghỉ | `leave_employee:<employee>` và `leave_record:<uid>` | Thứ tự phạt tăng dần của cùng nhân viên ổn định |
| Live Tour | employee, room, pending, invoice, customer, combo | Không trùng phòng, hóa đơn, combo hoặc thanh toán |
| Payroll | kỳ lương | Các kỳ khác nhau không chặn nhau |
| Profile | username | Hai tài khoản khác nhau không chặn nhau |
| Nội quy/cấu hình | từng setting/document | Revision vẫn chống ghi đè bản mới |

Live Tour được tách thành các bảng vật lý riêng `vera_live_tour_employee`,
`vera_live_tour_room`, `vera_live_tour_service`, `vera_live_tour_combo`,
`vera_live_tour_customer`, `vera_live_tour_pending`, `vera_live_tour_invoice`
và các bảng report/event/change tương ứng. JSONB chỉ còn ở cấp một bản ghi để
giữ tương thích DTO. Trong `shadow`, aggregate cũ vẫn được ghi để rollback nhưng
phần mirror chỉ upsert các hàng thay đổi; việc bỏ rewrite aggregate chỉ diễn ra
sau cutover nguồn đọc/ghi relational.

## Cơ chế an toàn

- `vera_resource_concurrency.py` chuẩn hóa khóa và luôn lấy nhiều khóa theo một
  thứ tự duy nhất để tránh deadlock.
- `vera_business_mutation` lưu receipt idempotency dùng chung.
- `vera_resource_claim` dành cho tài nguyên độc quyền.
- `vera_resource_revision` lưu revision theo từng tài nguyên.
- `vera_business_counter` cấp số nguyên tử, thay cho `MAX()+1` có thể race.
- Claim phòng Live Tour có khóa chính theo `room_key`; một phòng không thể thuộc
  hai booking khác nhau trong cùng thời điểm.

## Trình tự cutover

1. Deploy ở `VERA_RESOURCE_LOCK_MODE=hybrid` và
   `VERA_LIVE_TOUR_RELATIONAL_MODE=shadow`.
2. Chạy `vera_vps_concurrency_schema.py --apply --verify`. Lệnh tạo schema,
   backfill và dừng ngay nếu hash Live Tour không khớp.
3. Theo dõi ít nhất một chu kỳ nghiệp vụ và chạy verify lại. Không bật nguồn
   relational nếu parity khác 100%.
4. Chỉ khi mọi tiến trình writer đã chạy cùng phiên bản mới, chuyển khóa hệ
   thống sang `resource`. Không bỏ khóa legacy trong rolling deploy.
5. Live Tour cần một cutover riêng từ `verify` sang nguồn relational; aggregate
   được giữ làm rollback snapshot trong giai đoạn đầu.

Các thao tác batch thật sự đụng toàn bộ dataset (import, xóa kèm reindex, restore)
vẫn dùng khóa miền rộng. Đây là chủ ý; chúng không được chạy song song với các
thay đổi cùng dataset.
