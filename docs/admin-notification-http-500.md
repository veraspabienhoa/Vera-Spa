# Chẩn đoán HTTP 500 khi bật thông báo Admin

## Luồng thực tế của VERA SPA

Frontend hiện tại là React; nút **Bật thông báo Admin** gọi backend **Python/FastAPI + PostgreSQL**. Apps Script, Node.js và PHP là các trường hợp tham khảo ở cuối tài liệu.

`AdminChangesPage.togglePush` → `enablePushNotifications` → quyền trình duyệt → `GET /v2/push/config` → Service Worker/PushManager → `POST /v2/push/subscriptions`.

Bật thông báo đăng ký một thiết bị. Gửi thông báo là luồng tiếp theo qua Web Push/dispatch. Cần xác định request nào lỗi trước khi quy lỗi cho webhook.

## 1. Ghi lại đúng request lỗi

1. Mở Developer Tools → Network, bật Preserve log; ghi giờ thao tác và múi giờ.
2. Bấm nút một lần. Ghi URL, method, HTTP status, thời gian đáp ứng, response body và request ID nếu có.
3. Xem Console và Application → Service Workers: đăng ký Service Worker, trạng thái active, quyền Notification và lỗi PushManager.
4. Tách lỗi CORS/chặn quyền trình duyệt khỏi HTTP 500 do máy chủ trả về. iPhone/iPad cần mở bản PWA từ Màn hình chính theo kiểm tra hiện có trong ứng dụng.

Khi chia sẻ bằng chứng, che Authorization, cookie, khóa VAPID riêng, khóa subscription, mật khẩu và endpoint Web Push đầy đủ. Không chia sẻ HAR nguyên bản còn chứa những dữ liệu này.

## 2. Đọc log của đúng phiên bản và đúng thời điểm

Trên VPS, xác định service đang chạy API thay vì đoán tên:

```bash
systemctl list-units --all --type=service 'vera*'
```

Thay `vera-api.service` bên dưới bằng unit tìm được; với user service, dùng `systemctl --user` và `journalctl --user`:

```bash
systemctl status vera-api.service --no-pager
systemctl show vera-api.service --property=EnvironmentFiles
journalctl -u vera-api.service --since '15 minutes ago' --no-pager -n 400
```

Tìm **Traceback đầu tiên** của request, loại exception, tên file/dòng, SQLSTATE và lỗi gốc của driver; đừng chỉ đọc dòng “500 Internal Server Error”. Đối chiếu Nginx access/error log theo cùng thời điểm, đường dẫn và upstream status. Đường dẫn Nginx phổ biến là `/var/log/nginx/access.log` và `/var/log/nginx/error.log`; dùng đường dẫn cấu hình thực tế nếu khác.

Trong GitHub Actions → Deploy VPS Production → `deploy`, có bước **Report recent API errors**. Bước hiện tại chỉ lấy 250 dòng thuộc mức `err` trong 60 phút, và chủ yếu phát hiện system service. Python traceback ghi ra stdout có thể mang mức journal khác, hoặc API chạy dạng user service, nên log trống ở bước này không chứng minh API không lỗi. Log VPS quanh thời điểm bấm nút là bằng chứng chính; trạng thái deploy xanh chỉ xác nhận các bước deploy/health check.

## 3. Khoanh vùng theo endpoint

| Request/bước lỗi | Kiểm tra đầu tiên | Cách diễn giải |
|---|---|---|
| `GET /v2/push/config` trả 500 | `_vault_secret` trong `vera_web_v2_api.py`, kết nối DB, view `vault.decrypted_secrets`, quyền SELECT | View/schema thiếu hoặc không có quyền có thể gây exception. Chỉ không tìm thấy tên secret thì mã hiện tại trả `enabled: false`, không phải tự động 500. |
| `PushManager.subscribe()` lỗi trong Console | Service Worker active, HTTPS, Notification permission, định dạng/độ dài public key, subscription tạo bằng khóa cũ | Thường là lỗi trình duyệt; cần phân biệt với request HTTP 500. |
| `POST /v2/push/subscriptions` trả 500 | `register_push_subscription`, bảng `vera_v2_push_subscription`, quyền ghi, constraint, UUID và transaction | Lưu thiết bị có thể thất bại ngay cả khi trình duyệt đã tạo subscription. |
| Đăng ký thành công nhưng không nhận thông báo | `_send_web_push`, `_dispatch_admin_change_pushes`, cấu hình VAPID riêng/subject, audience, endpoint hết hạn, log upstream | Đây là bước gửi; kiểm tra status của dịch vụ push, không chỉ status đăng ký. |
| `/v2/push/dispatch` bị từ chối | Header `X-VERA-Push-Webhook`, secret phía nhận, URL đích và trạng thái upstream | Không đưa webhook secret vào frontend. Token/quyền sai nên trả 401/403, không nên bị biến thành 500. |

## 4. Kiểm tra PostgreSQL bằng truy vấn chỉ đọc

Chạy bằng cùng database và vai trò mà API sử dụng; thành công với tài khoản DBA chưa chứng minh vai trò API có quyền:

```sql
SELECT current_database(), current_user;
SELECT to_regclass('public.vera_v2_push_subscription') AS subscriptions,
       to_regclass('vault.decrypted_secrets') AS vault_view,
       to_regclass('auth.users') AS legacy_auth_users;

SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = to_regclass('public.vera_v2_push_subscription');
```

Nếu view Vault tồn tại và vai trò API có quyền, chỉ kiểm tra **sự hiện diện**, không in nội dung secret:

```sql
SELECT name, length(coalesce(decrypted_secret, '')) > 0 AS configured
FROM vault.decrypted_secrets
WHERE name IN ('vera_v2_vapid_public_key',
               'vera_v2_vapid_private_key',
               'vera_v2_push_webhook_secret');
```

Hai điểm đáng kiểm tra trong repo hiện tại, **chưa phải nguyên nhân đã xác nhận trên VPS**:

- Migration `vera_postgres_phase19_web_push.sql` khai báo `auth_user_id REFERENCES auth.users(id)`. Auth local có thể tạo UUID cho tài khoản chưa từng có dòng trong `auth.users`. Nếu constraint này vẫn tồn tại trên DB thực tế, việc lưu thiết bị của tài khoản đó có thể báo `23503` (foreign key violation). Tài khoản cũ có thể vẫn hoạt động do giữ UUID legacy. Xác minh constraint và UUID trước khi lên migration phù hợp với nguồn danh tính hiện tại.
- `push_config` vẫn đọc `vault.decrypted_secrets`. Nếu chuyển sang PostgreSQL không mang theo Vault hoặc quyền đọc của API, cần log để phân biệt `42P01` (thiếu relation) và `42501` (thiếu quyền).

Các lỗi thường gặp khác: `23505` trùng unique key, `23502` cột bắt buộc rỗng, `22P02` sai định dạng UUID/JSON, `28P01` sai mật khẩu DB, connection refused/SSL/DNS, pool hết kết nối, deadlock hoặc truy vấn chờ lock. Lấy lỗi DB đầu tiên trước thông báo “transaction aborted”; sau lỗi SQL, transaction cần rollback trước khi tái sử dụng.

Không tắt RLS hoặc xóa foreign key chỉ để hết lỗi. Sửa nguồn danh tính, migration, quyền của backend hoặc transaction theo nguyên nhân đã xác nhận. PostgreSQL hỗ trợ ghi câu lệnh gây lỗi qua `log_min_error_statement`; log có thể chứa tham số nhạy cảm, nên giới hạn truy cập và che dữ liệu khi chia sẻ. [Tài liệu PostgreSQL](https://www.postgresql.org/docs/current/runtime-config-logging.html).

## 5. Kiểm tra webhook hoặc dịch vụ gửi

- Đối chiếu URL production, HTTP method, `Content-Type`, cấu trúc JSON, token/signature và timeout của cả hai phía.
- Log từng giai đoạn: `config_read`, `subscription_save`, `push_send`; cùng request ID, thời lượng, kết quả và status upstream. Với lỗi ngoài dự kiến, lưu stack trace ở máy chủ; response chỉ trả mã lỗi/request ID đã che chi tiết nội bộ.
- Kiểm tra secret có trong môi trường **process/service thực sự chạy**, không chỉ shell SSH. Chỉ log có/không, không log giá trị.
- Lỗi 401/403/404/410 từ dịch vụ push, khóa VAPID không khớp, endpoint hết hạn, DNS/TLS hoặc timeout không được làm mất kết quả lưu dữ liệu nghiệp vụ đã thành công.
- Chỉ retry lỗi tạm thời với giới hạn; kiểm tra trạng thái đã lưu trước khi retry để tránh đăng ký/gửi lặp.

## 6. Nếu endpoint thuộc nền tảng khác

| Nền tảng | Log cụ thể | Nguyên nhân thường gặp |
|---|---|---|
| Google Apps Script | Editor → Executions, lọc lần chạy Web app/`doPost` đúng thời điểm; `console.error`/`Logger`; Cloud Logging và Error Reporting của Cloud project liên kết | Chưa deploy phiên bản mới, sai `/exec` deployment, Execute as/quyền truy cập không đúng, thiếu OAuth scope, vượt quota/thời gian chạy, parse JSON lỗi, `e.postData` thiếu, sheet/range không tồn tại hoặc không có quyền, exception từ `UrlFetchApp`. `doPost(e)` phải trả `TextOutput` hoặc `HtmlOutput`; bấm Run trong editor không tạo event webhook thật. [Logging](https://developers.google.com/apps-script/guides/logging), [Web apps](https://developers.google.com/apps-script/guides/web). |
| Node.js | stdout/stderr của process thực sự chạy: systemd journal, PM2 hoặc container logs; stack trace của request và lỗi driver DB | `await`/Promise bị reject, lỗi xử lý JSON/body parser, biến môi trường thiếu, dereference null/undefined, sai driver/credentials, pool cạn, timeout upstream. Ghi cả `error.code` và `error.stack`; không trả nguyên stack cho client. [Node.js Errors](https://nodejs.org/api/errors.html). |
| PHP | Nginx/Apache error log, PHP-FPM error log, log framework; file cấu hình bởi `error_log` | Fatal/parse error, thiếu PDO extension, DSN/quyền DB sai, biến môi trường FPM khác shell, exception PDO, quyền file, timeout hoặc thiếu bộ nhớ. Production dùng `log_errors=On`, `display_errors=Off`; đọc log phía server. [Cấu hình PHP](https://www.php.net/manual/en/errorfunc.configuration.php). |
| Supabase | Logs → Postgres, Auth, API Gateway; nếu có Edge Function, xem cả invocation và console logs; lọc theo thời gian/status/path | Sai nguồn Auth, thiếu relation/migration, thiếu quyền/RLS, secret chưa cấu hình, pooler/connection lỗi. Các log thuộc dịch vụ khác nhau; đọc đúng nguồn. [Supabase Logs](https://supabase.com/docs/guides/observability/logs). |

## 7. Xác minh sau khi sửa

Kiểm tra lần lượt: config 200 và có public key; Service Worker active; subscription POST 200; reload vẫn đồng bộ được thiết bị; tắt/bật không tạo bản ghi trùng; trường hợp sai quyền trả 401/403; dữ liệu thiếu/sai trả 400/422. Sau đó kiểm thử gửi tới một thiết bị đã được cho phép và xác nhận nhận được thông báo. Đối chiếu request ID với log để chứng minh đã xử lý đúng lỗi ban đầu.

Thông tin tối thiểu để chốt nguyên nhân: endpoint lỗi, thời điểm/múi giờ, response body đã che dữ liệu nhạy cảm và traceback/SQLSTATE tương ứng. Chưa có các bằng chứng này thì chỉ nên nêu giả thuyết.
