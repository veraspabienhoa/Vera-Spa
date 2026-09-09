# Live Tour: Thực hiện và Hoàn thành theo nhân viên/phòng

- Thêm hai nút **Thực hiện**, **Hoàn thành** cạnh tên nhân viên trong bảng và trong danh sách chi tiết phòng. Không cần đánh dấu chọn trước khi thao tác riêng lẻ.
- Thêm hai nút trên từng thẻ phòng và phần đầu chi tiết phòng. Số cạnh nút là số nhân viên có trạng thái phù hợp trong phòng đó. Bấm phần thông tin phòng vẫn mở booking như trước.
- **Thực hiện cả phòng** (`start_room`) chuyển các dịch vụ Đang chờ trong phòng sang Đang thực hiện, ghi giờ bắt đầu và số tua/YC theo quy tắc hiện có. Không bắt đầu lại dịch vụ đang thực hiện.
- **Hoàn thành cả phòng** (`finish_room`) chỉ hoàn tất dịch vụ đang thực hiện, chuyển sang Chờ thanh toán và giải phóng nhân viên/phòng. Giữ nguyên lịch đang chờ, dịch vụ đã chờ thanh toán và người ở phòng khác. Giữ từng phiếu với đúng khách hàng, không gộp khách khác nhau thành một phiếu.
- Server xác định toàn bộ giường thuộc phòng từ cấu hình khu vực và trạng thái đã lưu. Thao tác cả phòng bao gồm phiên đang ẩn và phiên cũ còn mở ngoài danh sách nhân viên; không phụ thuộc tìm kiếm, bộ lọc ca hoặc các checkbox đang chọn ở bảng. Tên phòng tùy chỉnh được gửi nguyên văn, không bỏ tiền tố “Phòng”.
- Các thao tác dùng quyền `live_tour_operate`; số lượng theo phòng không được trả cho người thiếu quyền này. Thông tin khách hàng vẫn được che nếu thiếu quyền thanh toán.
- Cả phòng xử lý nguyên tử: nếu có người không thể chuyển trạng thái, không ai trong phòng bị thay đổi. Revision ngăn thao tác trên dữ liệu cũ, idempotency key ngăn gửi lại ảnh hưởng booking tiếp theo của cùng phòng.
- Nút không có người phù hợp hoặc đang gửi yêu cầu sẽ bị vô hiệu hóa. Thanh điều khiển đổi nhãn “Bắt đầu đã chọn” thành **Thực hiện đã chọn**.
- Không thay đổi schema, nguồn dữ liệu hoặc kết nối file ngoài.

## Kiểm tra

291 test liên quan đạt, gồm 10 trường hợp mới: phòng nhiều trạng thái, dòng ẩn, tách khách hàng, tên khu vực tùy chỉnh, không tác động phòng khác, rollback, retry trên booking mới, quyền HTTP và giữ đúng phạm vi trong handler giao diện.

```sh
python -m pytest -q tests/test_live_tour*.py tests/test_spa_management.py tests/test_service_catalog.py tests/test_global_open_new_tab.py tests/test_tour_room_availability.py tests/test_tour_leave_sync.py --tb=short
```

`web-v2`: `npm run lint` và `npm run build` đạt; còn 3 cảnh báo lint và cảnh báo chunk lớn có sẵn. Chưa kiểm tra giao diện trực tiếp trên production.
