# Live Tour — quyền và điều chỉnh hóa đơn

## Phạm vi

Trong **Phân quyền → Live Tour**, admin cấp theo nhóm hoặc ghi đè từng tài khoản.
Giao diện và API dùng cùng quyền hiệu lực; không chỉ ẩn nút. Nhánh này không tự merge hoặc deploy.

| Chức năng | Quyền | Điều kiện bổ sung |
| --- | --- | --- |
| Mở bảng | `live_tour_view` | — |
| Đặt booking / hàng loạt | `live_tour_booking` | Xem Live Tour; thực hiện ngay cần `live_tour_operate` |
| Xem mục Chờ thanh toán | `live_tour_pending_view` | Xem chi tiết cần `live_tour_invoice_view` |
| Xem hóa đơn chờ | `live_tour_invoice_view` | Chờ thanh toán |
| Sửa hóa đơn chờ | `live_tour_invoice_edit` | Cả hai quyền xem hóa đơn chờ ở trên |
| Xóa hóa đơn chờ | `live_tour_invoice_delete` | Cả hai quyền xem hóa đơn chờ ở trên |
| Xem / in hóa đơn đã thanh toán | `live_tour_paid_invoice_view` | Mục Hóa đơn đã thanh toán |
| Sửa hóa đơn đã thanh toán | `live_tour_paid_invoice_edit` | Xem hóa đơn đã thanh toán |
| Xóa / hủy hóa đơn đã thanh toán | `live_tour_paid_invoice_delete` | Xem hóa đơn đã thanh toán |
| Khách hàng & combo | `live_tour_customers_view` | Đổi hồ sơ, bán combo vẫn cần `live_tour_payment` |
| Xem báo cáo | `live_tour_reports_view` | Không đòi quyền thanh toán hay xuất file |
| Xem lịch sử | `live_tour_history_view` | Chi tiết sửa/hủy hóa đơn cần thêm quyền xem loại hóa đơn đó |
| Tạo / khôi phục sao lưu | `live_tour_backup` | Không cấp kèm quyền quản trị danh mục |
| Xuất Excel / PNG | `live_tour_export` | Mỗi loại dữ liệu cần quyền xem tương ứng |

Booking có thông tin khách / combo và thanh toán có thông tin khách hoặc trừ vé
cần thêm `live_tour_customers_view`. Thanh toán tiền mặt từ phiếu đã lưu có thể giữ
nguyên khách gốc mà không gửi lại thông tin khách. Xuất chi tiết khách hàng cần đủ
quyền khách hàng, báo cáo, hóa đơn chờ và hóa đơn đã thanh toán vì file chứa các sổ này.

## Giữ cấu hình phân quyền cũ an toàn

Các quyền đọc mới chưa có cấu hình riêng kế thừa **quyền cũ hiệu lực**, kể cả
ghi đè từ chối của tài khoản: booking từ vận hành; hóa đơn, khách hàng, báo cáo
từ thanh toán; lịch sử/sao lưu từ quản trị. Khi đã lưu quyền mới, cờ mới có hiệu lực
độc lập. Thứ tự: admin → ghi đè tài khoản → ghi đè nhóm → kế thừa cũ/mặc định.

Bốn quyền sửa/xóa hóa đơn chờ/đã thanh toán **mặc định tắt với mọi nhóm không phải
admin**, không kế thừa quyền thanh toán hay quản trị cũ. Admin luôn có đầy đủ quyền.
Không tự cấp quyền thực tế cho bất kỳ tài khoản không phải admin nào trong lần cập nhật này.

## Hóa đơn chờ thanh toán

- Xem chi tiết; sửa dịch vụ/số lượng, giá dòng, ghi chú; xóa phiếu với lý do bắt buộc.
- Khách hàng, nhân viên, phòng, thời điểm hoàn thành giữ nguyên để không gán nhầm dịch vụ.
- Dịch vụ không đổi giữ giá đã lưu, kể cả khi giá danh mục đã đổi. Dịch vụ mới dùng giá danh mục và có thể chỉnh giá dòng.
- Đổi dịch vụ kiểm tra lại vé giữ chỗ, không lấy vé của booking/phiếu khác.
- Xóa giải phóng giữ chỗ, không trừ/hoàn vé đã dùng, không sửa doanh thu đã thu.
- `pending_changes` lưu trước/sau, người, thời gian, lý do; không mất bản gốc.

## Hóa đơn đã thanh toán

- Mục riêng hiển thị tối đa 500 hóa đơn còn hiệu lực gần nhất.
- Sửa giá từng dòng, giảm giá theo số tiền, TIP, ghi chú và chuyển giữa tiền mặt/chuyển khoản/thẻ.
- Không đổi khách, nhân viên, dịch vụ/số lượng, ngày kinh doanh, số bill hoặc chuyển qua lại COMBO. Nếu cần đổi, hủy rồi lập lại.
- Tổng tiền và phân bổ báo cáo/TIP được tính lại trên server, giữ nguyên định danh và ngày gốc. Sửa tiền không trừ vé thêm.
- Combo trả trước theo thành phần không thu lại doanh thu dịch vụ khi dùng lượt: tổng thu chỉ là TIP, không giảm giá lần hai.
- “Xóa” là **hủy có lưu đối soát**. Loại hóa đơn/báo cáo/lượt dùng khỏi sổ có hiệu lực, lưu bản gốc và các sổ liên quan trong `invoice_changes`.
- Hủy lượt dùng combo hoàn đúng số vé/thành phần từ lịch sử trừ vé gốc, không dùng danh mục hiện tại để đoán. Sổ vé không khớp thì từ chối toàn bộ.
- Hủy hóa đơn bán combo chỉ khi combo chưa dùng và không có booking/phiếu giữ chỗ. Combo đã hủy không còn khả dụng.
- Số bill đã hủy không được tái sử dụng, kể cả nhập tay. Không tự đưa dịch vụ đã hoàn thành về bảng tua.
- **Không tự hoàn tiền ngân hàng/thẻ**. Nhân viên phải đối soát thu/hoàn tiền thực tế riêng.

## Lưu trữ và an toàn

Mọi thay đổi chỉ dùng dữ liệu server, cùng transaction/advisory lock/revision và
idempotency của Live Tour. Mẫu sửa giữ revision lúc mở, không âm thầm ghi đè bản
mới sau lỗi xung đột. Sửa/hủy bắt buộc lý do; gửi lại không sửa/hủy hay hoàn vé lần hai.
Kiểm tra quyền trước cả nhánh retry. Retry thanh toán không trả hóa đơn đã bị hủy
để in nhầm. Khôi phục sao lưu không quay lùi sổ tiền/vé hoặc xóa lịch sử điều chỉnh.

API lọc dữ liệu ở tất cả alias, kết quả thao tác lồng nhau, lịch sử khách hàng,
cache trình duyệt và export. Thông tin hóa đơn bị từ chối không được cấp vòng qua
quyền quản trị danh mục hoặc thanh toán cũ.

## Kiểm thử / triển khai

Kiểm thử mới ở `tests/test_live_tour_invoice_permissions.py`; cập nhật các bài kiểm
quyền cũ sang quyền tách mới. Chạy nhóm `test_live_tour*`, `test_spa_management.py`,
`test_service_catalog.py`, build frontend và ESLint các file thay đổi.

Toàn bộ pytest còn 7 lỗi đã có trên main trước thay đổi này: kiểm tra nguồn đồng bộ
TimeSoft, kiểm tra nguồn thông báo lịch nghỉ, phân loại vi phạm và 4 fixture auth
chưa cấu hình PostgreSQL. Không sửa các phần không liên quan trong nhánh này.

Không cần đổi schema, không đồng bộ file ngoài. Sau khi được duyệt và deploy,
admin mở Phân quyền, chọn nhóm/tài khoản rồi bật các quyền sửa/xóa cần thiết.
