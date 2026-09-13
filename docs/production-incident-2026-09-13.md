# Sự cố đăng nhập và tải dữ liệu ngày 13/09/2026

## Đọc đồng thời sau PR 108

PR 108 đã deploy tại commit 4e6508eda644238adede2b710bc03c9bd95afbe1,
run 34770662457. Người dùng vẫn gặp thông báo bận và yêu cầu hỗ trợ nhiều user.
Bản tiếp theo cho GET đọc snapshot đã commit khi không lấy được khóa ngay;
không chạy attendance/daily projection hoặc ghi snapshot trong nhánh này.
Các lần đọc có khóa vẫn cập nhật projection như trước để giữ hành vi chấm công.
Các lần ghi vẫn khóa toàn bộ JSON và kiểm tra revision/idempotency: không tuyên
bố hỗ trợ ghi song song độc lập theo phòng. User đọc snapshot cũ có thể nhận
409 khi gửi thao tác; phải tải lại và xác nhận, không tự retry thanh toán.
Thông báo lỗi tải cũ được xóa khi lần tải kế tiếp thành công.

Kiểm thử mô phỏng 24 GET/8 luồng khi khóa bị giữ, các màn hình phụ và bootstrap
chưa commit. Đây không phải load test PostgreSQL/VPS thực tế. Chưa deploy bản này.

## Tái diễn lúc 16:37 UTC — bản vá giảm nghẽn, chưa deploy

VPS xác nhận commit 5fe64c818e5a59303048bb3cbf77134928a5c95f, không có
thay đổi tracked. Log: pool size 10, overflow 20, timeout 30 giây;
10 kết nối chờ advisory lock và một giao dịch idle in transaction 19 giây.
Chưa xác định PID giữ khóa hoặc tác vụ cụ thể giữ khóa lâu nhất.

Bản vá sử dụng pg_try_advisory_xact_lock trên cùng conn/giao dịch: khi bận,
trả 503 Retry-After 3 và rollback qua context manager, không xếp hàng giữ
kết nối. Không bỏ khóa, thay đổi idempotency, quyền hay số tiền. Giao diện
bỏ qua poll nền khi lần tải trước chưa xong; tải rõ ràng đợi lần trước rồi
đọc mới. Đây là giảm tải/giảm khuếch đại sự cố, chưa phải bằng chứng loại bỏ
mọi nguyên nhân giữ khóa. Không tự retry mutation thanh toán.

Chưa sửa schema payroll, mật khẩu hoặc đồng bộ Pages trong bản vá này.
Phải kiểm chứng hai health và booking/payment/combos trên môi trường thử
trước production; vẫn cần đo thời gian attendance và permissions trong khóa.

Người dùng đã xác nhận sau bản sửa: **đăng nhập được và dữ liệu đã hiển thị**.
Hồ sơ này được lưu theo yêu cầu của người dùng để tránh lặp lại lỗi.

## Triệu chứng và bằng chứng

- Trước đó xuất hiện “Không xác minh được phiên đăng nhập PostgreSQL”. Sau khi
  phần xác thực hoạt động lại, Live Tour vẫn báo HTTP 500; lịch nghỉ, hóa đơn và
  danh sách nhân viên không tải được.
- `/v2/auth/health` vẫn trả HTTP 200 nhưng `/v2/health`, dùng nhóm kết nối nghiệp
  vụ, bị timeout. Hai kết quả phải được kiểm tra riêng.
- Log runtime ghi nhận `sqlalchemy.exc.TimeoutError`: nhóm kết nối thực tế có
  `size=5`, `overflow=5`, hết thời gian chờ sau 30 giây. Đây là cấu hình quan sát
  tại thời điểm sự cố, không phải giá trị mặc định cần sao chép cho mọi môi trường.
- PostgreSQL ghi nhận **9 kết nối cùng chờ advisory lock** và một giao dịch đang
  giữ kết nối trong trạng thái `idle in transaction`. Các yêu cầu khác không lấy
  được kết nối để đọc dữ liệu.
- Kiểm tra trực tiếp vẫn đọc được **723 bản ghi lịch nghỉ** và 67 hồ sơ nhân viên.
  Đây là số liệu lúc kiểm tra, không phải tiêu chí cố định cho các lần deploy sau.

## Nguyên nhân và bản sửa

Live Tour giữ giao dịch và khóa trạng thái bảng tua khi gọi chuỗi tính chấm công.
Hai phần xử lý `vera_web_v2_outside_leave_rule.py` và
`vera_web_v2_break_return_penalty.py` lại mở thêm kết nối để đọc nội quy, ghi phạt
và gửi thông báo. Khi các kết nối còn lại đang chờ cùng khóa bảng tua, việc lấy
thêm kết nối làm cạn nhóm kết nối dùng chung. Vì vậy cả màn hình không liên quan
như lịch nghỉ cũng bị ảnh hưởng.

[PR #95](https://github.com/veraspabienhoa/Vera-Spa/pull/95) đã:

1. Dùng lại `conn` của giao dịch hiện tại khi đọc nội quy và ghi phạt.
2. Dùng `conn.begin_nested()` để cô lập lỗi ghi phạt bằng savepoint, giúp giao
   dịch bên ngoài vẫn sử dụng được khi một lần ghi phạt thất bại.
3. Cho giao dịch đọc chấm công thành công commit các bản ghi sự kiện và hàng đợi
   thông báo; cập nhật cả route snapshot gốc và route thay thế trong operations.
4. Bỏ gửi thông báo đồng bộ trong chuỗi đọc. Tác vụ TimeSoft hiện có gửi các
   thông báo đã commit theo lịch nền, giữ cơ chế thử lại và chống trùng.
5. Bổ sung kiểm tra `/v2/health` khi deploy, bên cạnh kiểm tra xác thực.

Giữ nguyên cơ chế nhóm kết nối xác thực riêng trong `vera_web_v2_auth_pool.py`:
giới hạn số kết nối/thời gian chờ, dùng cùng cơ sở dữ liệu và SSL, vẫn kiểm tra
thu hồi phiên và khóa tài khoản từ PostgreSQL. Không dùng cache danh tính hoặc
bỏ qua xác thực để che lỗi truy cập cơ sở dữ liệu.

Tăng số kết nối hoặc restart đơn thuần không loại bỏ nguyên nhân mở kết nối lồng
nhau. Không thay đổi quy tắc tính phạt, cơ chế chống trùng hoặc số tiền hóa đơn
để giải quyết lỗi hiệu năng này.

## Kiểm chứng phục hồi

- **1.019 kiểm thử Python đạt**, bao gồm kiểm thử hai luồng ghi phạt khi chỉ có
  một kết nối và khả năng rollback riêng lần ghi lỗi.
- Kiểm tra backend, React và hàng đợi thông báo trên GitHub đều đạt trước merge.
- Commit production: `bbb0894e4cdce23050a53e7314106230fc13e08c`.
- [Lần deploy thành công](https://github.com/veraspabienhoa/Vera-Spa/actions/runs/34749729221).
- Sau deploy, `/v2/health` và `/v2/auth/health` đều trả HTTP 200 với `ok=true`.
  Lần chụp trạng thái PostgreSQL sau deploy không còn kết nối chờ khóa.
- Sau đó người dùng xác nhận đăng nhập và hiển thị dữ liệu đã hoạt động.

## Chẩn đoán đúng khi có sự cố mới

1. Ghi nhận thao tác lỗi, URL API, mã HTTP và thời điểm; phân biệt không đăng nhập
   được với đã đăng nhập nhưng không tải được dữ liệu. Số liệu đang hiện có thể
   là cache của lần tải trước.
2. Xác minh máy chủ đang chạy bản ứng dụng. Trong sự cố này, DNS Cloudflare của
   `app`, `api`, `admin.veraspa.vn` trỏ về `160.236.192.51`. VPS `.65` người dùng
   từng SSH vào chạy một website khác, không phải runtime VERA. Cần đối chiếu lại
   cấu hình hiện hành trước mọi lần thay đổi; không đổi DNS chỉ từ IP được cung cấp.
3. Ưu tiên kênh SSH triển khai đã được cấu hình và cho phép. Không yêu cầu người
   dùng gửi mật khẩu root/PostgreSQL vào cuộc trò chuyện. Kết nối DB thành công
   từ máy cá nhân không chứng minh tiến trình API trên VPS dùng đúng cấu hình.
4. Dùng `vera_vps_runtime_diagnostics.py` để thu thập log của đúng systemd unit
   và trạng thái PostgreSQL. Script chỉ xuất loại lỗi, vị trí stack và số liệu
   tổng hợp; kết nối chẩn đoán chỉ đọc, có giới hạn thời gian. Không chỉ lọc log
   “local auth”, vì cách đó bỏ sót lỗi nghiệp vụ.
5. Đối chiếu timestamp của log, lần khởi động và SHA deploy. Giờ VPS và runner có
   thể lệch; traceback trong cửa sổ 20 phút có thể thuộc tiến trình trước restart.
6. Lỗi Actions “job was not started … failed to be acquired (5 attempts)” và
   “internal error” xảy ra trước khi job chạy không chứng minh code deploy lỗi.
   Kiểm tra runner, concurrency và SHA; chỉ chạy lại sau khi hiểu trạng thái run.
7. Sau sửa, kiểm tra cả hai API health, dữ liệu nghiệp vụ và màn hình người dùng.
   Chỉ kết luận những gì đã kiểm chứng; không dùng trạng thái workflow xanh làm
   bằng chứng duy nhất rằng toàn bộ ứng dụng hoạt động.

Các lỗi `DefaultCredentialsError`/`JSONDecodeError` ở tác vụ đối soát Google và
`ProgrammingError` tại phần đọc vault cũng từng xuất hiện trong log. Chúng cần
chẩn đoán cấu hình riêng nếu tái diễn; bản sửa nhóm kết nối không chứng minh các
cấu hình tích hợp đó đã được khắc phục. Không gộp chúng với lỗi hết kết nối.

Chẩn đoán tiếp theo về Đăng ký nghỉ tải chậm được ghi riêng tại
[hồ sơ tối ưu tải lịch nghỉ](leave-loading-performance-2026-09-13.md): đọc Nội
quy lặp trong API và chờ nhiều phần dữ liệu ở giao diện. Chưa có bằng chứng từ
video rằng lỗi hết nhóm kết nối trước đó tái diễn.

## Rà soát đăng nhập phía trình duyệt sau lần deploy tiếp theo

### Bằng chứng và giới hạn kết luận

- Người dùng tiếp tục báo không đăng nhập được. Hai ảnh kiểm tra mới đều có
  `ok=true` tại `/v2/health` và `/v2/auth/health` (`provider=postgres-local`).
  Điều này không chứng minh thao tác đăng nhập hoặc `/v2/me` thành công.
- Main được đối chiếu lúc rà soát là
  `21f81ab4eaf1bc6eab188ae19e63c13fe62b7103`, đã deploy qua
  [run 34759912065](https://github.com/veraspabienhoa/Vera-Spa/actions/runs/34759912065).
  Không suy ra nguyên nhân lỗi đăng nhập từ riêng trạng thái deploy thành công.
- Chưa có request/response của lần đăng nhập lỗi trên trình duyệt người dùng.
  Các lỗi bên dưới được xác nhận bằng mã nguồn và kiểm thử mô phỏng; chưa đủ
  bằng chứng khẳng định chúng là nguyên nhân duy nhất trên production.

### Lỗi tái hiện và bản sửa

1. `supabase.js` có mặc định API production nhưng `api.js` không có; cách xử lý
   khoảng trắng cũng khác nhau. Với biến build thiếu hoặc có khoảng trắng,
   login và xác minh hồ sơ có thể gọi khác backend. Dùng chung `apiConfig.js`,
   giữ override local/staging và không chuyển sang Supabase Auth khi API lỗi.
2. Refresh gặp lỗi mạng, 429 hoặc 5xx có thể xóa refresh token đang lưu. Chỉ xóa
   khi máy chủ xác nhận 401/403; lỗi tạm thời giữ token để thử lại. Không coi
   access token hết hạn hoặc hồ sơ lưu cục bộ là bằng chứng xác thực.
3. `/v2/me` trả 401 rồi refresh trả 503: vòng thử lại giữ response 401 cũ và có
   thể làm App đăng xuất nhầm. Tách refresh khỏi vòng thử lại transport, truyền
   đúng lỗi refresh, và chỉ refresh một lần cho mỗi request bị từ chối.
4. Login/refresh/xác minh hồ sơ không có thời hạn chờ. Thêm deadline **15 giây
   cho mỗi request**, gồm đọc body, và màn hình thử xác minh lại khi khôi phục
   phiên thất bại tạm thời. Không áp deadline ngắn này cho payroll/export.
5. Response HTTP 200 sai định dạng không được ghi đè phiên hợp lệ. Tiếp tục giữ
   single-flight refresh và bảo vệ phiên đăng nhập mới trước kết quả refresh cũ.

Kiểm thử `authSessionTransport.test.mjs` tái hiện lỗi trên mã cũ và kiểm chứng
phục hồi, timeout, 401/403, response lỗi, refresh đồng thời và đăng xuất.
`authRecovery.test.mjs` kiểm chứng giao diện không mở dữ liệu khi PostgreSQL hoặc
refresh chưa xác minh được, có thể thử lại và vẫn từ chối tài khoản bị khóa.
Hai bộ được đưa vào CI. Không sửa schema, dữ liệu, DNS hoặc cơ chế xác thực
PostgreSQL. Cần xác minh lại đăng nhập và dữ liệu thực tế **sau khi bản sửa được
merge/deploy**; mục này không phải xác nhận production đã phục hồi.

Kiểm chứng cục bộ bản sửa: **1.035 kiểm thử Python**, **122 kiểm thử Web V2**
(gồm 24 kiểm thử xác thực/phục hồi) đạt; build production thành công. Cập nhật
kiểm thử đăng xuất cũ để kiểm tra thu hồi refresh token của phiên hiện tại,
thay vì dựa vào một comment về Supabase SDK đã không còn được gọi.

## Kiểm tra hồi quy cần giữ

```bash
python -m pytest -q tests/test_attendance_connection_reuse.py tests/test_auth_pool.py tests/test_auto_penalty_employee_notifications.py tests/test_vps_runtime_diagnostics.py
```

- `test_attendance_connection_reuse.py`: hai luồng phải hoàn tất với một kết nối;
  ghi thành công được lưu và lỗi ghi riêng không làm hỏng giao dịch bên ngoài.
- `test_auth_pool.py`: xác thực vẫn dùng được khi nhóm kết nối nghiệp vụ bị chiếm
  hết; giữ giới hạn kết nối và chính sách SSL.
- `test_auto_penalty_employee_notifications.py`: hàng đợi vẫn thử lại/chống trùng;
  tác vụ nền gửi thông báo, chuỗi đọc không gửi ngay khi đang giữ giao dịch.
- `test_vps_runtime_diagnostics.py`: giữ thông tin chẩn đoán hữu ích nhưng không
  làm lộ dữ liệu riêng trong log.

Workflow thông báo cần đủ phụ thuộc cho các module chấm công được kiểm thử,
bao gồm `requests` và `gspread`. Giữ kiểm tra hồi quy khi đổi thiết kế; cập nhật
kiểm tra hành vi cũ cho đúng ranh giới giao dịch, không chỉ tắt một kiểm tra đỏ.
