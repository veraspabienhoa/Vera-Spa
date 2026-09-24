# Sự cố đăng nhập và tải dữ liệu ngày 13/09/2026

## 25-09-2026: điều khiển thông báo theo kênh, chưa triển khai

Thông báo trong ứng dụng trước đây vẫn xuất hiện sau khi đánh dấu đã đọc và
danh sách lưu cả các ngày cũ. Bản sửa chỉ trả về bản ghi chưa xem của ngày hiện
tại theo `Asia/Ho_Chi_Minh`; khi mở hộp thư, bản ghi trong ứng dụng của ngày cũ
và push đã gửi của ngày cũ được dọn khỏi bảng giao nhận. Push còn chờ gửi không
bị xóa để giữ cơ chế thử lại. Chi tiết qua liên kết cũ hết hiệu lực sau nửa đêm.
Nút Đã xem của Admin ghi `read_at` theo đúng người nhận; xem chi tiết không tự
đánh dấu. Tiêu đề mới và giao diện gỡ tiền tố VERA SPA; service worker cũng gỡ
tiền tố cho thông báo đẩy cũ.

Admin chỉnh riêng kênh trong ứng dụng và thông báo thiết bị cho từng loại trên
trang Cài đặt / Thông báo. Trạng thái kênh lưu trong bảng riêng, kiểm tra trước
khi tạo bản giao nhận, khi đọc và ngay trước khi gửi push; API cập nhật yêu cầu
quyền Admin và revision hiện hành. Công tắc thiết bị của Admin chuyển khỏi trang
Thay đổi hệ thống và Hồ sơ sang trang này. Chưa xác minh dữ liệu PostgreSQL và
thông báo trên thiết bị production; cần triển khai backend trước frontend và
kiểm tra hai health endpoint cùng hoạt động thật sau triển khai.

## Chuẩn hóa địa chỉ Web production — 17/09/2026, chưa deploy

Người dùng xác nhận địa chỉ duy nhất còn sử dụng là
`https://app.veraspa.vn/`, không còn sử dụng đường dẫn Pages theo repository.
Rà soát mã xác nhận production build, manifest, icon và service worker vẫn gắn
với prefix lịch sử `/Vera-Spa/`; backend và Cloud Build vẫn cho phép origin
GitHub Pages cũ.

Bản sửa đặt production base, PWA scope/start URL, icon và URL thông báo ở root;
thêm `CNAME` cho `app.veraspa.vn`; đồng thời bỏ origin GitHub Pages cũ khỏi cấu
hình CORS production và cập nhật tài liệu triển khai. API vẫn chỉ định rõ origin
`app.veraspa.vn`, không nới CORS và không thay đổi xác thực, phiên đăng nhập hoặc
dữ liệu nghiệp vụ. Chưa deploy hoặc thay đổi DNS; cần workflow có thẩm quyền
triển khai frontend và backend tương ứng rồi xác minh URL production thực tế.

## Live Tour dựng lại toàn trang quá thường xuyên — 17/09/2026, chưa deploy

Rà soát mã phía trình duyệt xác nhận đồng hồ Live Tour cập nhật React state mỗi
giây. Vì đồng hồ nằm trong component trang lớn, mỗi tick dựng lại cả lưới phòng,
bảng nhân viên và các panel tài chính dù phần đếm thời gian chỉ hiển thị theo
phút. Ngoài ra lifecycle tải dữ liệu phụ thuộc vào trạng thái modal và thao tác;
đóng/mở modal hoặc đổi trạng thái đang lưu đã hủy/tạo lại poller và có thể kích
hoạt thêm một lượt tải đầy đủ có projection ngay sau thao tác.

Bản sửa cập nhật đồng hồ mỗi 20 giây, giảm đúng 20 lần số lượt render định kỳ do
đồng hồ mà không thay đổi độ chi tiết phút đang hiển thị. Poll ba giây và cơ chế
revision `unchanged` vẫn được giữ để thiết bị đang mở nhận thay đổi nhanh; tab ẩn
không poll và tải bù ngay khi hiện lại. Poller dùng ref cho trạng thái thao tác và
không còn bị tạo lại bởi modal/action, nên thao tác không tự phát sinh lượt tải
projection ngoài response của chính nó. Không thay đổi khóa, transaction,
idempotency, quyền, dữ liệu tài chính hoặc projection chấm công.

Kiểm chứng cục bộ: kiểm thử mới xác nhận tỷ lệ tick 20:1 và tab ẩn/hiện; 152 kiểm
thử backend trọng tâm, 34 kiểm thử frontend trọng tâm, lint các file thay đổi và
production build đều đạt. Lint toàn frontend còn hai lỗi tồn tại ngoài phạm vi ở
`employeeDirectoryUx.js` và `liveTourAppearance.js`. Chưa đo CPU/latency trên VPS,
chưa deploy và chưa xác minh hai health endpoint hoặc thao tác nghiệp vụ thật;
vì vậy mục tiêu 20 lần ở đây chỉ được xác nhận cho nguồn render định kỳ phía
trình duyệt, không phải tuyên bố toàn bộ request backend nhanh hơn 20 lần.

## Live Tour: ca hồ sơ bị nhãn ca TimeSoft ghi đè — 15/09/2026, chưa deploy

Người dùng báo Thanh Nhã đã được xếp Ca 1 từ 14/09/2026, chu kỳ luân phiên
14 ngày, nhưng Live Tour ngày 14 và 15/09 vẫn hiện Ca 2. Rà soát ZIP nguồn
`37ba6cc264e9631e6468f326eb3d0635f4db05f1` xác nhận `project()` trong
`vera_web_v2_live_tour_checkin.py` ưu tiên `WorkTimeName`/`ShiftName` của TimeSoft
trước ca tính từ hồ sơ. Kiểm thử với cấu hình đúng như ảnh và TimeSoft còn Ca 2
đã tái hiện sai lệch ở cả hai ngày; chưa truy vấn dữ liệu production để khẳng
định đó là nguyên nhân duy nhất trên VPS.

Bản sửa ưu tiên ca hồ sơ đã có hiệu lực, sau khi xác nhận check-in hợp lệ.
Hồ sơ chưa gán được ca, ngày hiệu lực ở tương lai hoặc ngày không hợp lệ thì
chỉ dùng nhãn ca TimeSoft dự phòng. Hồ sơ cũ không có ngày bắt đầu vẫn có hiệu
lực ngay. Giữ nguyên thuật toán luân phiên và các hàm dùng chung với cảnh báo/
lịch nghỉ, không thay schema, dữ liệu TimeSoft, tài chính hay cơ chế khóa.
Quyền Admin đổi Ca 1/Ca 2 riêng trong ngày vẫn được áp dụng ở bước reconcile;
nghỉ phép và kiểm tra check-in không bị bỏ qua. Projection hiện có tự sửa ca
snapshot ở lần làm mới hoặc tick scheduler thành công, vẫn dùng revision hiện
hành; không thêm truy vấn hay giao dịch lồng nhau.

Kiểm chứng cục bộ: bộ mới 47/47 đạt (trên mã cũ: 26 lỗi assertion, 21 đạt);
nhóm trọng tâm 173/173 đạt. Toàn bộ pytest với tiếp tục sau lỗi collection:
973 đạt, 9 thất bại và 24 lỗi collection do thiếu `gspread`/`google.auth`.
Chạy lại ZIP gốc cho cùng 9 thất bại và 24 lỗi collection, 926 đạt. Các nhóm
xác thực/push/chẩn đoán/cảnh báo/lịch nghỉ đã chạy được có 27 test đạt;
`test_attendance_connection_reuse.py` bị chặn bởi thiếu `gspread`.
Không coi kết quả này là toàn bộ CI đạt; chưa push, merge, deploy hoặc xác minh
hai health và màn hình thực tế trên VPS. Kiểm thử mới nằm trong
`tests/test_live_tour_shift_effective_date.py`, được pytest mặc định của CI thu thập.

## Live Tour chậm trên mobile/desktop — bản sửa ngày 15/09/2026, chưa deploy

Rà soát mã xác nhận mỗi trang Live Tour mở đang poll ba giây một lần và mỗi
response không đổi vẫn dựng/truyền lại toàn bộ aggregate đã phân quyền, gồm các
collection khách hàng, hóa đơn, báo cáo và lịch sử. Khi lấy được khóa, GET còn
có thể chạy lại attendance/directory/leave projection. Thanh toán hóa đơn chờ,
thanh toán nhanh và mua combo cũng dùng đường projection đầy đủ dù các bất biến
tài chính của chúng chỉ đọc/ghi aggregate đã khóa.

Bản sửa cho poll gửi revision hiện có. Nếu revision PostgreSQL không đổi, API
chỉ trả marker `unchanged`; trình duyệt không thay state, không ghi lại cache và
không render lại bảng. Nếu revision đã đổi, poll đọc snapshot đã commit mà không
lặp projection của scheduler. Lần mở đầu và thao tác làm mới rõ ràng vẫn giữ
projection hiện hành. Các mutation hóa đơn/combo được chuyển sang đọc aggregate
`FOR UPDATE` không projection; vẫn giữ khóa chung, expected revision,
idempotency, quyền, chống trừ combo/thanh toán trùng và ghi shadow relational.
Booking/start/finish vẫn dùng projection đầy đủ vì phụ thuộc trạng thái ca, nghỉ
và chấm công.

Kiểm chứng cục bộ: 183 kiểm thử backend trọng tâm, 37 kiểm thử frontend trọng
tâm và production build đạt; lint không có lỗi (còn một cảnh báo cũ ở payroll).
Toàn bộ 134 kiểm thử frontend có một lỗi cũ ở
`paymentPresentation.test.mjs` về mặc định mở hóa đơn; lỗi tái hiện riêng và
không thuộc các file thay đổi. Chưa đo latency, log khóa hoặc tải response trên
VPS production, nên nguyên nhân production được xem là phù hợp với triệu chứng
và đã xác nhận trong mã, chưa phải kết quả đo runtime sau deploy.

## Nền tảng khóa tài nguyên toàn hệ thống — đang phát triển, chưa deploy

Theo yêu cầu mở rộng ngày 15/09/2026, thiết kế concurrency không chỉ áp dụng
cho Live Tour. Mã đang phát triển bổ sung primitive dùng chung cho khóa theo
employee/leave/room/invoice/combo, revision, idempotency, exclusive claim và bộ
đếm nguyên tử. Các thao tác hồ sơ nhân viên và lịch nghỉ đơn lẻ bắt đầu dùng khóa
theo tài nguyên trong chế độ chuyển tiếp `hybrid`; batch import/xóa-reindex vẫn
giữ khóa miền rộng vì chúng thay đổi nhiều hàng.

Live Tour được backfill sang các bảng vật lý riêng theo collection và dual-write
ở chế độ shadow. Workflow production sẽ chạy migration rồi kiểm tra hash parity.
Phần này chưa được push/deploy và chưa phải bằng chứng production hỗ trợ toàn bộ
mutation Live Tour commit song song. Chỉ chuyển `hybrid` sang `resource` sau khi
mọi writer cũ đã được nâng cấp; không bỏ khóa chung trước cutover.

### Deploy #395: ứng dụng đã lên, migration chưa chạy

Run 34922095434 đã deploy đúng commit `923788d7` và xác minh local Auth, nhưng
dừng tại bước concurrency schema trước khi ghi DDL. Script migration gọi trực
tiếp `vera_postgres.get_engine()` trong tiến trình SSH không kế thừa môi trường
systemd, nên nhận `VERA_DB_ENABLED=0`. Bản sửa nạp cùng managed runtime file/fallback
process environment đã dùng bởi payroll schema và data check, dùng `NullPool`,
và chỉ log loại lỗi đã khử connection string/SQL payload. Cần chạy lại deploy
sau khi bản sửa qua CI; run #395 không phải bằng chứng backfill/parity đã đạt.

## Giảm tranh chấp Live Tour — bản ZIP ngày 15/09/2026

Rà soát tiếp xác nhận đọc snapshot khi khóa bận đã có, nhưng tác vụ projection
nền vẫn cố lấy khóa mỗi 15 giây và mọi mutation vẫn chạy toàn bộ attendance,
directory và leave projection trong khóa. Bản sửa cho tác vụ nền bỏ qua tick khi
operator đang thao tác; tính quyền phản hồi trước khóa; các thay đổi metadata an
toàn (khu vực/phòng/dịch vụ/combo, thứ tự, lịch hẹn và cài đặt thanh toán) đọc
aggregate trực tiếp không chạy projection. Booking, bắt đầu/kết thúc dịch vụ,
nghỉ giữa ca, đổi nhân viên, combo và thanh toán vẫn dùng projection đầy đủ và
khóa/revision/idempotency để chống xung đột nghiệp vụ.

Thiết kế JSON aggregate vẫn tuần tự hóa các lượt ghi. Bản sửa làm critical
section ngắn hơn để nhiều tài khoản thao tác gần như đồng thời, nhưng không tuyên
bố hai mutation ghi được commit song song. Ghi song song độc lập theo nhân viên/
phòng cần migration sang bảng chuẩn hóa hoặc event/patch rows và kiểm tra khóa
riêng theo resource; không được bỏ khóa chung khi dữ liệu tài chính còn nằm trong
một JSON.

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

## Ca Live Tour và Chấm công không đồng nhất — 22-09-2026, chưa deploy

Người dùng báo Phương Vy trên Live Tour là Ca 2, Chấm công là Ca 1 và xác
nhận ca đúng là Ca 1. Chưa truy cập hồ sơ, ca Admin ghi đè hoặc runtime
Production của nhân viên này; không kết luận nguyên nhân riêng từ báo cáo đó.

Rà soát mã xác nhận Chấm công dùng WorkTimeName và giờ ca TimeSoft cho KTV
có FaceID; dòng chưa có FaceID chỉ dùng ca gốc và không tính luân phiên.
Live Tour tính chu kỳ Vera nhưng vẫn lấy nhãn TimeSoft dự phòng nếu hồ sơ
không có ca hiệu lực. Đây là các đường gây sai lệch đã xác nhận trong mã.

Bản sửa dùng chung bộ tính ca Vera theo ngày hiệu lực/chu kỳ cho Live Tour
và Chấm công, loại bỏ dự phòng TimeSoft; dữ liệu TimeSoft vẫn cung cấp
FaceID. Chấm công thay nhãn và giờ ca trước bước đọc cấu hình ca/nghỉ giữa
ca. Không gán cứng ca theo tên nhân viên, không thay hồ sơ hoặc tài chính.
Giữ Admin đổi ca trong ngày trên Live Tour; nếu Phương Vy vẫn lệch sau
triển khai cần đối chiếu hồ sơ và manual_shift_date/manual_shift_by thực tế.
Kiểm thử tình huống mô phỏng hồ sơ Phương Vy Ca 1 và TimeSoft Ca 2 không
phải bằng chứng đã đọc hay sửa dữ liệu Production.

Kiểm chứng cục bộ: 1.312 kiểm thử Python đạt, gồm các trường hợp ca Vera
trái nhãn TimeSoft, đổi chu kỳ, ngày hiệu lực, thiếu ca và các hồi quy pool/
notification/booking. Chưa deploy hoặc xác minh ca Phương Vy trên Production.

## 22-09-2026: Live Tour performance changes (not deployed)

The proposed resource-storage release adds an explicit offline cutover with parity
verification and an export-back rollback. Never switch active/shadow modes without
the corresponding cutover while all writers are stopped. See
[live-tour-resource-performance.md](live-tour-resource-performance.md).
Local regressions do not establish production performance or deployment success;
resource transaction tests use an isolated PostgreSQL CI service. No production
latency multiplier has been measured.

## Scoped Live Tour start follow-up (not deployed)

The proposed follow-up removes whole-board employee writes from `start` in active
resource mode. A metadata invalidation marker resets manual ordering; only selected
employees are written. `start_room` locks and rechecks all waiting members. The
existing room/customer constraints and exclusive reorder/restore fence remain.
Rollback materializes effective manual flags for old releases. This change does
not itself activate resource storage or establish a production speed multiplier.

## 23-09-2026: explicit Live Tour activation safeguard (not activated)

Code inspection confirms the managed environment allowlist omitted
`VERA_LIVE_TOUR_RELATIONAL_MODE`, and schema backfill trusted the SSH process mode.
A ready resource database with a shadow CLI could therefore be overwritten from
frozen aggregate data. This is a confirmed code risk, not evidence that production
records were overwritten. A successful deployment/parity log alone does not prove
that the API is serving resource mode.

The proposed manual maintenance workflow backs up privately, stops the discovered
API unit and embedded projection writers, holds both session fences through
cutover/restart/verification, and recovers with current canonical data. The managed
mode is optional but validated. Database readiness independently prevents legacy
writes/backfill; actual API business health rejects mode mismatches. See the
resource-performance runbook for requirements, downtime and failure recovery.
No production activation or production performance measurement is performed by
creating this workflow. PostgreSQL integration tests cover post-cutover backfill
protection, both fences across commits and canonical export/reactivation.

## 23-09-2026: maintenance status rejected a systemd-configured VPS

Deploy run 35825197223 succeeded at e296a0f7. Maintenance run 35825402395
selected `status` and failed with `private managed API environment is required`.
This happened before service stop or cutover. The mandatory managed-file check
was incompatible with the process-environment fallback already used by deployment.
The correction reads only allowlisted settings from validated API processes,
rejects disagreement, and persists storage mode separately from DB/Auth settings.
This code change alone does not establish successful production activation.

## 23-09-2026: activation failed before stopping writers

Maintenance run 35827575962 at ed90908b selected activate. The automatic status
check returned ok=true, mode=shadow, resource_ready=false. The next helper exited
with the generic maintenance subprocess error before printing the stopping-writers
marker. The code path suggests the noninteractive sudo authorization probe; the
old log suppresses subprocess details, so the exact VPS policy cause remains
unverified. Add safe command-specific authorization errors and read-only preflight
results to status. No permissions are expanded and no production cutover is
established by this diagnostic change.

## 23-09-2026: preparation blocked by cron schema backup permissions

User-provided VPS diagnostics confirm API service active, stop/start authorization
passing, pg_dump/pg_restore 17.11, and a zero-byte database.dump in failed preparation.
A schema-only pg_dump reproduced PERMISSION_DENIED and identified schema cron.
The cutover does not modify scheduler objects. Exclude only cron and pg_cron from
its archive, record that scope, and require archive definitions/data for every
Live Tour resource table before cutover. This is not a full-instance backup or
proof of a successful production activation. Do not grant cron access to the API
role or suppress subsequent dump errors.


## 24-09-2026: FaceGate mapping confirmation actor missing

User evidence shows profile 142 mapped successfully and an exact reference match,
but the read-only readiness probe reports one stored mapping and zero confirmed
mappings. Code inspection confirms save_facegate_mapping reads Identity.username,
which does not exist: the authenticated field is employee_username. Consequently
confirmed_by is empty and readiness correctly excludes the row.

Use employee_username and reject an empty actor before any database write.
Regression tests use the production identity field and cover reconfirming a legacy
row, recording the actor, and readiness counting its reference without enabling
attendance cutover. Do not invent historical actors or weaken readiness checks.
After backend deployment, an authenticated Admin must read and reconfirm the
existing profile, then verify readiness and both health endpoints. This entry
records diagnosis and tested code, not completed production verification.


## 24-09-2026: FaceGate log pagination dropped subsequent pages

Production read-only diagnostics report total=129 and pages beginning at
0,20,40,60,80,100,120, with ITEM indices matching these absolute offsets.
Only the first 20 records parsed because both log parsers capped the numeric
ITEM index at 19. The full-day sync correctly refused incomplete_day and did
not write an incomplete archive. Replace the numeric-index cap with a maximum
of 20 distinct items per response; report truncation when parsed count is below
the device total. Regression fixtures cover 129 records over seven pages,
page-local indices, oversized pages and short responses. Local tests pass;
production full-day preview and archive writes still require verification
after deployment. No attendance source cutover has occurred.

## 24-09-2026: notification click destination and recovery access

Code inspection found notification clicks defaulting to the app root, where
login opens Live Tour without selecting a notification. Routed push deliveries
now carry their persisted delivery ID and an app-local detail URL. The detail
API checks recipient ownership, active profile and current notification routing
and channel grants. Detail UI mounts only after session verification and password
change gates. Legacy admin-system-change clicks route to the changes page.
Recovery status and retry are Admin-only; controls move to a separate menu.
Notification list rows are single-line with ellipsis and a full-detail view;
the rounded dialog has a viewport width cap and a tinted background.
These code/test results do not prove OS lock-screen interaction on a physical
phone. Verify a newly delivered notification after backend/frontend deployment.
Old notifications without a delivery ID cannot retroactively gain that ID.
The prior CI static idempotency test matched the inner retry catch; it now
checks release ordering against the outer action-failure handler, preserving
the requirement to retain the request key on failure.
