# Báo cáo: kết quả tối ưu ngày 03-10-2026

Baseline: main 1d0d10fc9a8f26995bab2c484b23efa9941989b9. Deploy VPS run
37098678879 xác minh backend, health và frontend của commit này lúc 12:06 +07.
Video người dùng bắt đầu lúc 12:05; chưa xác định chính xác thời điểm browser
nạp bundle trong video. Không có trace Network/Performance hoặc SQL production.

## Nguyên nhân và thay đổi

- Tạo Intl.DateTimeFormat từng dòng, lọc invoices/reports/performance cả khi
  chỉ xem một tab. Dùng một formatter, chỉ lọc tập đang xem; memo theo dữ liệu
  và bộ lọc để mở hộp sửa không quét lại lịch sử.
- Default array props tạo lại gợi ý ở mọi render. Giữ tham chiếu ổn định,
  thay tìm khách hàng lồng nhau bằng Map. Tổng/export vẫn dùng đầy đủ bộ lọc.
- Preset ngày không xóa ô ngày riêng: chọn Tất cả vẫn bị lọc ngày cũ. Đã sửa.
- Sửa/hủy báo cáo chưa dùng read profile dành cho điều chỉnh hóa đơn và còn
  đọc lại board sau commit. Chuẩn hóa action chỉ ở tầng khóa/storage; UI dùng
  receipt, đóng editor khi đã commit và tải báo cáo riêng. Không bỏ ledger lock,
  quyền report/paid-invoice/date, revision, audit hoặc chống lưu trùng.
- Response đọc cũ không được ghi đè kết quả mới; đang tải lại thì tạm khóa nút
  mở điều chỉnh để không chủ động đưa người dùng vào bản hóa đơn cũ.

## Số đo trước/sau

Node v24.19.0, dữ liệu giả, 20 mẫu mỗi kích thước, một user; xen kẽ trước/sau.
Đo CPU phần chọn/lọc tab Doanh thu, chưa gồm DOM, React render, mạng hoặc VPS.
Đối chiếu kết quả trước/sau bằng deep equality. Không dùng response cache.

| Dòng mỗi tập | Dòng quét trước → sau | p50 ms trước → sau | p95 ms trước → sau | p50 tăng tốc |
|---|---|---|---|---|
| 100 | 300 → 100 | 12,535 → 0,170 | 13,821 → 0,286 | 73,7 lần |
| 1.000 | 3.000 → 1.000 | 122,706 → 1,580 | 141,115 → 2,389 | 77,7 lần |
| 3.000 | 9.000 → 3.000 | 362,494 → 4,332 | 443,692 → 5,485 | 83,7 lần |

| Tác vụ | HTTP trước/sau | SQL trước/sau | Ghi | Pool/lock | Payload | Lỗi/retry |
|---|---|---|---|---|---|---|
| Lọc dữ liệu đã nạp | 0/0 | 0/0 | 0/0 | Không dùng DB | 0/0 byte truyền | 0/0 trong benchmark |
| Mở hộp sửa | 0/0 | 0/0 | 0/0 | Không dùng DB | 0/0 byte truyền | Kiểm thử giao diện |
| Lưu và tải lại | 2/2 theo luồng mã | Chưa đo production | Giữ nguyên giao dịch nghiệp vụ | Chưa đo production | Chưa đo production | CI kiểm thử retry và nguyên tử |
| Mở trang, export | Không thay endpoint | Chưa đo production | Không đổi | Chưa đo | Không đổi định dạng API | Chưa benchmark VPS |

Các con số không chứng minh toàn trang/hệ thống nhanh 50 lần. API đọc ban đầu
vẫn trả tập báo cáo đầy đủ; nếu còn chậm ở bước tải, cần trace trên VPS trước
khi đổi sang phân trang/aggregate SQL, giữ tổng và export đúng phạm vi.

Tái lập: bundle helper trước sửa bằng esbuild (giữ các import cùng revision),
rồi tại web-v2 chạy `node scripts/benchmarkReportFilters.mjs /tmp/before.mjs`.
Script báo lần đo đầu và p50/p95; không coi lần đo đầu là cache nguội production.

## Nghiệm thu và triển khai

Kiểm thử frontend: ngày Việt Nam/UTC, dữ liệu legacy, chọn đúng tab, mở editor
không quét 3.000 ngày, receipt đóng dialog trước GET tải lại. Giữ kiểm thử tổng,
quyền, tiền/TIP và export hiện có. PostgreSQL CI mở rộng cả report update/delete
cho read scope, ledger, audit, idempotency trong hai mode receipt.

Không có migration hoặc xóa dữ liệu. Rollback bằng deploy commit trước.
Sau merge cần deploy cả thay đổi frontend và backend. Workflow Deploy VPS
Production hiện build và xác minh frontend cùng backend; xác minh commit mới
và thử đổi ngày, nhân viên, Xem/Sửa với quyền thực tế. Đo Network/Performance
20 lần cùng bộ lọc trước/sau nếu cần kết luận độ trễ người dùng trên VPS.
