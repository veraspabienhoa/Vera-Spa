# Tối ưu hiệu năng toàn hệ thống — 08-10-2026

Bản gốc đối chiếu: `e734dd90c5ef588a07a5fd054650d0d05016d0f7`.
Triển khai các tối ưu nền dùng chung và các điểm đã xác định chắc chắn bằng mã.
Không cam kết toàn hệ thống nhanh 100 lần; độ trễ VPS và tải đồng thời cần đo sau deploy.

## Thay đổi đã triển khai

- **Lịch làm việc, Booking online, Đào tạo, sổ Doanh thu và ảnh hồ sơ**:
  thay DDL lặp lại bằng migration có phiên bản. Khi đã sẵn sàng, chỉ đọc bảng
  phiên bản, không lấy khóa advisory hay chạy ALTER TABLE. Không cache readiness
  trong process; rollback cả transaction/savepoint cũng rollback phiên bản.
  Dùng đúng kết nối của caller. Các bảng phiên bản được bảo vệ bằng RLS và thu
  hồi quyền PUBLIC/anon/authenticated. Deploy schema gate chuẩn bị các bảng;
  runtime vẫn tương thích DB chưa được nâng cấp qua migration một lần có khóa.
- **Lương hành chánh**: dùng chung dữ liệu tháng, cấu hình từng nhân viên,
  tiền phạt và ca cho một lần tính tổng hợp. Nhóm dữ liệu theo cùng hàm chuẩn hóa
  tên trước khi tính từng người. Đọc nhãn/cấu hình theo bộ phận, không đọc lại
  cho từng dòng khi tính/lưu bảng nháp. Giữ bộ phận của từng lịch cũ khi chuyển
  nhân sự, ca qua đêm, tăng ca, trạng thái thiếu bằng chứng, chính sách thử việc,
  tiền ứng và khấu trừ. Đồng hồ HH:MM/HH:MM:SS hợp lệ có đường parse ngắn;
  các định dạng cũ vẫn dùng bộ parse cũ.
- **Doanh thu realtime**: token thay đổi gồm bốn bộ đếm nhỏ, cập nhật cùng
  transaction với nguồn qua PostgreSQL triggers. Bao gồm imports, sửa, xóa mềm,
  xóa thật và truncate; thay đổi cài đặt ngoài revenue không làm tăng bộ đếm.
  SELECT thấy dữ liệu đã commit; rollback không tăng revision. Polling không
  còn COUNT/MAX/SUM toàn bộ lịch sử sau khi deploy gate cài trigger. DB chưa có
  migration vẫn dùng cách đọc cũ. Không dùng sequence độc lập transaction vì
  có thể làm UI nhận token trước khi dữ liệu commit.
- **Khởi động mọi trang**: SDK Supabase chỉ tải nếu thực sự gọi RPC dữ liệu cũ.
  Đăng nhập/refresh vẫn hoàn toàn qua API VERA. LayoutDesigner chuyển thành
  module riêng có Suspense, boundary và retry; vẫn áp dụng bố cục đã lưu cho
  mọi người. Không tắt layout hay thay màn hình mặc định.
- **Tác vụ DOM nền**: ba compatibility helpers của danh sách/hồ sơ chỉ theo dõi
  subtree liên quan, gộp các thay đổi vào một animation frame, bỏ timer 500/700/
  1200 ms, ngắt observer của root đã tháo. Bỏ qua mutation do chính helper tạo
  để tránh vòng lặp. Không bỏ cơ chế chống nhầm ảnh nhân viên.
- **Thông báo**: settings/break polling dùng poller chờ lần trước hoàn tất,
  ngừng khi tab ẩn, cập nhật khi quay lại. Inbox GET chỉ SELECT và lọc hết hạn
  theo ngày Việt Nam. Worker dọn tối đa 500 thông báo cũ/lượt, SKIP LOCKED,
  giữ pending push và các claim đang hoạt động. Phân quyền thông báo riêng tư,
  retry/deduplication và gửi mạng ngoài transaction được giữ nguyên.
- **Lịch làm việc/Thay đổi hệ thống**: dùng transport dùng chung có deadline,
  refresh session, gộp GET và hủy request. Thay bộ lọc/unmount hủy lần đọc trước;
  response cũ không thể ghi đè ngày/bộ phận mới. Lịch tháng, lịch đang xem và
  combo được lấy song song, chỉ cập nhật UI khi cùng lượt tải còn hiệu lực.
- **Imports và lương KTV**: Excel và DB của Nhập mua, lịch/ combo, nhân viên,
  lịch nghỉ, Nội quy, Doanh thu, Live Tour, ảnh hồ sơ và các lớp tính lương
  chuyển khỏi event loop sang thread pool có giới hạn của Starlette/AnyIO.
  ASGI vẫn đọc request body; từng worker sở hữu và đóng connection của nó.
  Không tự thử lại thao tác ghi và không chia sẻ connection giữa threads.
- **Hợp đồng**: lấy metadata CCCD của những nhân viên được phép xuất trong
  một truy vấn; không tải BLOB ảnh, OCR hay cập nhật hồ sơ khi xuất. Render PDF
  sau khi giải phóng transaction/connection. Hồ sơ thiếu thông tin vẫn bị từ
  chối như trước. Runtime hiện tại vốn đã tắt OCR tự động.
- **Nhân viên/Live Tour**: trả danh sách quyền từ một payload quyền đã đọc
  revision mới trên connection hiện tại. Không cache tài khoản/session; quyền
  bị thu hồi, khóa tài khoản, phạm vi self-service và kiểm tra ghi vẫn giữ nguyên.
- **Giao diện**: endpoint nhỏ `/v2/live-tour/appearance` chỉ đọc cấu hình và
  revision, không lấy toàn bộ hóa đơn, bản sao lưu hay cache idempotency.
  Giữ kiểm tra `live_tour_admin` và revision cho thao tác lưu hiện hữu.
- **Toàn bộ API**: ASGI middleware đo từ trước dependency xác thực tới cuối
  response, gồm SQL count/time, số byte response và latency histogram theo
  route template. Thêm `X-Request-ID` ngẫu nhiên do server tạo. Gộp metrics
  theo process, flush mỗi phút có traffic; log request từ 1000 ms hoặc lỗi 5xx.
  Không log raw URL/query, tên người, body, token, SQL/params hay exception text.

## Đo cục bộ, không phải độ trễ production

`python scripts/benchmark_system_performance.py --baseline e734dd90 --samples 20`

Python 3.12, một caller tuần tự, dữ liệu giả 31 ngày/người. Đo hàm tổng hợp
ca, bao gồm chi phí tạo nhóm trong bản mới. Không có SQL/network/DOM. So sánh
mọi kết quả trả về trước khi đo; tất cả bằng nhau.

| Nhân viên | Dòng lịch | p50 cũ (ms) | p50 mới (ms) | p95 cũ (ms) | p95 mới (ms) | Tỷ lệ p50 |
|---|---:|---:|---:|---:|---:|---:|
| 15 | 465 | 53.057 | 5.297 | 83.672 | 6.228 | 10.02× |
| 60 | 1.860 | 463.228 | 20.606 | 507.531 | 21.379 | 22.48× |
| 200 | 6.200 | 4184.899 | 71.427 | 4582.546 | 84.091 | 58.59× |

Tệp JS entry build cũ 916.129 byte; build mới khoảng 468 KB (giảm khoảng 49%).
Đây là kích thước entry, không phải tổng mọi module tải sau đăng nhập. SDK cũ
và LayoutDesigner có chunk riêng; không cộng tỷ lệ này với tỷ lệ CPU phía trên.
Warm schema schedule từ 19 execute calls (10 ALTER) xuống 2 SELECT; booking
existing schema từ 4 calls (khóa + 2 ALTER) xuống 2 SELECT. Execute calls không
đồng nghĩa với số roundtrip/statement bên trong PostgreSQL.

## Kiểm tra và triển khai

Các regression mới kiểm tra: rollback/cạnh tranh migration trên PostgreSQL,
readiness không DDL/khóa khi đã nâng cấp, token chỉ đổi sau commit, nhiều nguồn
viết/rollback/truncate, lương theo nhóm bằng quét cũ, chỉ đọc input tháng một
lần, request metrics không chứa dữ liệu riêng, Excel không chặn request khác,
PDF không giữ connection, response cũ không ghi đè bộ lọc mới, observer không
chạy trên trang khác/không tự lặp. CI có PostgreSQL 16 biệt lập để chạy các bài
không thể chạy trong workspace thiếu DB. Giữ các gate auth/attendance/outbox/
runtime diagnostics, mọi test cũ và build/lint.

Deploy backend bằng workflow **Deploy VPS Production** tại đúng main đã merge.
Gate schema chạy migration đọc trong transaction riêng ngắn; backfill hiện hữu
và cài trigger revision ở các transaction tách biệt, có lock/statement timeout.
Không đổi cơ chế deploy hay tự chạy workflow production trong lượt cập nhật mã.
Frontend mới dùng endpoint appearance mới, vì vậy cần deploy backend tương ứng.

Sau deploy kiểm tra SHA frontend/backend, cả `/v2/auth/health` và `/v2/health`,
rồi thực hiện đọc lịch/booking, tính nháp lương, tải ảnh hồ sơ, đổi ngày liên tục,
nhận đúng thông báo, Doanh thu cập nhật sau ghi, xuất hợp đồng và một import
kiểm soát. Đối chiếu số tiền/xuất Excel với mẫu chuẩn. Không benchmark hàng loạt
thao tác ghi trên dữ liệu thật.

Log `VERA_REQUEST_METRICS` có histogram không cộng dồn với cận ms:
50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, +∞ (key 0..9).
Đây là histogram theo process, chưa phải p95 chính xác hay pool-wait/lock-wait
riêng. Dùng `VERA_REQUEST_SLOW` và Request-ID để tìm route cần đo sâu hơn;
không bật log SQL params để đo.

## Các thay đổi cấu trúc cần số đo/parity tiếp theo

Bản này chưa thay cách đánh số hóa đơn hoặc khóa ledger; chưa chuyển toàn bộ
bộ lọc lịch sử/báo cáo sang SQL/read model; chưa thêm cache ảnh thiết bị hay
bulk mutation API cho nhiều hồ sơ. Các phần này cần baseline runtime, EXPLAIN,
mẫu dữ liệu lịch sử đầy đủ và kiểm tra mọi writer trước khi thay cấu trúc.
Không cắt bớt lịch sử, không trả tổng chỉ của một trang, không thêm cache dùng
chung dữ liệu cá nhân, và không công bố đạt mục tiêu 100× toàn hệ thống.
