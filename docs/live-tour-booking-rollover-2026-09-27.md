# Booking và mốc ngày nghiệp vụ — 27-09-2026

## Bằng chứng và nguyên nhân

Người dùng gửi ảnh lỗi “Cấu hình đã đổi. Hãy làm mới rồi thử lại.” khi đặt
`90 PR VIP`, phòng VIP 20, giường 20.1, chưa chọn khách hàng. Video 9,4 giây
không có waterfall/timing nên không dùng để suy ra số request hay độ trễ API.
Deploy 36298048116 đã xác minh frontend/backend `1e215ece`, không chứng minh
booking hoạt động. Không tạo booking/hóa đơn thử trên production.

Resource writer không cho thao tác độc lập đổi `business_date`, trong khi
mọi action đều cập nhật trường này theo đồng hồ server. Mốc ngày nghiệp vụ
là **11:10 Asia/Ho_Chi_Minh**, khác mốc bộ đếm tua 10:00. Khi metadata còn
ngày trước, thao tác hợp lệ bị coi là đổi cấu hình. Tải lại GET không sửa lỗi.

[CI trước sửa](https://github.com/veraspabienhoa/Vera-Spa/actions/runs/36299337789)
tại `aacb8b8` tái hiện đúng HTTP 409 sau mốc này; 11:09:59 vẫn thành công.
Sáu kiểm thử mới thất bại đúng đường này, 1.850 kiểm thử còn lại đạt.
Chưa đọc metadata riêng của request lỗi trên VPS, nên không khẳng định đã
loại trừ mọi nguyên nhân có thể sinh cùng thông báo.

## Thay đổi

- Xếp ngày nghiệp vụ do server tính vào metadata vận hành được phép cập nhật.
- Gộp ngày bằng GREATEST trong UPDATE xuất bản revision hiện có. Hai thao tác
  độc lập qua mốc 11:10 commit ngược thứ tự không kéo ngày lùi lại.
- Không thêm câu SQL, mở thêm connection hay đổi phạm vi khóa. Giữ riêng
  cơ chế chuyển bộ đếm 10:00, phiên bản tài nguyên, cấu hình, idempotency,
  ghi tài chính và rollback. Không sửa schema/storage mode.
- Giao diện hiện có áp dụng board trả về sau booking, không gọi GET bổ sung
  cho phản hồi đó. Giữ draft và không tự retry 409 bằng dữ liệu cũ.

## Đo lường

Fixture: 42 nhân viên, booking PR tại 20.1, giá 350.000đ; 0 hoặc 3.000 dòng
trong **mỗi** bộ audit/invoices/reports. Mỗi trường hợp 10 mẫu tuần tự, giữ
cả mẫu đầu lạnh trong số liệu. Thời gian chuẩn bị/reset/xác minh ngoài cửa sổ
đo. Đây là HTTP trong tiến trình + PostgreSQL 16 trên CI, danh tính/quyền dùng
fixture; không gồm mạng trình duyệt, xác thực production hay tải nhiều user.

Số SQL là lần driver execute; dòng đọc là dòng trả về qua cursor, **không**
phải số dòng PostgreSQL quét hay số wire round trip. Dòng ghi gồm metadata,
employee, audit, board history và một audit cũ hết vòng khi đã đầy.

| Trường hợp trước sửa | HTTP/mẫu | SQL | Dòng trả về/ghi | p50/p95 (ms), n=10 | JSON byte | Kết quả |
|---|---:|---:|---|---|---:|---|
| Cùng ngày, không lịch sử | 1 POST | 14–19 | 298–299 / 4 | 22,77 / 67,37 | 87.082–87.083 | 200, 10/10 |
| Đổi ngày, không lịch sử | 1 POST | 7 | 195 / 0 | 8,41 / 8,74 | 72 | 409, 10/10 |
| Cùng ngày, 3.000 dòng/bộ | 1 POST | 14 | 298 / 5 | 24,75 / 26,20 | 87.083 | 200, 10/10 |
| Đổi ngày, 3.000 dòng/bộ | 1 POST | 7 | 195 / 0 | 9,94 / 13,03 | 72 | 409, 10/10 |

Response lỗi ngắn/nhanh không phải hiệu năng thành công. Không dùng 7 → 14
SQL để kết luận chậm hơn: phía cũ dừng trước khi ghi booking.

Số đo sau sửa nằm ở dòng `BOOKING_MEASUREMENT` trong bước
**Report isolated booking work measurements** của CI tại đúng commit.
[PR #312](https://github.com/veraspabienhoa/Vera-Spa/pull/312) ghi bảng đối chiếu
trước/sau và kết quả CI cuối cùng. Kiểm thử so sánh riêng các mẫu đã khởi tạo
để tránh trộn chi phí khởi tạo lần đầu với mức tăng lịch sử; báo cáo vẫn giữ
toàn bộ mẫu và chi phí lạnh.

| Phạm vi còn lại | HTTP/SQL/dòng/pool/lock/p50/p95/payload/lỗi |
|---|---|
| Mở Live Tour, bắt đầu, hoàn thành, thanh toán lẻ/combo, tìm kiếm, chuyển tab | Chưa đo thời gian hoặc request end-to-end trong đợt này; hồi quy nghiệp vụ chạy trong CI |
| Pool wait, lock wait, PostgreSQL rows scanned | Chưa đo tách riêng; kiểm thử tranh chấp/rollback không thay thế phép đo |
| VPS và trình duyệt thực | Chưa benchmark; không kết luận nhanh gấp X lần |

## Kiểm thử và deploy

`tests/test_live_tour_day_rollover_postgres.py` đi qua API thật/transaction
PostgreSQL, gồm trước/đúng/sau 11:10, retry cùng key, stale revision,
hai phòng độc lập, không lùi ngày, cấu hình thật vẫn bị chặn, rollback và
booking/multi-booking/start/finish/checkout. Hồi quy bắt buộc theo AGENTS.md
vẫn nằm trong toàn bộ CI, cùng lint/build Web V2.

Sau khi PR merge và CI đạt, người dùng tự chạy **Actions → Deploy VPS
Production → Run workflow → main**. Workflow kiểm tra đúng origin/main,
hai health và frontend/backend cùng SHA. Không dispatch VPS tự động từ PR.

Sau deploy, đối chiếu SHA trong run và thao tác booking hợp lệ tại phòng trống
trong công việc thật. Nếu còn lỗi, giữ nguyên form, ghi thời điểm và response
lỗi để phân biệt xung đột phòng/nhân viên với lỗi metadata. Không sửa ngày
database bằng tay, không đổi storage mode, không tắt khóa để né lỗi.
