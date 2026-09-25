> Integration follow-up: see [monthly-leave-cache-retention.md](monthly-leave-cache-retention.md) for the production modules, migration, automated schedule and tests. The examples below remain reference implementations.

# Tăng tốc VERA SPA — 25-09-2026

Stack xác nhận từ repository: React 18/Vite 6; Python/FastAPI, SQLAlchemy/psycopg;
PostgreSQL; VPS/systemd/Nginx, GitHub Actions; hàng đợi PostgreSQL cho projection.
Redis chưa được xác nhận là dịch vụ đang chạy và không phải điều kiện để sửa lỗi.

Phân biệt: PR 274 là bản sửa runtime. Các file `examples/performance/` là bộ mã
tham chiếu có kiểm thử, chưa tự cài endpoint/cache/cron hoặc thực thi index trong
production. Không coi việc thêm ví dụ vào repository là đã triển khai các chức năng đó.

## Phần 1 — Lộ trình ưu tiên

| Ưu tiên | Thay đổi | Trạng thái/phạm vi |
|---|---|---|
| 1 | Bỏ đọc cả Live Tour khi chỉ cần giờ đi trễ/về sớm; TIP chỉ đọc reports | PR 274 |
| 1 | Không khởi tạo chồng request danh sách theo mỗi revision bảng tua; hủy bộ lọc cũ | PR 274 |
| 1 | GET có thời hạn; không tự lặp khi timeout hoặc bị hủy | PR 274; không áp dụng cơ chế này cho thanh toán |
| 1 | Chuẩn hóa sau phân trang, đưa xử lý JSON ẩn tài khoản khỏi event loop | PR 274 |
| 2 | Endpoint lịch nghỉ theo đúng một tháng, phân trang 50/100 dòng | Mã tham chiếu `month_api.py`, cần nối vào UI và đường invalidation trước bật |
| 2 | Phân trang/filter SQL cho hóa đơn; index theo bộ lọc thực tế | Chưa có trong PR 274; cần benchmark và kiểm thử đối chiếu dấu tiếng Việt, múi giờ, tổng báo cáo |
| 2 | Tách đọc báo cáo/Excel khỏi critical section; chuyển các route async chứa SQL đồng bộ sang worker | Cần kiểm tra từng route; không thay đổi hàng loạt chỉ dựa vào từ khóa async |
| 3 | Cache đọc có giới hạn, chống nhiều request cùng dựng cache | `read_cache.py` hoàn chỉnh, chưa bật cache mới trong production |
| 3 | Dọn tác vụ projection đã hoàn tất sau 72 giờ | Script dry-run, script index và cron mẫu; chưa cài lịch tự chạy |

Không gộp bảng tua, hóa đơn, báo cáo và lịch sử thành một response lớn. Chỉ gộp các
lookup nhỏ mà cùng một màn hình cần ngay. Lazy load panel đang mở; debounce nhập
180–300 ms; tối đa một lượt đọc nền cho mỗi panel. Không retry POST tài chính bằng
request key mới. Khi dữ liệu đang tải, không hiển thị “không có hóa đơn” như kết quả cuối.

Đo trước/sau cùng bộ lọc và lượng dữ liệu: p50/p95/p99 latency, số request/thao tác,
byte JSON, số câu SQL, thời gian giữ connection/transaction, CPU/RSS, tỷ lệ 5xx.
Mục tiêu đề xuất: phần lớn đọc danh sách p95 < 1 giây; trả kết quả thanh toán sau
commit, không chờ render báo cáo. Đây là mục tiêu nghiệm thu, không phải số đã đạt.
Health xanh không chứng minh tất cả màn hình nhanh.

## Phần 2 — Backend theo tháng và chính sách hóa đơn

### API lịch nghỉ

File đầy đủ: [`month_api.py`](../examples/performance/month_api.py).

```python
from examples.performance.month_api import install_month_api
invalidate_leave_reads = install_month_api(
    app, engine_instance=_engine_instance, current_identity=current_identity,
    require_feature=_require_feature, feature_allowed=_feature_allowed,
)
# GET /v2/leave/month-records?month=2026-09&page=1&page_size=50
```

Câu WHERE chỉ từ ngày đầu tháng đến trước ngày đầu tháng sau; không tải tháng
trước, không chạy EXTRACT trên cột ngày, không SELECT *. Đọc 51 dòng để trả 50 dòng
và `has_more`, tránh COUNT toàn bảng. Chọn tháng mới phải hủy request tháng cũ,
reset trang 1 và không prefetch tháng trước. Với số trang rất sâu, đổi sang cursor
(leave_date, employee_name, record_uid) thay OFFSET.

Sau tạo/sửa/xóa/import thành công, gọi `invalidate_leave_reads()` **sau commit**.
Không nối cache vào production nếu còn đường ghi chưa invalidation. Tính hạn mức/
phép năm/tiền phạt vẫn dùng dữ liệu canonical trong giao dịch, không lấy quyết định
nghiệp vụ từ cache danh sách. Báo cáo lịch sử khi người dùng chủ động yêu cầu là
luồng riêng, không phát sinh tự động khi đăng ký tháng hiện tại.

### Hóa đơn lẻ và combo — theo xác nhận mới nhất

| Trường hợp | Hành vi |
|---|---|
| Hai giao dịch lẻ khác nhau, cùng khách/dịch vụ/số tiền | Cho phép; không chặn chỉ vì nội dung giống nhau |
| Gửi lại cùng request key của một lần thanh toán | Trả lại kết quả cũ, không tạo hóa đơn mới |
| Cùng key nhưng đổi nội dung/actor/action | Từ chối xung đột |
| Hóa đơn có dùng vé combo, kể cả hóa đơn trộn | Khóa nguồn vé, kiểm tra reservation/balance, trừ vé đúng một lần |
| Mua một gói combo mới | Giữ tính nguyên tử giữa hóa đơn và gói được cấp |

Mã phân loại: [`invoice_policy.py`](../examples/performance/invoice_policy.py).
Phân loại từ dòng booking đã đọc và khóa trên server; không tin `is_combo` do trình
duyệt gửi. PR 274 không bỏ idempotency tài chính. Bộ nhớ chống trùng không được đặt
TTL ba ngày vì một request thanh toán cũ gửi lại vẫn phải được nhận diện.

Luồng transaction:
1. Kiểm tra session/quyền, nhận request key ổn định cho một lần bấm thanh toán.
2. Khóa tài nguyên liên quan; đọc canonical booking và combo.
3. Kiểm tra replay key + actor/action/payload hash.
4. Kiểm tra số dư/reservation combo nếu có, rồi ghi hóa đơn, báo cáo, trừ vé và receipt
   trong cùng transaction. Hóa đơn lẻ không chạy tìm hóa đơn có nội dung giống nhau.
5. Commit rồi trả receipt; notification và tải bảng/báo cáo thực hiện sau.

## Phần 3 — SQL, index và giữ log kỹ thuật ba ngày

[`indexes.sql`](../examples/performance/indexes.sql) có CREATE INDEX và câu EXPLAIN.
VERA đã có index `(leave_date, employee_name)` và `(employee_name, leave_date DESC)`;
không tạo thêm index tương đương chỉ để tăng số lượng. Cột equality thường đứng
trước range/order; partial index phải có điều kiện phù hợp WHERE; tránh index tất cả
cột JSON. Với bộ lọc text không dấu, cần thống nhất cột chuẩn hóa và biểu thức SQL
trước khi chọn B-tree/trigram; không giả định B-tree tăng tốc `%chuỗi%`.

Chạy CREATE INDEX CONCURRENTLY bằng autocommit, ngoài transaction; kiểm tra
`indisvalid` nếu bị gián đoạn. Không chạy EXPLAIN ANALYZE trên mutation production.
Index tăng chi phí ghi nên chỉ thêm sau khi kiểm tra query plan, kích thước và lưu lượng.

Theo lựa chọn của chủ hệ thống, **chỉ giữ log kỹ thuật/tác vụ đã hoàn tất 72 giờ**.
Không xóa hóa đơn, báo cáo, combo, receipt chống trùng, lịch sử sửa/xóa hay lịch nghỉ.
Script hiện chỉ dọn queue `live_tour_projection`, status `done`, không còn lease;
không đụng retry/failed/processing hoặc hàng đợi thanh toán.

```bash
# Xem trước số dòng, không xóa:
cd /opt/vera-spa/current
/opt/vera-spa/.venv/bin/python -m examples.performance.technical_retention
# Áp dụng đúng phạm vi đã kiểm tra:
/opt/vera-spa/.venv/bin/python -m examples.performance.technical_retention --apply
```

Cron mẫu [`retention.cron`](../examples/performance/retention.cron) chạy mỗi giờ,
có flock và timeout. Script xóa từng batch 500, SKIP LOCKED, giới hạn thời gian và
số batch; backlog lớn có thể cần nhiều lượt. Đây là 72 giờ trượt, không phải xóa theo
mốc 00:00. Autovacuum thu hồi tuple chết cho tái sử dụng; DELETE không bảo đảm file
trên đĩa nhỏ lại ngay. Không chạy VACUUM FULL trong giờ làm việc.

Log Nginx/journal chưa được script này xóa. Muốn giữ đúng ba ngày cần chính sách
rotation riêng cho log VERA; không vacuum toàn bộ journal hệ điều hành để xử lý log
của một ứng dụng. Lịch cron mẫu chưa tự được cài chỉ bởi deploy mã.

## Phần 4 — Cache backend hoàn chỉnh và cache trình duyệt

[`read_cache.py`](../examples/performance/read_cache.py) cung cấp:
- TTL, LRU, giới hạn 128 key/8 MB; cache JSON độc lập, không trả object dùng chung.
- Một loader cho các request đồng thời cùng key; chờ không giữ connection DB.
- Invalidation có generation: lượt đọc cũ không thể ghi cache ngược sau khi lưu mới.
- Lỗi không được cache; keys có caller/quyền/tháng/bộ lọc/trang.

`month_api.py` minh họa dùng cache 5 giây và trả hàm invalidation. Session và quyền
vẫn kiểm tra mỗi request; thu hồi quyền có hiệu lực dù dữ liệu đọc còn trong cache.
Dữ liệu tài chính, quyết định quota, session và thao tác ghi không dùng cache này.

Cache này dùng trong **một process**. Khi chạy nhiều process/host, cần shared
generation/Redis hoặc phát invalidation tới mọi process; TTL không phải bảo đảm
read-your-writes giữa các process. Chưa thêm Redis vì chưa đo được nhu cầu và chưa
xác nhận hạ tầng. Chỉ dùng Redis khi đã có timeout, fallback về DB và invalidation
sau commit, không để Redis trở thành nơi quyết định thanh toán.

Trình duyệt: asset có hash có thể cache immutable dài hạn; HTML/service worker cần
kiểm tra bản mới. API chứa dữ liệu cá nhân dùng `private, no-store`, không đưa vào
cache CDN công khai. Trong React, giữ dữ liệu hiện tại khi refresh nền, hủy request
lọc cũ và bỏ response sai query. Revision chỉnh sửa phải thuộc đúng dữ liệu đang xem.

Nguồn nền tảng:
- https://fastapi.tiangolo.com/async/
- https://www.postgresql.org/docs/current/sql-createindex.html
