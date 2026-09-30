Warning: truncated output (original token count: 38741)
Total output lines: 2098

# Sự cố đăng nhập và tải dữ liệu ngày 13/09/2026


## 29-09-2026 — Tạm ngừng bốn tài khoản; hoàn tất ngừng TimeSoft

Deploy VPS Production #617 đã thành công tại commit 4821fd28. Kết quả chỉ
đọc người vận hành gửi lúc 22:04 xác nhận FaceGate, TimeSoft network=false,
cache mới lúc 22:03:25, 153 dòng, review Gia Anh 79335 đã áp dụng và không
còn unresolved_evidence; còn 56/58 nhân viên pending. Đây là bằng chứng
production của bản #343, không phải bằng chứng bản thay đổi bên dưới đã chạy.

Lúc 22:07:31 +07 người vận hành yêu cầu tạm bỏ chấm công/tính lương đúng
admin, akamen, letan, Ms Tuyết. Năm nhân viên Cậu Tưởng, Nguyễn Thị Sen,
Nguyễn Thị Thu Hiền, Ngô Sĩ Đạt, Vũ Tân sẽ đăng ký Face ID sau; không được
coi năm người này là miễn công/lương, không tạo ảnh, mapping, ca hoặc giờ ra.

Quyết định có phiên bản trong vera_attendance_participation.py, bắt đầu theo
ngày công Việt Nam 29-09. Chỉ khớp username, không khớp vai trò hoặc tên máy.
Loại bốn tài khoản khỏi bản công FaceGate và người nhận cảnh báo chấm công.
Các bảng lương mới có kỳ giao với thời gian tạm ngừng bỏ toàn bộ tài khoản,
không âm thầm tính nửa tháng hay lương 0. Chặn bản nháp cũ/giả mạo khi lưu,
xuất, gửi; áp dụng cả nguồn lịch VERA và TIP. Tiền đã lưu được giữ khi cập
nhật cùng kỳ cho người khác, gồm dòng relational và đầu vào đối soát nợ TIP.
Không sửa hồ sơ, quyền đăng nhập, log gốc, mapping, lương/phạt đang lưu khi deploy.

Để khôi phục một tài khoản, đặt effective_until là ngày bắt đầu tính lại
(exclusive end); giữ interval cũ để không thay lịch sử. Không tự hết hạn khi
Face ID được thêm. Năm người chờ ảnh và mọi thiếu bằng chứng khác vẫn pending.
CLI inspect trả policy ID, excluded_employee_count và excluded_usernames.

Rà soát xác nhận luồng chính đã không kết nối TimeSoft sau cutover. Bổ sung
chặn ở entrypoint JSON/Playwright cũ dùng session có sẵn; tắt tải nguồn TIP
TimeSoft cũ bằng HTTP 410 và hướng sang TIP Live Tour. Worker vẫn chạy outbox
đã commit và luật Auto Check hiện hữu; không xóa cron/credential/archive.
Kết nối FaceGate lỗi vẫn không fallback TimeSoft. Chưa deploy bản này;
CI PostgreSQL và readback sau deploy là bước nghiệm thu bắt buộc.


## 29-09-2026 — FaceGate activation verified; one reviewed Gia Anh identity

Operator-provided production output verifies activation on release bc857f0 at
21:15:59 +07:00: source=facegate, effective_date=2026-09-29,
timesoft_network_enabled=false, cache_fresh=true. A subsequent read-only report
shows last_sync_at=21:19:18 +07:00, proving another publication after activation.
These are timestamped observations, not a guarantee of future connectivity.
Payroll/penalty writes were false. Missing mappings, shifts and unfinished work
remain pending; no system-account exemption has been confirmed.

The remaining identity issue for 29-09 was event 79335 at 16:31:37 +07:00.
The operator explicitly confirmed "Anh Nguyen" is Gia Anh at 21:21:48 +07:00.
A later read-only report matches that event on the device and in the immutable
archive (both references null), verifies the archive digest, and identifies
Gia Anh / Nguyễn Gia Anh / letan with confirmed profile 198, reference
0/0/12910592 on the current address. The mapping confirmation is unchanged from
2026-09-29T04:27:27.238000+00:00.

Add an identity-only, versioned review for that exact timestamp, ID and digest,
requiring the same confirmed mapping and employee. It adds the scan to the
ordinary VERA shift resolver and exposes the review ID in projection/inspection.
It neither assigns a direction nor creates a checkout, shift, mapping or salary.
Raw payload/hash and archived null reference remain unchanged. Reused IDs or
changed evidence/owner/confirmation reject the review; other missing references
still block normally. This does not create a general name alias or change the
two reviewed Yến Linh test scans. The source remains FaceGate.

This review is code-level work pending deployment/production readback. Regression
coverage includes tampering, other unknown scans, missing shifts/checkouts, and
a real PostgreSQL read-only transaction with a pool of one and archive comparison.

## 29-09-2026: tính thử lương cơ bản từ dữ liệu FaceGate

Theo yêu cầu tiếp tục tính công/lương, bổ sung API và nút Admin trong bảng
đối chiếu FaceGate để tính tiền cơ bản cho khối lương giờ/tháng, theo khoảng
1–7 ngày. Đọc cấu hình từng nhân viên và bộ phận đang lưu trong VERA; dùng
công thức hiện hữu để chia giờ Ca 2 trước/sau 22:00 và lương tháng theo công.
Không suy ra lương KTV theo tip từ lượt quét, không cộng phụ cấp tháng vào
một khoảng ngày nhỏ, không thay thưởng/phạt/tạm ứng hoặc gửi phiếu lương.

Nguồn dùng bản projection đã loại hai lượt quét thử Yến Linh theo PR #335.
Nhân viên thiếu ánh xạ, thiếu ngày/giờ vào-ra/ca, ngày đang mở, log chưa đủ,
sự kiện chưa giải quyết hoặc đơn giá chưa cấu hình có tiền null và trạng
thái chờ bổ sung; không tự chuyển thành lương 0. Kết quả đủ đầu vào vẫn là
ước tính theo công thức hiện hữu, chưa xác minh toàn bộ cutover. Các blockers
vẫn được trả để đối chiếu, không bị xóa bằng yêu cầu tính thử.

API chỉ Admin, giới hạn ngày trước khi mở connection; một transaction
REPEATABLE READ READ ONLY và timeout, không gọi máy/đổi nguồn/ghi bảng lương.
Giao diện hiển thị rõ tổng chỉ gồm dòng đã tính, ngày dd-mm-yyyy và không có
thao tác lưu chính thức. Đây là bước tạo kết quả có thể xem xét; chưa hoàn
thành yêu cầu chuyển nguồn lương toàn hệ thống hoặc xử lý hết dữ liệu thiếu.
Kiểm thử công thức với đơn giá riêng, ca đêm, dữ liệu thiếu/null, quyền, giới
hạn ngày, dùng một connection và UI đổi ngày/lỗi/pending. Chưa kiểm chứng số
tiền trên VPS; cần triển khai và chạy đối chiếu dữ liệu thực tế.

## 29-09-2026: loại hai lượt quét thử Yến Linh khỏi bản tính công thử

Người vận hành xác nhận lúc 14:35:40 và yêu cầu áp dụng lúc 14:38:57 giờ
Việt Nam: sự kiện 79329 (14:21:22), 79330 (14:21:24) là quét thử, nhân viên
vẫn làm việc. Hồ sơ đã đối chiếu 217, reference 0/0/14155776; ảnh màn hình
xác nhận cả hai sự kiện được lưu và ánh xạ Yến Linh. Không coi đây là giờ ra.

Thêm ngoại lệ có phiên bản trong mã, không xóa/sửa archive hoặc mapping.
Chỉ loại đúng cặp khỏi dữ liệu đưa vào calculator khi cả hai ID, timestamp,
reference, địa chỉ, tên máy, status/type và chủ mapping xác nhận còn khớp.
Thiếu hoặc thay đổi bằng chứng giữ nguyên dữ liệu và báo blocker. Báo cáo
trả applied_test_scan_reviews để kiểm tra ngoại lệ, trong khi đối chiếu log
thô vẫn giữ cả hai sự kiện. Lượt 09:02:57 và lượt ra thực tế về sau giữ nguyên.

Đây mới là sửa shadow projection, chưa thay nguồn công/lương chính thức,
chưa ghi review PostgreSQL hay xác minh bản sửa trên VPS. Báo cáo 14:29 còn
năm nhân viên chưa ánh xạ, bốn sự kiện An An/Lê My thiếu reference, thiếu
TimeSoft lịch sử 26–28, chênh lệch ngày công qua đêm, ngày hiện tại chưa đóng
và các gate xác minh status/cutover. Không bỏ qua các blocker này.

## 29-09-2026: đăng ký Face ID mới từ hồ sơ VERA

Người vận hành xác nhận năm nhân viên chưa đăng ký khuôn mặt và yêu cầu
chọn ảnh trong VERA rồi gửi lên máy. Thêm nút đăng ký trong FaceIdCard,
API yêu cầu đồng thời quyền quản lý Face ID và ánh xạ thiết bị, xác nhận đúng
người và hash ảnh đang lưu. Quyền tự thay ảnh không cấp quyền ghi máy.

Adapter dựa trên nguồn bwlist.asp/js/bwlist.js người vận hành cung cấp ngày
28-09: upload multipart vfileselector với LISTADD, IsCheckSim=1; poll
getUploadPercent; setWhitelist action=add, uid=-1; sau đó đọc lại danh sách
đầy đủ và hồ sơ riêng. Chỉ thành công khi tên, token lần ghi và tham chiếu
ảnh chính xác. Máy tự cấp UID. Không tự chọn UID hoặc ghép theo tên.
JPEG vận chuyển giữ tỷ lệ, không thay ảnh gốc đã lưu. Không thay ảnh đăng ký
hiện có vì việc đó cần bảo toàn lịch sử tham chiếu qua một quy trình riêng.

Nhật ký PostgreSQL được commit trước mỗi thao tác ghi máy. Unique partial
index chỉ cho một lượt chưa hoàn tất trên thiết bị. Không giữ transaction
hoặc pooled connection trong lúc gọi mạng. Mất phản hồi sau thao tác ghi
chuyển sang chưa xác minh; nhấn lại không gửi ảnh/lưu hồ sơ lần hai. Nút kiểm
tra lại chỉ đọc máy và hoàn tất ánh xạ nếu bằng chứng khớp. Trường hợp tiến
trình chết trước bước lưu hồ sơ cần đối chiếu nhật ký, không tự giải phóng
lượt để tạo hồ sơ lặp. Khi lưu ánh xạ phải kiểm tra lại IP, nhân viên và xung
đột quyền sở hữu dưới khóa; không ghi đè ánh xạ cũ.

Đây là tính năng đăng ký mới, không xác nhận năm nhân viên đã được đăng ký.
Chưa kiểm thử ghi/nhận diện trên máy thật. Ngày 29-09, người vận hành đã
cung cấp đầy đủ sendBTNSetting: action=list dùng GET; action khác dùng POST,
nonce tám ký tự ở cả nRanId và body, Content-Type text/html; charset=UTF-8.
Đã sửa setWhitelist sang POST theo bằng chứng này, giữ query và Basic Auth
phía máy chủ, không retry thao tác ghi. Kiểm thử xác nhận đúng method/body/header.
CI/PostgreSQL và thử một đăng ký có ảnh được người vận hành chọn là các
bước nghiệm thu còn lại. Nguồn tính công, lương/phạt và tám blocker không
được mở khóa bởi tính năng này.

## 29-09-2026: FaceGate đổi IP và giữ bằng chứng lịch sử

Kết quả do người vận hành cung cấp xác nhận tuyến Tailscale ban đầu chỉ tới
IP cũ; sau bổ sung tuyến máy mới, đọc thiết bị thành công. Bước xác nhận lại
51 ánh xạ đã commit và đọc lại thành công sau khi đối chiếu chính xác ID hồ sơ,
tham chiếu đăng ký và tên máy. Lần preview tiếp theo đọc đủ 40 sự kiện, khớp
40, chưa khớp 0. Worker báo kho ngày 28 có 148, ngày 29 có 40, thêm mới 0.
Đây là các snapshot do người dùng gửi, chưa chứng minh chuyển nguồn tính công.

Mã cũ so địa chỉ hiện tại với địa chỉ trong mọi payload/review, nên đổi IP
làm lịch sử nguyên vẹn và ngoại lệ checkout đã lưu bị từ chối. Bản sửa đọc
metadata ip_reconfirmation trên từng ánh xạ hiện tại: đúng người xác nhận,
địa chỉ trước/sau, phương thức đối chiếu, mốc xác nhận và reference chính xác.
Chỉ bằng chứng trước/đúng mốc đó được chấp nhận từ địa chỉ cũ. Không dùng
fallback tên cho địa chỉ cũ hoặc cho tham chiếu thiếu, không tạo alias IP chung.
Xác nhận ánh xạ khác về sau làm metadata cũ mất hiệu lực.

Review vẫn kiểm tra hash nguyên bản, chủ sở hữu, ID hồ sơ, năm sự kiện, thời
điểm, vai trò và ca. Đọc lại case sau đổi IP không tạo review mới. Không sửa
payload/hash/archive, không ghi lại review, không mở connection hoặc gọi máy
trong projection. Nguồn chấm công, lương/phạt và các gate chuyển nguồn giữ
nguyên. Bản sửa này chỉ xử lý lịch sử sau chuyển IP đã được xác minh.

Kiểm thử gồm địa chỉ thứ ba, thiếu/sai reference, thời điểm sau chuyển IP,
metadata thiếu/sai, xác nhận lại khác, status lạ, bảo toàn input và kiểm tra
review cũ/idempotency/fingerprint. Chưa xác minh bản sửa trên VPS. Những vấn
đề dữ liệu chưa ánh xạ, sự kiện thiếu định danh, tham chiếu TimeSoft và ngữ
nghĩa status/type vẫn phải xử lý trước khi bật nguồn chính thức.

## 28-09-2026: Lễ tân/Quản lý xóa lịch được nhập trong ngày

Theo yêu cầu mới, thêm ngoại lệ xóa riêng cho letan/quanly khi created_at
của bản ghi thuộc ngày hiện tại theo giờ Việt Nam, không phụ thuộc ngày nghỉ,
nhóm lý do hay người nhập. created_at lấy từ dòng PostgreSQL đang khóa, không
nhận từ body, không dùng updated_at/update_date để cấp lại quyền cho dòng cũ.
Timestamp thiếu/không hợp lệ/không có timezone không hưởng ngoại lệ này.

Thêm created_at vào SELECT danh sách và SELECT xóa hiện hữu; không thêm query,
pool hoặc thay cấu hình phân quyền. Ngoại lệ đứng trước guard nhóm cùng ngày
và guard hủy cũ, nhưng chỉ trong đường xóa. Quyền sửa, thêm, Admin, nhân viên
và đường kiểm tra bản ghi cũ giữ nguyên. Xóa batch vẫn kiểm tra hết trước khi
ghi, một dòng không được phép làm rollback toàn bộ. UI dùng cùng mốc ngày
Việt Nam; API kiểm tra lại khi bấm xóa, kể cả trang mở qua nửa đêm.

Kiểm thử đối chiếu UI/server với UTC/Việt Nam, dữ liệu thiếu, bản ghi được sửa
hôm nay nhưng tạo từ trước, nhiều vai trò/ngày nghỉ, bật/tắt guard và batch trộn.
Không xóa bản ghi thật trong quá trình sửa. CI là gate; chưa triển khai VPS.

## 28-09-2026: cột STT và ca tuần hiện tại trong Excel nhân viên

Thêm STT đánh số theo thứ tự danh sách đã lọc, trước Tên nhân viên. Thêm Ca
tuần hiện tại sau Chu kỳ và trước Khóa đăng nhập (ranh giới Z/AA của file cũ;
sau khi thêm STT, cột mới là AB). Tính ca bằng scheduled_shift chung của VERA,
ngày Việt Nam và danh mục ca đã đọc trong staff_result; không đọc check-in,
TimeSoft hoặc thêm truy vấn theo nhân viên. Giữ Ca làm việc là ca gốc để import.
Hai cột mới chỉ hiển thị, không thuộc ánh xạ ghi hồ sơ khi import lại.

Ảnh người dùng cho thấy W–AA không có tiêu đề. Mã hiện tại đã khai báo đủ
nhãn; chưa có file XLSX gốc để xác nhận nguyên nhân mất tiêu đề trong ảnh.
Builder nay ghi tường minh từng tiêu đề dạng text và tăng chiều cao hàng đầu.
Kiểm thử đọc lại toàn bộ nhãn sau middleware định dạng, cả file trống/lọc và
xuất kèm ảnh; kiểm tra vị trí cột, dropdown, STT, ngày Việt Nam/đổi chu kỳ,
ca tùy chỉnh/cố định/chưa hiệu lực và import bỏ qua hai cột chỉ xem.
CI là gate trước merge. Chưa triển khai hoặc xác minh file xuất trên VPS.

## 28-09-2026: cập nhật check-in qua hàng đợi projection hiện hữu

Mã nguồn xác nhận scheduler bảng tua chờ 300 giây, trong khi trình duyệt poll
revision mỗi 3 giây. Đây không phải phép đo độ trễ máy FaceID/TimeSoft thực tế.
Khi ghi cache check-in hôm nay, câu SQL ghi refresh event nay đồng thời đánh
dấu một job gộp trong cùng giao dịch. Giữ hai SQL round trip mỗi lần ghi cache,
dùng connection hiện tại, không thêm poller, pool, thread hoặc request trình duyệt.
Schema queue được khởi tạo cùng cache trước khi writer nhận dữ liệu.

Fingerprint chỉ gồm trường đọc check-in; bỏ metadata ca TimeSoft, tiền công,
thời lượng, dòng trùng và thứ tự dòng. Các nguồn alias/dated/raw cùng ngày dùng
một job. Payload có generation; thay đổi tới trong lúc xử lý phải trở lại pending
khi hoàn tất generation cũ. Giữ lease fencing, retry và phục hồi worker chết.
Không gọi phép tính công/phạt đầy đủ trên job check-in; scheduler 300 giây vẫn
chạy phép tính đầy đủ. Nguồn ca vẫn là lịch VERA, không chuyển sang FaceGate.

Worker hiện có thức tối đa mỗi 2 giây khi rảnh; trình duyệt giữ poll 3 giây.
Do đó bản sửa bỏ chờ tick 300 giây sau khi nguồn đã tới VERA, không cam kết
zero latency từ máy quét. Hash/UPSERT và projection khi dữ liệu đổi vẫn có chi
phí; không suy diễn số SQL round trip không đổi thành CPU/I/O không tăng.
Kiểm thử PostgreSQL dùng pool một connection, rollback cache/event/job, chống
trùng, gộp burst, generation/lease/retry, ngày mới và worker thật mở ca mà không
gọi attendance đầy đủ. CI là gate trước merge. Chưa triển khai/xác minh trên VPS.

## 28-09-2026: xếp cuối tua cho cả đi trễ/về sớm không phép

Người dùng xác nhận quy tắc quay lại xuống cuối áp dụng cho cả Nghỉ không
phép, Đi trễ không phép và Về sớm không phép, gồm nhãn CUỐI TUẦN. Yêu cầu này
thay thế phạm vi chỉ nghỉ nguyên ngày của mục 27-09 bên dưới.

Dùng canonical_reason hiện hữu cho cả ghi nhận nguồn và đối chiếu lại nguồn
trước khi xếp tua. Nghỉ/đi trễ/về sớm có phép vẫn không thuộc quy tắc. Giữ mốc
ngày nghiệp vụ, yêu cầu check-in hoặc Admin gán ca vào ngày sau, thứ tự nhóm,
chống đẩy lặp, lượt YC, quyền sắp xếp và phục hồi vị trí khi đổi nhân viên.
Không thay đổi tính tiền phạt, hóa đơn, connection, query hoặc poller.

Kiểm thử mở rộng sáu nhãn ngày thường/cuối tuần, nhóm có đủ ba loại, không
đẩy ngay trong ngày vi phạm, quay lại ngược thứ tự, ngày mốt, sửa/xóa nguồn và
lưu/replay PostgreSQL với một truy vấn đối chiếu. CI là gate trước merge.
Chưa deploy VPS. Cơ chế vẫn cần dấu ghi nhận nguồn từ ngày vi phạm; không tự
quét lại lịch sử hoặc khẳng định các bản ghi trước nâng cấp đã được xử lý.

## 27-09-2026: giữ thứ tự nhóm quay lại sau nghỉ không phép

Mã cũ chỉ tách người đang nghỉ xuống dưới; khi quay lại, giờ tua cũ đưa họ về
thứ tự trước nghỉ. Projection nay ghi nhận nghỉ không phép nguyên ngày từ
leave_records, cùng ngày nghỉ, ID nguồn và thứ tự Người Thứ N. Chỉ áp dụng khi
đã sang ngày nghỉ kế tiếp và có Ca 1/Ca 2 từ check-in hoặc Admin gán ca trong
ngày. Nghỉ có phép, đi trễ/về sớm, chưa check-in và tên trùng không bị suy diễn.

Nhóm quay lại xuống cuối phần Đi làm, giữ thứ tự Người Thứ N kể cả check-in
ngược thứ tự qua nhiều tick. Những người trong nhóm chưa nhận lượt thường giữ
thứ tự tương đối khi thành viên còn lại quay lại sau. Lượt thường kế tiếp giải
phóng vị trí tạm; lượt YC không giải phóng. Snapshot đổi nhân viên/hủy Thực hiện
giữ vị trí này; Admin vẫn có quyền sắp xếp thủ công. Không sửa giờ bắt đầu dịch
vụ, bộ đếm, hóa đơn hoặc dữ liệu phạt để mô phỏng việc xuống cuối.

Lưu dấu đã xử lý trong employee payload, dùng khóa độc quyền projection hiện
hữu. Chỉ khi còn người chờ quay lại mới đọc lại các ID bản ghi nghỉ trong một
truy vấn trên connection hiện tại để loại trường hợp đã sửa/xóa; không N+1,
không thêm poller hoặc mở pool lồng nhau. Ghi nhận từ ngày nghỉ được projection
quan sát; không quét toàn lịch sử để phạt lại người đã đi làm trước nâng cấp.

Cục bộ 289 kiểm thử đạt, gồm ngày hôm sau/ngày mốt, thứ tự thủ công/tự động,
quay lại ngược thứ tự, correction và tương tác đổi nhân viên. Hai ca PostgreSQL
kiểm tra nguồn thật, ghi/lưu/replay và một query theo ID là gate CI. Chưa deploy
VPS hoặc xác minh lịch nghỉ/check-in thực tế; người dùng deploy thủ công.

## 27-09-2026: booking chung combo và thu gọn thao tác đổi nhân viên

Rà soát mã xác nhận form booking nhiều khách theo phòng chỉ gửi dịch vụ và
customer_id, không gửi combo_purchase_id. Booking đơn đã giữ vé, nhưng nhãn
khách còn hiển thị số vé chưa trừ các booking đang giữ. Đây là bằng chứng mã
và kiểm thử bằng dữ liệu giả, không phải số đo độ trễ hoặc sai lệch trên VPS.

Form nhiều khách nay tự chọn combo/dịch vụ khi chọn khách, cho dùng combo của
khách dòng 1 cho cả phòng và truyền đúng chủ combo ở mỗi booking. Cộng nhu cầu
theo cặp chủ khách/combo và từng dịch vụ; hiện vé khả dụng, số vé cần dùng,
số còn lại và chặn thiếu vé trước khi gửi. Dịch vụ combo trong booking đơn
hiển thị rõ trong ô riêng. Combo vé chung cũ không có danh mục dịch vụ vẫn
yêu cầu chọn dịch vụ, không đoán quyền dùng vé từ tên combo.

Server giữ cơ chế đặt giữ vé trong cùng giao dịch booking: số khả dụng giảm
ngay, booking khác không dùng lại được, hủy trả vé, thanh toán ghi sử dụng một
lần. Batch thiếu vé rollback toàn bộ; các phòng cùng chủ combo dùng khóa khách
hiện hữu. Đổi nhân viên chuyển nguyên booking/reservation và không ghi hóa đơn,
pending, report hay combo_usage cho người bị thay. Luồng đổi nhân viên dùng
snapshot operational gọn và phản hồi board, không đọc lịch sử hóa đơn/báo cáo
hay toàn bộ receipt; vẫn giữ khóa độc quyền vì có thể khôi phục thứ tự cả bảng.

Khách đã chọn trong form được tải theo một danh sách ID giới hạn 50 khách,
dùng một yêu cầu cho cả nhóm bên cạnh tìm kiếm hiện hữu; không N+1 theo dòng.
Revision mới không dùng số vé cũ khi đang tải. Chỉ mount một form/một đồng hồ,
giảm tick từ mỗi giây xuống 20 giây và dừng khi tab ẩn; không thêm poller mạng.

Kiểm thử gồm tự điền/cảnh báo/khóa nút, dữ liệu đổi giữa lúc mở form, giữ khách
đã chọn khi tìm khách khác, dùng chung và hủy từng người, chuyển nhân viên rồi
thanh toán chỉ người thay. PostgreSQL CI kiểm tra batch rollback, replay, khóa
khách giữa phòng khác nhau và phạm vi đọc đổi nhân viên với 0/400 hóa đơn cũ.
Cục bộ 135 kiểm thử Python đạt; các ca PostgreSQL cần service CI. Build/lint
và kiểm thử giao diện đạt. Không tuyên bố không có độ trễ ở mọi tải production;
Deploy VPS Production vẫn do người dùng chạy thủ công sau CI và merge.

## 27-09-2026: đổi nhân viên trả lại vị trí trước lượt không yêu cầu

Tái hiện bằng nhân viên giả: bắt đầu lượt không YC đẩy người đầu xuống dưới;
đổi nhân viên vẫn giữ board_started_at của lượt vừa bị thay nên thứ tự tự động
không trả người đó về vị trí ban đầu. Nhánh phục hồi board_index trước đây chỉ
chạy khi có thứ tự thủ công. Tám ca hồi quy mới đều thất bại trên mã cũ.

Snapshot trước khi bắt đầu lưu thêm giờ bắt đầu thường gốc. Khi đổi nhân viên
ở lượt không YC, phục hồi giờ đó, kể cả giá trị trống; booking đang chạy từ bản
cũ dùng giờ hiển thị đã có trong snapshot. Nếu giờ cũ đã trả đúng vị trí, không
ghi lại nhân viên khác. Nếu các lượt bắt đầu xen kẽ làm thay đổi hàng đợi, chèn
người bị thay vào chỉ số đã lưu, giữ thứ tự tương đối của những người còn lại.
Luồng này dùng khóa độc quyền change_employee hiện có; không thêm query,
connection, poller hoặc gọi mạng. Lượt thường tiếp theo vẫn chạy sắp xếp tự động.

Giữ thời gian dịch vụ, hạn đổi nhân viên, YC, số lượt chuyển sang người thay,
combo, quyền, revision và idempotency. Kiểm thử gồm thứ tự tự động/thủ công,
lượt đầu, lịch sử giờ cũ, refresh, đổi liên tiếp và snapshot trước nâng cấp.
Cục bộ 118 kiểm thử đạt; hai ca HTTP/PostgreSQL cần service CI để xác minh lưu,
replay và từ chối revision cũ. CI là gate trước merge. Chưa triển khai hoặc
xác minh hành vi này trên VPS; Deploy VPS Production vẫn chạy thủ công.

## 27-09-2026: nhân viên tự nhận popup chưa check-in

Mở popup cho leader, nhanvien, locker, tapvu và support với phạm vi chỉ
chính tài khoản đang đăng nhập. Admin/Quản lý giữ quyền xem danh sách;
Lễ tân vẫn chỉ xem leader/nhanvien/letan. Đối tượng Giám đốc/Quản lý vẫn
được loại khỏi danh sách cảnh báo theo yêu cầu trước.

API lấy employee_username từ identity đã xác thực, không nhận tên người
xem từ query/body, không dùng tên hiển thị hoặc bỏ dấu để cấp quyền. Hai
truy vấn lịch ca giới hạn ngay theo username đối với phạm vi cá nhân; vẫn
lọc lại trước khi trả kết quả. Không thêm poller, API, connection hay gửi
mạng. Dùng chung nút ẩn/hiện và Đã xem theo tài khoản. Legacy break-alert
popup được lọc qua cùng helper để không hiển thị trùng với popup mới.

Kiểm thử dùng tài khoản giả: self-only, sai username, tên hiển thị trùng,
khác dấu, thiếu identity, query giả mạo username/role, tự hết cảnh báo khi
check-in/đăng ký nghỉ và quyền Lễ tân không đổi. CI là gate trước merge;
Deploy VPS Production vẫn do người dùng chạy thủ công. Không gửi thử thông
báo tới nhân viên thật hoặc xác nhận giao diện mới đã chạy trên VPS.
Lượt CI đầu: 1890 đạt, 2 kiểm thử booking thiếu vera_dataset_cache vì fixture
trước đây không cần dữ liệu công cho viewer nhân viên. Bổ sung đúng bảng
cache trống vào fixture booking để feed thực hiện đường đọc mới; giữ nguyên
tất cả assertion về người nhận, giao dịch, truy vấn, dedup và quyền booking.


## 27-09-2026: ẩn/hiện popup, Đã xem từng người và lọc cho Lễ tân

Popup thiếu check-in có nút Ẩn thông báo / Hiện thông báo; thu gọn nội dung
vẫn giữ tiêu đề và số người chưa xem để mở lại. Thu gọn không đánh dấu đã xem.
Mỗi dòng nhân viên có nút Đã xem riêng, chỉ lưu khóa của người đó. Giữ lựa
chọn thu gọn theo tài khoản trên trình duyệt và đồng bộ tab bằng storage event;
không thêm API hay poller. Trạng thái Đã xem đã lưu trước đây vẫn được giữ.

Server lọc danh sách cho viewer letan chỉ còn employee_role leader, nhanvien,
letan. Mọi viewer bỏ qua đối tượng giamdoc/quanly; Quản lý vẫn được nhận cảnh
báo về nhân viên theo quyền hiện hữu. Đây là cách hiểu mục “bỏ qua thông báo
với tài khoản giám đốc, quản lý” đã thông báo cho người dùng trước khi sửa.
Vai trò đối tượng lấy từ employees hiện tại, không suy từ department trên
lịch ca. Không thêm truy vấn theo từng người hoặc mở connection khác. Thay
đổi này dành cho popup hiện tại, không đổi phân quyền hay cấu hình push.

Kiểm thử dùng nhân viên giả: ẩn/hiện giữ danh sách, cảnh báo mới tăng số đếm,
Đã xem một người không ẩn người khác, đổi tài khoản giữ lựa chọn riêng; thêm
PostgreSQL coverage cho role đối tượng, viewer lễ tân, nhãn department không
trùng role và role thay đổi. CI là gate trước merge; deployment VPS vẫn do
chủ hệ thống chạy thủ công, chưa xác minh giao diện mới trên production.

## 27-09-2026: popup thiếu check-in và nút Đã xem

Người dùng báo thiếu popup cảnh báo và yêu cầu nút Đã xem. Kiểm tra giao diện
cài đặt production xác nhận kênh popup của loại Thiếu chấm công FaceID đang
tắt. Đã bật riêng Popup trong ứng dụng theo yêu cầu và đọc lại xác nhận;
không đổi kênh push hoặc trung tâm thông báo. Sau làm mới chưa quan sát được
popup thực tế. Không đưa thông tin chấm công/nghỉ của cá nhân vào tài liệu này.

Rà soát mã: popup phụ thuộc current_alerts do full TimeSoft worker ghi, hết
hạn sau 10 phút. Luồng live refresh có cập nhật cache chấm công nhưng không
cập nhật current_alerts. Chưa đọc log worker trên VPS nên chưa kết luận worker
đã dừng hay có lỗi cụ thể. Bản sửa tách popup hiện tại khỏi tiến trình gửi:
đọc tối đa một cache hôm nay theo hai khóa chính xác, đúng source_version,
updated_at trong 10 phút và chưa hết hạn. Đối chiếu roster xoay ca/override,
lịch ngày và lịch nghỉ trên cùng connection; một truy vấn lịch nghỉ cho toàn
bộ nhân viên. Không gọi mạng, không mở pool lồng nhau, không ghi dữ liệu hoặc
tính phạt trên đường đọc; giữ shared notification feed 60 giây. Cache trống,
cũ, ngày khác hoặc tương lai không tạo cảnh báo. Dùng ranh giới ngày như Live
Tour để không coi lần quét 00:30 của ca trước, checkout-only hoặc giờ tương
lai là check-in đầu ca. Không đổi nguồn TimeSoft/FaceGate hay luồng gửi push.

Nút Đã xem và nút X cùng lưu tối đa 200 khóa cảnh báo vào localStorage riêng
cho tài khoản trên trình duyệt/thiết bị này, đồng bộ các tab. Giữ trạng thái
qua refresh, đổi trang và bản feed rỗng; tài khoản khác và khóa ngày/ca mới
vẫn hiện. Không hứa đồng bộ trạng thái Đã xem giữa các thiết bị. Storage bị
chặn thì vẫn tắt trong phiên hiện tại. Popup vàng gọn, nút tối thiểu 44px.

Kiểm thử frontend: 11 trường hợp đạt; build và ESLint component đạt. Bổ sung
PostgreSQL regression với dữ liệu nhân viên giả, ba vai trò, ngày/giờ,
leave, check-in, cache freshness và chặn lấy connection lồng nhau. CI là gate
trước merge. Chưa deploy bản mã mới hoặc xác minh popup mới trên VPS; chủ hệ
thống chạy Deploy VPS Production thủ công rồi xác minh lại.

## 27-09-2026: popup booking trong app cùng thông báo màn hình khóa

Kiểm tra mã xác nhận booking chỉ ghi in_app/push, kênh popup bị ẩn trong cài
đặt nguồn này, và popup chung không được mount trên Live Tour. Bổ sung popup
booking riêng theo mẫu thẻ vàng, hiển thị đúng nội dung và nút Mở Live Tour.
Đóng chỉ lưu tag đã ẩn trong session của tài khoản, không đánh dấu thông báo
Trung tâm đã đọc; đánh dấu Đã xem trong Trung tâm vẫn cập nhật mọi kênh.

Thêm popup vào cùng INSERT theo lô trên connection/giao dịch booking hiện có.
Feed popup dùng chung kiểm tra người nhận hiện tại, tài khoản hoạt động, tên
booking, nguồn/kênh và ngày Việt Nam với Trung tâm. Loại bỏ trường nội bộ khỏi
payload. Component dùng feed sẵn có, không thêm poller/request định kỳ hoặc
truy vấn booking; message push hiện có làm mới feed khi app đang mở. Admin có
thể tắt riêng popup hoặc push. Không gửi thử đến nhân viên thật. Kiểm thử mô
phỏng giao diện và PostgreSQL không xác nhận điện thoại thật hay VPS; người
dùng vẫn chạy Deploy VPS Production thủ công.

## 27-09-2026: thông báo booking đúng nhân viên, ghi theo lô

Theo yêu cầu, booking và multi_booking ghi thông báo sau khi kiểm tra nghiệp vụ
và chống trùng, trước khi ghi state, trên connection/giao dịch hiện có. Một câu
INSERT theo lô ghi cả Trung tâm và push cho tài khoản đang hoạt động có tên hệ
thống khớp nhân viên được booking. Nội dung lấy từ kết quả server: tên | dịch vụ
| YC hoặc Tua | phòng/giường; không gửi dữ liệu khách hoặc ghép theo tên gần đúng.

Không đọc lại bảng booking, không đọc subscription, không mở connection hay gửi
mạng trong thao tác booking. Thêm một SAVEPOINT/RELEASE quanh INSERT để lỗi riêng
của kho thông báo không phá booking. Rollback nghiệp vụ hủy cả thông báo; retry
cùng idempotency_key không ghi lại. Worker hiện có gửi sau commit và kiểm tra lại
công tắc Admin, tài khoản, tên nhân viên và lựa chọn tắt theo thiết bị. Không thêm
worker/timer/request frontend. Kiểm thử PostgreSQL đo số statement/connection;
đây không phải số đo độ trễ thực tế của VPS.

Thêm Booking cho nhân viên vào Cài đặt thông báo với công tắc toàn loại và từng
kênh. Người nhận cố định theo booking, không cho cấu hình thành gửi toàn bộ nhân
viên. Menu giảm chiều cao, bỏ dòng ghi chú “Tắt ở đây vẫn nhận…”. Đồng hồ phòng
Live Tour bỏ chữ “Còn”, giữ giá trị và logic trễ/hết giờ. Chưa xác minh điện thoại
thật hoặc production; Deploy VPS Production vẫn do người dùng chạy thủ công.

## 27-09-2026: hợp nhất thông báo và công tắc theo thiết bị

Kiểm tra mã xác nhận inbox chỉ đọc kênh in_app, nút mở chỉ dành cho Admin,
trong khi nhiều nguồn mặc định chỉ gửi trực tiếp tới thiết bị đã đăng ký.
Đồng bộ Web Push khi focus có thể đăng ký lại sau khi người dùng tắt.
Ảnh gửi lúc 13:28 hiển thị Trung tâm rỗng; không đủ để xác định sự kiện
nào đã phát sinh trên production.

Dùng outbox chung cho nguồn mặc định và route cấu hình, cùng quyền người nhận.
Inbox gộp hai kênh theo sự kiện/route; Đã xem cập nhật cả hai bản ghi. Mọi tài
khoản có nút Trung tâm và công tắc màn hình khóa trong Menu. Tắt chỉ áp dụng
cho trình duyệt/app đang dùng, giữ inbox và thiết bị khác. Lưu lựa chọn tắt,
không tự đăng ký lại khi focus/reload. Service worker kiểm tra thiết bị và chủ
sở hữu trước khi hiển thị; đăng xuất/đổi tài khoản đóng thông báo cũ. Không đưa
danh sách người nhận nội bộ vào payload trả cho trình duyệt.

Kiểm thử thiết bị dùng trình duyệt mô phỏng, bao gồm iPhone standalone/Android,
permission, tải lại, API offline, đăng ký đến muộn và đổi tài khoản. PostgreSQL
kiểm tra quyền hiện tại, override, nguồn/kênh tắt, dedup, đọc hai kênh, rollback
và gửi mạng sau khi trả connection. Không gửi thử thông báo tới nhân viên thật.
Chưa xác minh trên điện thoại thật hoặc VPS. iPhone cần iOS 16.4+, Thêm vào Màn
hình chính và cấp quyền từ thao tác Bật; OS quyết định hiển thị trên màn hình
khóa theo cài đặt thông báo/Focus. Deploy VPS Production vẫn chạy thủ công.

## 27-09-2026: Booking bị từ chối khi đổi ngày nghiệp vụ lúc 11:10

Ảnh người dùng ghi nhận đặt lịch `90 PR VIP` tại giường `20.1` báo
“Cấu hình đã đổi. Hãy làm mới rồi thử lại.” Deploy VPS Production
[36298048116](https://github.com/veraspabienhoa/Vera-Spa/actions/runs/36298048116)
đã xác minh API và frontend ở commit `1e215ece`, cùng cả hai health. Đây
không phải bằng chứng booking thành công và không đủ để suy ra độ trễ VPS.

Kiểm thử API với PostgreSQL thật ở commit `aacb8b8`,
[run 36299337789](https://github.com/veraspabienhoa/Vera-Spa/actions/runs/36299337789),
tái hiện đúng HTTP 409/thông báo trong ảnh tại 11:10:00, 11:10:01 và sau đó;
11:09:59 vẫn thành công. `_apply_action_impl` cập nhật `business_date` từ đồng
hồ server, nhưng resource writer coi trường này là cấu hình không được phép
đổi dưới khóa độc lập. Ngày bộ đếm đã đổi lúc 10:00 nên không chặn luồng này
sớm hơn. GET/làm mới trình duyệt không sửa được sai lệch phân loại đó.
Chưa đọc trực tiếp metadata giao dịch lỗi của production; đây là nguyên nhân
đã tái hiện tương ứng với triệu chứng, không phải suy đoán từ riêng video.

Bản sửa cho phép ngày nghiệp vụ do server tính đi qua khóa độc lập. Ngày được
gộp bằng GREATEST ngay trong câu UPDATE xuất bản revision hiện có, để giao dịch
trước 11:10 commit muộn không kéo ngày lùi lại. Không thêm query/connection,
không đổi mốc ngày, không ghi lại lịch sử. Cấu hình thật vẫn cần khóa phù hợp;
khóa phòng/nhân viên, revision, chống trùng, chuyển bộ đếm 10:00 và rollback
được giữ nguyên. Không retry tự động lỗi 409 bằng payload cũ.

Xem [báo cáo kiểm chứng booking](live-tour-booking-rollover-2026-09-27.md) cho
số đo trên dữ liệu giả, phạm vi chưa đo và bước Deploy VPS Production thủ công.
Bản ghi này không xác nhận production đã nhận bản sửa.

## 27-09-2026: tám điều chỉnh giao diện và popup thiếu check-in (chờ deploy thủ công)

Đối chiếu đủ bảy ảnh người dùng gửi: thêm lọc số tiền TIP chính xác (kể cả
tham số xuất Excel), bố trí năm bộ lọc trên một hàng desktop cho Doanh thu
và Tiền Tip. Tổng mua theo bộ lọc nằm gọn tại đầu bảng mua hàng, tính toàn
bộ kết quả lọc trước phân trang. Hai hàng thống kê nhân viên giảm chiều cao,
thanh tìm kiếm có Clear, các nút và bộ lọc được chia lại độ rộng. Bảng lương
hành chánh trên mobile dùng chữ 11–12 px, cho cuộn ngang trong khung bảng
thay vì ép hơn hai mươi cột và ô nhập tiền vào chiều rộng điện thoại.

Auto mở Đến ngày ở hôm nay theo giờ Việt Nam, cập nhật khi sang ngày mới
và khi quay lại tab. Ngày lịch sử do người dùng chọn được giữ; nút Dùng ngày
này bật lại theo ngày hiện tại. Các lần cập nhật chỉ đọc, không tự lưu kỳ
hay ghi số tiền. Giữ kiểm tra ngày nhập dở và bỏ phản hồi báo cáo cũ đến muộn.

FACE ID tải trước ảnh gần nhất trong ngày đã chọn, sắp theo thời gian rồi
mã sự kiện; xem ảnh khác không tự lưu. Chọn ảnh này mở bước xem/xác nhận ảnh
gốc hiện hữu. Danh sách vẫn là ảnh của thiết bị, chưa xác minh danh tính;
không đổi ánh xạ, nguồn tính công hay đăng ký ảnh lên FaceGate. Hủy phản hồi
ảnh cũ khi đổi lựa chọn và giải phóng URL ảnh khi đóng/đổi ngày.

Mã cũ chỉ ghi danh sách thiếu check-in cho giao diện khi route thông báo
trả false; route đã cấu hình làm danh sách rỗng. Danh sách hiện tại nay độc
lập với thành công gửi push. Admin/letan/quanly đọc danh sách qua notification
feed hiện hữu, trên cùng connection, không gọi thiết bị hay mở pool lồng nhau.
Popup hiện cả ở Live Tour, chống lặp sau khi ẩn, bỏ người đã check-in/nghỉ
khi bản đồng bộ mới cập nhật, và hết hạn sau tối đa 10 phút hoặc hết ngày.
Tôn trọng tắt loại thông báo/kênh popup. Nếu lần đọc TimeSoft không có dữ
liệu, xóa cảnh báo hiện tại thay vì coi toàn bộ nhân viên là vắng mặt.

Giữ ngưỡng quá giờ bắt đầu ca 15 phút; cập nhật theo worker TimeSoft sẵn có
(5 phút) và feed giao diện (60 giây). Chỉ VERA phân ca: resolver xoay ca,
ngày hiệu lực, Admin gán ca trong ngày, lịch làm/nghỉ theo ngày. Loại bỏ
fallback giờ ca từ TimeSoft, bỏ lịch người đã nghỉ việc/xóa, giữ lịch Nghỉ
để nó chặn fallback ca mặc định. Gửi mạng ở ngoài transaction; đọc overrides
hỗ trợ cả kho aggregate và resource trên connection của caller.

Kiểm thử frontend cục bộ đã qua các trường hợp lọc, phân trang, ngày cũ,
sang ngày mới, quyền xem popup, cảnh báo hết hạn, chọn ảnh và phản hồi muộn;
build và lint không có lỗi mới. Lượt CI đầu có 1843 kiểm thử Python đạt; 4 assertion về cấu trúc ngày và
header Excel cần cập nhật theo hành vi mới. Kiểm thử ảnh/popup dùng React
act thay cho chờ cố định để ổn định trên CI. CI PostgreSQL/pytest là gate
trước merge.
Không tự kích hoạt Deploy VPS Production cho đợt sửa này theo yêu cầu người
dùng. Chưa xác minh giao diện và hành vi mới trên VPS; cần xác minh commit,
frontend, hai health endpoint và thao tác thực tế sau lần deploy thủ công.

## 27-09-2026: Capture Log hiển thị ảnh nhưng lưu FACE ID bị từ chối định dạng

Ảnh người dùng lúc 10:14 cho thấy nút Lưu ảnh FACE ID trả lỗi chỉ nhận JPEG,
PNG hoặc WebP. Proxy Capture Log cho phép BMP/GIF, trong khi luồng lưu ảnh gốc
mới gửi nguyên blob sang API chỉ nhận ba định dạng trên. Kiểm thử HTTP bằng
BMP thực tái hiện thông báo trên API cũ. Chưa có byte gốc của ảnh production
để xác định chính xác định dạng ảnh trong ảnh chụp màn hình.

Luồng chọn ảnh Capture dùng endpoint riêng, nhận tối đa 4 MB như proxy thiết
bị và xác minh giải mã raster trước khi lưu. BMP/GIF tĩnh chuyển sang PNG
không mất điểm ảnh nếu đủ nhỏ; ảnh lớn nén WebP trong giới hạn lưu 700 KiB.
Giữ toàn khung, kích thước và tỷ lệ; JPEG/PNG/WebP hợp lệ dưới giới hạn giữ
nguyên byte gốc. Không chỉ đổi đuôi/MIME. Từ chối ảnh động, tệp hỏng, ảnh quá
6000 px mỗi chiều hoặc 24 megapixel. Chính sách CCCD và API ảnh thường giữ nguyên.

Kiểm tra quyền xem lịch sử thiết bị và sửa FACE ID trước xử lý ảnh, trả kết
nối trong lúc giải mã/nén, rồi kiểm tra lại quyền trong transaction lưu.
Bắt buộc điều kiện ảnh cũ; retry cùng nội dung sau chuyển đổi không ghi lại,
hai người cùng thay ảnh vẫn chỉ một thành công. Chỉ dùng blob đã xem, không
gọi lại thiết bị, không đổi ánh xạ hay đăng ký ảnh lên FaceGate.

Deploy 36287704014 đã xác minh commit 5880b294, hai health endpoint, frontend
và user cron mỗi phút lúc 09:11. Kết quả VPS người dùng gửi sau đó xác nhận
lấy log thành công: 26-09 có 126 sự kiện, 27-09 có 56, lượt sync thêm 0; mẫu
readiness 20/126, ánh xạ hợp lệ 0. ConnectionError lúc 08:34 không còn xảy ra
trong lượt đọc này. Đây là bằng chứng trước bản sửa định dạng, chưa xác nhận
lưu ảnh sau sửa trên production; TimeSoft vẫn là nguồn tính công.

## 27-09-2026: mặc định TIP, lọc tiền, đổi khách hóa đơn chờ và kiểm tra phép năm

Ảnh người dùng cho thấy Manual mở Từ ngày tính TIP ở 16-09-2025 dù đang
ở tháng 09-2026. Mã đọc lại kỳ TIP đã lưu, không tính kỳ hiện tại. Khi mở
Manual, dùng ngày 01 hoặc 16 của tháng hiện tại theo giờ Việt Nam; Đến ngày
lấy ngày giao dịch cuối trong sổ Manual (bỏ dòng đã xóa và ngày tương lai).
Nếu chưa có báo cáo, dùng hôm nay. Chọn ngày rõ ràng vẫn được giữ trong
phiên xem. Khi báo cáo chưa tới đầu kỳ mới, tổng Thu/Chi vẫn hiển thị tới
ngày báo cáo cuối và TIP kỳ mới bằng 0. Không sửa số tiền hay dữ liệu cũ.

Báo cáo/Doanh thu thêm lọc Tổng tiền chính xác; Excel dùng cùng điều kiện.
Hóa đơn chờ cho đổi khách và combo: kiểm tra khách còn hoạt động, quyền xem
khách, số lượt và thành phần combo, giữ chỗ trong giao dịch hiện hữu; khóa
cả khách cũ và mới, giữ idempotency. Trả lượt giữ chỗ khi chuyển về khách
lẻ. Không trừ vé trước checkout, không sửa nhân viên hoặc hóa đơn đã thu.

Mỗi đơn Phép năm chờ duyệt có nút Kiểm tra riêng. API chỉ Admin, đọc đúng
khoảng ngày của đơn trên một connection; không đồng bộ/ghi lại toàn bộ
lịch sử. Tách đã duyệt/chờ duyệt, đếm nhân viên duy nhất, bỏ người đã nghỉ
việc, đơn không duyệt, phần thời gian sau ngày quay lại làm. Chỉ trang
Đăng ký nghỉ bỏ tự lưu (đăng ký mới và sửa danh sách), giữ nút Ghi/Lưu.

Bổ sung kiểm thử giao diện, API, Excel, ranh giới kỳ TIP, PostgreSQL thực
và replay hóa đơn chờ. Đây là sửa mã và kiểm thử tổng hợp; chưa xác nhận
dữ liệu hay phiên bản đang chạy trên VPS production.

## 26-09-2026: thêm giường khi phòng đang dùng và xung đột giữa nhiều người

Hai ảnh người dùng gửi lúc 23:31 cho thấy lưu khu vực bị chặn bởi revision
toàn bảng và bởi việc khu vực còn dịch vụ chưa thanh toán. Mã xác nhận
_service_area_change chặn mọi sửa đổi ngay khi có bất kỳ giường được tham
chiếu, kể cả thêm giường mà không đổi giường đang phục vụ.

Cho phép thêm phòng/giường, giữ ID và tên booking của giường đang dùng. Chỉ
chặn đổi tên/chuyển loại/xóa vị trí đang được tham chiếu bởi phiên mở hoặc
hóa đơn chờ. Quy tắc khóa toàn phòng PR vẫn áp dụng cả với giường mới.

Khu vực trả version riêng; biểu mẫu giữ version lúc mở, gửi lại làm điều
kiện so sánh trong giao dịch đã khóa. Các thay đổi ngoài khu vực không làm
hỏng việc lưu. Hai người sửa cùng khu vực có một người nhận 409 cụ thể;
tải danh sách mới không tự nâng version cho nội dung cũ. Mở bản mới nhất
cần xác nhận thay nội dung chưa lưu. Replay cùng idempotency key trả kết
quả cũ trước khi kiểm tra version, không thêm trùng giường. API cũ vẫn giữ
kiểm tra revision; quyền server không thay đổi.

Trong resource mode, lưu khu vực dùng snapshot riêng gồm rooms/employees/
pending và một receipt, ghi rooms/audit theo batch; không tải lịch sử
hóa đơn, báo cáo hay hàng nghìn receipt. Trả receipt ngay sau commit rồi
giao diện tải danh mục riêng. Vẫn giữ exclusive maintenance fence ngắn để
kiểm tra tham chiếu nhất quán với booking/thanh toán. Revision của phòng
được kiểm tra theo phòng vật lý (gồm giường cùng phòng PR); thay khu vực
không còn tăng cấu hình toàn bảng gây xung đột cho phòng khác.

Kiểm thử mô phỏng hai admin lưu đồng thời, phòng khác cùng thành công,
cùng phòng trả xung đột thật; kiểm tra dữ liệu tài chính giữ nguyên, thêm
giường ở cả trạng thái chờ/đang làm/chờ thanh toán, PR, replay và SQL ghi
theo batch. UI kiểm tra giữ draft, không retry 409, retry 503 khóa bị từ
chối với cùng ý định/key và không báo lưu thất bại khi chỉ lỗi tải lại.
Đây là kiểm thử trên fixture/CI PostgreSQL, chưa phải phép đo tải VPS.

## 26-09-2026: sổ Thu Chi không giới hạn ngầm ngày và theo dữ liệu mới nhất

Theo yêu cầu tiếp theo, mặc định Tất cả của cả Manual và Auto đọc toàn bộ
dòng hiện có, kể cả trước 05-09-2025, không cắt theo kỳ TIP hoặc ngày cố định.
API và Excel nhận live_ledger, được truyền qua wrapper V2 thật. Khoảng ngày
hiển thị lấy ngày đầu có dữ liệu đến ngày mới nhất (ít nhất là hôm nay tại
Việt Nam); bộ lọc Tùy chỉnh và Ngày do người dùng chọn vẫn có hiệu lực.
API cũ và các thẻ tổng/TIP giữ kỳ báo cáo đã chọn; không đổi số tiền đã lưu.

Manual, Auto và Manual/TIP tự động dùng chung kiểm tra revision mỗi 5 giây
khi trang hiện, tải lại khi dữ liệu …13741 tokens truncated…ược ghi đè phiên hợp lệ. Tiếp tục giữ
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

## 26-09-2026: browser work when switching Revenue tabs and application pages

A user recording shows delayed tab changes on Revenue. It does not establish the
current deployed backend revision or isolate network latency. Source inspection
confirms three browser costs: the shell's one-second clock reconstructs business
page children, customized labels search the entire document once per repeated
row, and Revenue/report tables mount the full result set on each tab change.
The Revenue ledger and purchase tabs also reload the same detail endpoint.

Isolate page content from shell-only renders, resolve custom label owners locally,
and subscribe each label only to its own value. Paginate Revenue and Live Tour
report tables at 100 displayed rows, keeping totals, filters and Excel exports
on the complete result set. Index invoices once for report-row lookups. Reuse the
loaded Revenue detail payload across its two tabs; existing source/mutation/refresh
revisions invalidate it and Auto retains its 30-second visible refresh. Prefetch
page code on authorized menu hover/focus without mounting a page or loading its
business data.

The shared API transport coalesces only concurrently pending identical GETs,
isolated by authorization headers and request policy. There is no response or
identity cache; independent readers can cancel without cancelling each other.
Writes, uploads and session application clear the pending registry, so later
reads cannot join pre-change work. Authentication checks and financial write
retry/idempotency behavior stay on their existing paths.

Regression fixtures cover 3,000 rows with 100 rendered rows, complete totals and
export filters, one detail request across Revenue tab switches, refresh after a
shared mode change, ten identical concurrent reads using one HTTP request,
independent cancellation, account separation and module-load recovery. These are
local automated checks, not production latency measurements. Validate the actual
business tabs and health endpoints after deployment before claiming resolution
of all production slowness.

## 26-09-2026: Live Tour keeps only the pending-payment overlay

The user marked two empty areas in a screenshot: the shell's reserved feedback
slot above the board and Live Tour's reserved action-feedback slot below the
header. Remove both from Live Tour, including their notices and reserved height.
Suppress general popup, birthday/break and profile-completion banners on this
page; other pages and notification delivery settings keep their existing behavior.
The pending-payment reminder is now a fixed, viewport-bounded portal with Close
and Open list controls, below transaction dialogs in stacking order. It creates
no placeholder in the board and uses the existing pending-view permission and
reminder schedule. Closing it does not clear invoices; zero pending bills removes
it. Open list is explicit navigation to the existing pending-payment panel.

Remove transient board-only message state while preserving operation busy guards,
failed-save drafts, form-level errors, revision checks, idempotency keys and all
financial action payloads. Updated regressions verify no banner insertion during
saving/failure, portal placement/dismissal/list navigation, permission denial,
retained drafts and room action payloads. This entry describes code and automated
checks; it is not a claim of a completed production payment or browser latency
measurement.

## 26-09-2026: opening Leave Registration clears the React screen

The user recording shows Live Tour disappearing into a blank page after opening
Leave Registration. Mounting the actual leave page with all three enhancement
components reproduces NotFoundError from LeaveListPersonalStats.insertBefore:
StableDataRegion now wraps the table, so leave-list-wrap is no longer a direct
child of leave-list-panel. Passing that nested node as the panel's insertion
anchor throws during a React effect and tears down the application tree.

Resolve the direct child ancestor of the table before inserting the statistics
portal host. Keep the existing table/loading wrapper, month-scoped data reads,
quota checks and permission rules. The new CI integration test mounts the real
page and all enhancements together under StrictMode, for Admin, Lễ tân and Nhân
viên; it checks open/reopen, one summary host, quota access and a failed records
read without losing the form. The older isolated quota fixture had a flat table
layout and could not catch this integration failure. This frontend fix does not
require a database migration or VPS restart. Local reproduction and tests are
not a claim of an authenticated production leave write.

## 26-09-2026: repeated Leave Registration opening failure and page recovery

The operator reports that opening Leave Registration still fails after PR #285.
The Pages workflow for aec96028 completed successfully, but this is not proof of
an authenticated browser operation. The earlier recording shows the older inline
pending-payment banner. It does not prove which assets the latest browser loaded.
Direct app/health reads from the maintenance environment timed out or were denied;
do not interpret those results as production health or change server settings.

A broader regression now bundles the actual App, AppShell, LiveTourPage and leave
route plus the production startup DOM enhancers, with synthetic API/auth fixtures.
Opening/reopening Leave Registration succeeds on #285 with these fixtures. The
latest operator failure has not been reproduced with production data or layout.
However, source inspection confirms that rejected lazy page imports automatically
reload the entire app (losing the selected page), then can escape Suspense, which
only handles loading and is not an error boundary. Other page render/effect errors
also tear down the shell. Injecting a leave statistics render failure reproduces
that loss of navigation on the previous code.

Wrap business page content in a keyed error boundary, keep the shell/menu alive,
and replace automatic full-app reload with explicit lazy-module retry. A rejected
React.lazy needs a fresh instance as well as eviction of the rejected loader
promise. Provide a same-origin new-tab link to the selected standalone page with
a fresh query key; it loads the current entry document without interrupting the
existing tab. Session verification/password-change gates and default Live Tour
routing remain unchanged. No successful write is automatically retried.

Tests exercise full-app navigation with startup enhancers and nonempty violation
catalogs, render-error recovery, repeated module-load failures followed by success,
month-scoped reads, existing role gates, auth recovery, preserved form/focus on
normal refresh, and reopen after recovery. The old App fails the navigation-loss
assertion and the updated App passes it. This hardens a confirmed failure mode;
it is not a claim that the latest operator-specific cause or a real leave write
has been verified on production.

## 26-09-2026: user-requested rollback of Leave Registration only

At 15:10 ICT the user requests the older Leave Registration version after a new
recording still shows a blank screen even through the fresh standalone URL. The
underlying production exception remains unknown; do not claim the recovery layer
resolved it. Restore this feature from edbb05160494d1ff18c1941a02645774fdfa8f43
(PR #279, before the #281 page-stability changes). This snapshot retains month-only
queries, quota checking, employee self-service and current leave edit policies.

Restore LeaveRegistrationPage's original feedback/table structure and loading-row
behavior plus its matching LeaveListPersonalStats. LeaveRegistrationEnhancements
and LeaveListTypeColumn are byte-identical between that snapshot and current main.
The sole compatibility addition to the old page is the existing usePageRefresh
subscription/busy guard so the current shell's Refresh button still works. Restore
neither the database nor the shared shell, Live Tour, payments, Revenue, auth,
notification configuration, caches or cleanup jobs. Do not delete leave records.

Regression coverage uses the real page and all enhancements, the direct table
parent expected by the original statistics portal, Admin/Manager/Reception/Staff
roles, current-month quota arguments, loading/error rows, bounded refreshes and
reopening from the current Live Tour. CI remains required before frontend deploy.
The requested rollback is a scoped mitigation; production opening still needs
confirmation on the user's browser.


## 27-09-2026: attendance-code review, combo directory and device/photo removal

The owner requests TimeSoft attendance-code discovery for manual FaceGate mapping,
customer selection by name/phone in schedule combo sales, a row per remaining
customer purchase, and role-scoped device/photo deletion. This change is code-level
work; no production database write or new FaceGate attendance cutover is claimed.

The attendance catalogue projects only name, phone and the two distinct TimeSoft
code fields from saved datasets. It does not call attendance projection, re-ingest
FaceGate events or infer a FaceGate profile ID. XLSX preview is bounded and read-only;
ambiguous matches and reused codes cannot auto-fill a confirmed mapping. Confirmation
still validates the actual FaceGate profile using the existing route.

Schedule combo lookups read only the canonical customer collection, reuse the
caller connection during save, and validate the newest nondeleted purchase date.
Selecting a customer fills the fields; explicit Add/Save remains the operation
that records a commission sale. Older imports and historical edits stay compatible.
The customer table shows separate remaining purchases and right-aligned actions.

Only Admin can remove registry entries, including through bulk registry writes.
Deletion shares the existing revision check and locked writer; saved attendance is
not removed. Removing the FaceGate profile blocks new adapter I/O until the profile
is restored. USB discovery now requires the explicit discovery button so a removed
device is not immediately re-added by a browser reconnect event.

Admin, Manager and Reception have a distinct stored-photo deletion permission.
Photo deletion preserves event ID, upload digest and confirmed attendance. Replaying
the original upload cannot restore a deleted photo. Confirmation and deletion lock
the same event; an unconfirmed event with a deleted photo cannot be confirmed.
Photo-only access does not grant capture or attendance-confirmation privileges.
Regression tests cover these behaviors, stale gallery reads, permission boundaries,
canonical combo matching and compact reads in both PostgreSQL storage modes.


## 27-09-2026: TimeSoft XLSX declared dimensions hide actual attendance rows

Two operator exports for 26-09-2026 were compared read-only. FaceGate Control Log
contains 126 unique event IDs and 126 unique timestamps for 40 machine names.
TimeSoft has 126 detail events for 40 staff, plus 40 daily summary rows. All 126
timestamps match to the second. Six names differ beyond accents; their event
sequences match. These are comparison candidates, not newly confirmed FaceGate
profile mappings. No employee data or original files are committed here.

The TimeSoft XML declares A1:K4 for its summary and A1:F2 for detail despite later
rows in sheetData. openpyxl read_only trusts those dimensions, so the new attendance
code preview read just two source rows instead of the full report. Earlier manual
analysis using the same read-only default also understated the available codes.
Reset declared dimensions before streaming and enforce limits against actual rows
and columns. The supplied report then yields all 40 distinct attendance codes.
Tests cover understated/overstated row and column metadata, leading-zero codes and
actual row/column limits. Existing ZIP/upload bounds remain enforced. This fixes
the preview reader; it does not alter XLSX inputs, saved attendance or mappings.

## 27-09-2026: FaceGate attendance rehearsal before TimeSoft cutover

The operator requests confirmed mapping completion and direct FaceGate attendance.
The supplied comparison exports do not contain device profile IDs/registration
references, so their 126 matching timestamps cannot authorize bulk identity writes.
No new production mapping, successful VPS deployment or source switch is claimed.

An Admin-only installed API and Check-in History panel now adapt saved FaceGate
events into the existing VERA attendance reader with explicitly supplied datasets.
Production readers keep TimeSoft. The preview reuses one caller connection in a
PostgreSQL REPEATABLE READ, READ ONLY transaction and performs no device I/O,
leave-return writes, payroll updates or penalty/outbox generation. Identity comes
only from a unique confirmed device reference at the current registered address
and an existing VERA username. Machine names remain review metadata. Exact unique
timestamp sequences propose mappings but cannot supply a device profile ID or
confirm a mapping. Normal VERA shifts still do not require an exit scan.

Workday assignment uses VERA schedules/effective assignments, with the next calendar
day fetched for overnight evidence. The preview preserves full local timestamps;
overlapping shift windows, missing shifts, changed evidence, unknown status/type
and missing identities are review blockers. Raw timestamps and the shared base
attendance/break result are compared separately, so five-minute grouping cannot
hide a missing repeat scan. This is not a full payroll/approved-leave/Auto Check
cutover validation: payable minutes and vendor status semantics remain unverified,
and attendance_cutover_ready remains false. Never stop the whole TimeSoft worker:
it also handles historical invoice imports and delivery of committed penalty events.

The production deployment workflow installs an independent archive-only systemd
timer, 60 seconds after the prior service finishes. A nonblocking local file lock
also excludes the hourly GitHub fallback. Device fetches finish before database
transactions. PostgreSQL archival now uses two SQL statements per bounded batch
of 250 records plus two per-day bookkeeping statements; the evidence digest check
and transaction rollback remain mandatory. Regression tests use synthetic records,
including first insert/replay, a conflict in the second batch, a pool of one,
read-only enforcement, Unicode names, repeats, date rollover and ambiguous shifts.

## 27-09-2026: FaceGate scheduler installer rejects the deployment account

Deploy VPS Production #564, run 36265105847, confirms DEPLOY SUCCESS for
21fcc40 and passes active-release/schema verification, then fails in the newly
added FaceGate timer step with exit code 1 and no diagnostic. The API remains
active. The installer begins with an unconditional `id -u = 0` test, incompatible
with the documented production setup: the deployment and API share an
unprivileged account. This root-only assumption was introduced in PR #305.
The run does not establish that the timer was installed or that the subsequent
public frontend/health gates passed; those steps were skipped.

Replace privileged system-unit installation with a current-account crontab entry.
Check API ownership, worker/Python files, writable status/lock files and an active
cron daemon first. Preserve unrelated crontab entries, serialize installers,
reject concurrent changes detected before replacement, and verify the installed
entry. Repeated installation does not duplicate or rewrite an unchanged entry.
Keep an existing active FaceGate timer if one was separately installed. No sudo,
permission grants, service restart or source cutover is performed. The archive
worker's existing nonblocking lock still excludes concurrent cron/hourly runs.
The schedule checks every minute; a still-running archive is skipped.

Failures now report a bounded stage/reason without dumping existing crontabs,
credentials or API environment. Auth, commit/business health and frontend checks
still run after a successful application deployment even if scheduler setup fails.
The scheduler failure remains a failed workflow, not a claimed successful setup.
Regression tests execute the actual installer with simulated non-root commands,
existing/empty/denied/concurrently changed crontabs, an inactive daemon and repeated
installation. Live cron availability and execution still require deployment.

## 27-09-2026: chọn ảnh Capture Log cho hồ sơ FACE ID của nhân viên

Ảnh người dùng xác nhận 0/66 ánh xạ có hiệu lực tại IP hiện tại. Bản PDF ngày
26-09 hiển thị 132 sự kiện chưa có ánh xạ duy nhất và thiếu log TimeSoft cho
bộ đối chiếu. Đây không phải chứng cứ ánh xạ bị xóa hay hai nguồn đã khớp.

Theo yêu cầu mới, thêm Chọn ảnh cho nhân viên sau khi xem ảnh Capture Log.
Danh mục chỉ đọc tên hệ thống và họ tên, tải khi mở công cụ, yêu cầu đồng thời
quyền xem lịch sử thiết bị và quản lý FACE ID. Người vận hành chọn rõ nhân viên,
xem ảnh FACE ID hiện có, cắt ảnh 3:4, xác nhận và bấm Lưu. Dùng đúng blob vừa
xem; không quét lại toàn bộ Capture Log khi lưu. Nhân viên đã xóa không được
chọn; lưu vẫn kiểm tra quyền, định dạng, kích thước và tỷ lệ qua API FACE ID.

Lưu có điều kiện theo SHA ảnh lúc xem (hoặc If-None-Match khi chưa có ảnh), dùng
khóa nhân viên hiện hữu; hai người thay cùng ảnh chỉ một người thành công.
Retry đúng nội dung đã lưu không ghi lại. Xung đột giữ ảnh đang chọn và yêu cầu
đọc lại ảnh hiện tại rồi xác nhận; lỗi mạng không xóa ảnh nháp. Dialog giữ vị trí
trang, ảnh chỉ tải khi xem, phần cắt ảnh được tải theo yêu cầu. Không đưa ảnh vào
Excel danh sách nhân viên, không đổi ảnh CCCD/đại diện hoặc tự ánh xạ nhân viên.

Ảnh này lưu trong mục ẢNH FACE ID riêng của VERA. Adapter hiện có chỉ đọc hồ sơ,
log và ảnh; chưa có luồng đăng ký ảnh mới lên thiết bị được xác minh. Không gửi
lệnh ghi không rõ giao thức tới FaceGate, không đổi nguồn công hoặc ngừng TimeSoft.
Kiểm thử HTTP/PostgreSQL, quyền, Unicode, retry và lưu đồng thời cùng kiểm thử
UI được bổ sung. Chưa xác nhận thao tác lưu ảnh này trên VPS production.

## 27-09-2026: lưu ảnh FACE ID và nhân viên theo tỷ lệ gốc

Ảnh chụp mới của người dùng cho thấy lưu Capture Log bị chặn bởi ngưỡng tối thiểu
160 × 160 px. Yêu cầu mới thay thế tỷ lệ 3:4 bắt buộc: ảnh nhân viên và FACE ID
được lưu theo tỷ lệ gốc, kể cả ảnh nhỏ. Giữ kiểm tra file ảnh, dung lượng và giới
hạn giải mã tối đa; CCCD vẫn giữ kiểm tra riêng. Camera giữ toàn khung hình,
chỉnh ảnh và tải hàng loạt không ép 3:4 hoặc phóng lớn ảnh nhỏ. Capture Log có thể
lưu ảnh gốc sau khi chọn và xác nhận nhân viên, không bắt buộc mở trình cắt ảnh.
Cơ chế kiểm tra quyền và chống ghi đè ảnh khi nhiều người cùng thao tác giữ nguyên.

Excel mặc định vẫn chỉ có dữ liệu. Thêm lựa chọn Admin xuất kèm ảnh nhân viên
3 × 4 cm, giữ toàn ảnh trong khung trắng khi tỷ lệ gốc khác 3:4. Đọc ảnh theo
nhân viên đã lọc bằng truy vấn theo lô, tối đa 200 nhân viên/40 MB; xử lý ảnh sau
khi trả kết nối. Không đọc ảnh CCCD/FACE ID cho bản xuất, không sửa ảnh gốc và
không đăng ký ảnh lên FaceGate. Bổ sung kiểm thử HTTP/PostgreSQL, UI lưu ảnh gốc,
ảnh nhỏ/ngang/vuông, quyền và kích thước khung Excel qua middleware định dạng.
Chưa xác nhận bản sửa trên VPS; không thay nguồn tính công hoặc dừng TimeSoft.

## 27-09-2026: trang Nhân viên lỗi khi thay đổi bộ lọc

Sau deploy main `19517aeb2bf2827c087642b48202e914c5535717`, đã đăng nhập
production bằng biểu mẫu bảo mật và tái hiện lỗi chỉ bằng thao tác tìm tên không
có kết quả. Console ghi `NotFoundError: Failed to execute 'removeChild' on
'Node': The node to be removed is not a child of this node.` Trang chuyển sang
PageErrorBoundary giống ảnh người dùng. Trước lỗi, thống kê còn hiển thị 0 nhân
viên dù bảng có dữ liệu. Thử mở lại khôi phục được trang; không sửa hồ sơ thật.

Hai bộ bổ sung giao diện `employeeMissingProfileFix` và
`employeeProfileCompletionAndIssuerFix` ghi đè `textContent` của thống kê và
nhãn hồ sơ do React quản lý. Khi bộ lọc đổi làm nhánh cảnh báo biến mất, React
xóa text node đã bị mã ngoài thay thế và phát sinh lỗi. Đây là lỗi giao diện đã
tái hiện, không phải kết luận từ trạng thái CI/deploy hoặc lỗi đọc ảnh đính kèm.

Chuyển nhãn thiếu hồ sơ, tiêu đề dòng, màu dòng và thống kê về cùng phép tính
trong EmployeePage. Tôn trọng miễn yêu cầu đủ hồ sơ và bỏ Quận/Huyện khỏi danh
sách bắt buộc như hành vi hiển thị trước đây. Gỡ bộ sửa DOM/poll API hồ sơ cũ;
giữ phần danh mục nơi cấp CCCD nhưng bỏ việc sửa nhãn và thống kê trong đó.
Không thay xác thực, API lưu hồ sơ, dữ liệu hoặc nguồn chấm công.

Kiểm thử tích hợp tải main thực tế cùng các bộ bổ sung giao diện, thay riêng
transport bằng dữ liệu giả. Kiểm tra mở trực tiếp/từ menu, dữ liệu đến chậm,
lọc có/không có kết quả, xóa lọc, hồ sơ miễn yêu cầu, hồ sơ đủ không có quận,
làm mới và chuyển trang. Bổ sung vào CI. Xác minh production sau deploy vẫn
phải kiểm tra thao tác lọc đã gây lỗi, phiên bản frontend và hai health gate.


## 29-09-2026: Live Tour metadata receipt archive dominates mutation writes

Read-only diagnostic run `36128412508`, rerun job `109323304150`, verified
production release `7fe9b8123da6744a8b03adc9fe7a869bc6659b16`. Maintenance status
run `36542715447` reported active/resource_ready. Metadata JSON text was
10,879,007 bytes, including 10,867,707 bytes of idempotency receipts. Three
slow-log samples after this deploy were: multi_booking 1,178.62 ms total /
973.85 ms write; multi_booking 1,541.41 / 1,323.16; finish_room 1,302.53 /
1,086.13. The write phase therefore occupied about 83–86% of these samples.
These are thresholded slow logs (>=500 ms or error), not unbiased latency
percentiles, and exclude authentication and final HTTP serialization. No start
sample after this exact deployment was observed. No speedup is established yet.

The proposed fix moves durable replay receipts from the metadata JSON to the
previously reserved `vera_live_tour_mutation` table, one row per idempotency key.
Ordinary mutations update only changed receipts in the existing caller-owned
transaction, retaining resource locks, publication ordering, authorization and
financial retry semantics. Full reads/backups reconstruct the archive; scoped
reads use the primary key. No financial receipts expire. A database guard rejects
old inline writers after cutover instead of allowing silent duplicate execution.

Migration is explicit, not part of deployment: `optimize_receipts` stops writers,
verifies a private backup and both session fences, compares complete canonical
state before/after, restarts the exact release and verifies receipt-format health.
`restore_receipts` exports the latest rows back, including writes since cutover.
Full resource rollback also exports receipts first. Failure recovery uses current
data, never a stale financial snapshot. See `docs/live-tour-receipt-rows.md`.
This entry describes code and isolated validation; production optimization has
not been activated by this change.

## 29-09-2026 — Explicit retirement of the TimeSoft live dependency

Confirmed operator instruction: use direct FaceGate evidence and stop using
TimeSoft. Previously reported `already_applied=true` for the reviewed 27-09-2026
Yến Linh exception remains authoritative; this change does not reapply it.
The two confirmed test events 79329/79330 remain excluded from calculated
attendance while their raw archived evidence is retained.

The independent runtime adds a shared, hot-readable source policy at
`/opt/vera-spa/attendance-source.json`. Before its effective Vietnam date,
existing PostgreSQL TimeSoft snapshots remain readable history. From that date,
attendance reads mapped FaceGate archive evidence through the same VERA shift
resolver; Live Tour uses a separate FaceGate cache and the existing coalesced
projection queue. The archive cron publishes that cache only after a complete,
fresh device sync. Neither source imports vendor shift assignments.

TimeSoft login, live refresh, invoice backfill and worker acquisition are disabled
in the selected mode. The existing worker still runs committed notification
retries and existing Auto Check rules; its FaceGate input contains one verified
arrival per employee/day. Incomplete evidence suppresses automated conclusions.
The separate legacy customer search rejects vendor access after retirement;
VERA's existing customer directory and Live Tour TIP payroll remain independent.

This is an explicit operator waiver of cross-vendor comparison blockers, not a
claim that missing photos, identity ambiguity, raw status documentation or
historical discrepancies have been resolved. Missing/unfinished attendance is
marked pending per employee, with null payable salary instead of zero, and is
rechecked server-side before official attendance-based payroll saving/export or
email. Existing schedule-based payroll remains an explicit independent option.

Production activation is opt-in via `retire_timesoft` in Deploy VPS Production.
It verifies the exact running release and both health endpoints, locks the archive
worker, refreshes raw evidence, checks the existing attendance worker lock, then
publishes and selects the source. It does not change photos/mappings, reviewed
exceptions, payroll, penalty history, credentials, or system services. Repeated
activation preserves the original effective date. Default CLI invocation is
read-only and reports source, freshness and unresolved counts without identities.

Production verification is still pending at implementation time. SSH from the
assistant runtime returned `Network is unreachable`; a build, test or merge alone
must not be reported as a successful live cutover. Do not roll an active FaceGate
source back to code that predates this runtime. Keep the configuration and raw
archive with operational backups. A source rollback is a separate explicit
operator action because it would resume TimeSoft network access.


## 29-09-2026: Website booking inbox (not deployed)

- Reviewed WordPress CF7 forms 1271 (booking) and 606 (contact). Contact has only name, phone and message; missing appointment fields must not be guessed.
- Added signed server-to-server intake, a durable WordPress outbox, UUID replay protection, and separate indexed PostgreSQL inbox rows. No Live Tour state/receipt writes, staff assignment, payment or network calls while holding a business transaction.
- Admin/Quản lý/Lễ tân see a Live Tour popup and the Booking online page. API independently enforces the audience, SQL pagination and optimistic row revisions.
- Activation still requires both server secrets, plugin installation and normal backend/frontend deploy. No live customer form has been submitted in this work. See [runbook](online-booking.md).


## 29-09-2026 — Live Tour leave and employee controls (code review)

- The current missing-check-in feed excluded every registered leave reason, including late arrival. Registered late arrivals now alert at 15:00 for Ca 1 and 17:00 for Ca 2; checked-in staff remain excluded and the fresh attendance cache safeguard remains in place.
- Early-leave return markers now use the existing return queue, ahead of unexcused-leave markers within the return cohort. Existing service release and manual shift safeguards are retained.
- Weekend reason availability depended on catalog allowed_days, and registration timing bypasses could bypass that restriction. A reason-name invariant now validates the target leave date on create/edit, including admin paths; weekday reason menus also exclude these reasons.
- The supplied screenshot shows a weekend reason created on Saturday 26-09-2026 for Tuesday 29-09-2026. No production record or audit log was read: the specific submission path is not confirmed, and no historical record has been rewritten.
- The user explicitly extended quick shift assignment to quanly and letan. FaceID device controls and capture endpoints are limited to admin/quanly, with the gallery rendering the five latest complete images. Quota checks use the current Vietnam calendar month independently of the list filter.
- This is a source change, not evidence of deployment or production verification.


## 30-09-2026 — Optional deferral of attendance freshness for unrelated deployment

Read-only GitHub logs for Deploy VPS Production #619 (36642002476), release
5f3813f6, show failure in the source inspect gate: FaceGate remained selected,
TimeSoft network disabled, but cache age was 19633 seconds at 05:52 +07.
The schedule installer verified its entry. Exact-release and both health checks
passed later; this does not prove device connectivity or attendance readiness.

The operator explicitly asks to temporarily defer FaceGate checks and continue
all outstanding work outside attendance. Add a dispatch option defaulting false.
When selected without a new source activation, deployment checks only the existing
active FaceGate policy, emits a freshness-deferral warning and keeps all commit,
schema, auth/business-health and frontend gates. Missing/malformed/future policy
fails closed. If source activation is selected, full verification remains required.
This performs no device I/O, database writes, source switch, cache publication or
payroll/penalty changes. Freshness/readiness are explicitly unverified.
Production use of this new dispatch option is not yet verified.

## 30-09-2026: xếp cuối bảng tua một lần tại mốc 03:00

Yêu cầu mới thay thế cơ chế chờ check-in/quay lại ở các mục 27–28/09:
chỉ xử lý chung một lần/ngày tại mốc 03:00 giờ Việt Nam, dựa trên lịch nghỉ
ngày liền trước. Áp dụng đúng chín lý do: Về sớm CÓ phép, Về sớm KHÔNG phép,
Về sớm CUỐI TUẦN CÓ phép, Về sớm CUỐI TUẦN KHÔNG phép, Về sớm phát sinh,
Leader về sớm về sớm theo chính sách, Về sớm bệnh có giấy khám hoặc được quản lý duyệt
(bổ sung lúc 13:06–13:07 ngày 30/09), Nghỉ KHÔNG phép, Nghỉ CUỐI TUẦN KHÔNG phép. Không đưa đi trễ hoặc các lý do
khác vào danh sách này bằng so khớp tiền tố.

Scheduler hiện hữu thức tại mốc 03:00; worker lưu dấu ngày đã chạy cùng giao
dịch/khóa bảng tua, kể cả không có nhân viên đủ điều kiện. Nguồn lịch nghỉ
ngày trước được đọc một lần bằng connection đang giữ khóa; không cần dấu đã
quan sát hôm trước, không đợi check-in, không tích lũy nhiều ngày vắng mặt.
Lượt xử lý có thể trễ nếu dịch vụ dừng hoặc hàng đợi bị nghẽn; lần phục hồi
chỉ xử lý ngày liền trước một lần, bỏ qua lượt thường đã bắt đầu trong ngày.
Không có cam kết thời gian thực cứng đến từng giây khi VPS không hoạt động.

Bản mới khởi tạo mốc theo dõi khi nâng cấp và chờ 03:00 kế tiếp, không đảo
bảng giữa ngày deploy. Nhóm về sớm trước nhóm nghỉ không phép, giữ thứ tự
Người Thứ N. Sau lượt sắp xếp, vận hành tua thường/YC, đổi nhân viên, hủy
Thực hiện và quyền Admin giữ nguyên; check-in, refresh, chỉnh lịch nghỉ sau
mốc đã xử lý không xếp lại. Dấu xếp cuối cũ hết hiệu lực ở lượt 03:00 kế tiếp.
Không sửa giờ dịch vụ, tiền phạt, lương hay hóa đơn. Chưa xác minh production;
CI kiểm tra biên 02:59:59/03:00, replay PostgreSQL và vận hành sau sắp xếp.

Bổ sung lúc 13:09: menu Nội quy có mục Xếp cuối bảng tua · 03:00, cho Admin
kích hoạt/tắt tất cả hoặc từng lý do. Mặc định bật đủ chín lý do được xác nhận.
API kiểm tra cả quyền sửa Nội quy và role Admin, khóa cập nhật cùng kiểm tra
revision để chặn ghi đè cấu hình cũ. Mỗi thao tác lưu ngay, ghi updated_by;
worker đọc cấu hình tại lượt chạy, lưu revision đã áp dụng trong dấu ngày.
Thay cấu hình sau lượt đã xử lý không kích hoạt lại ngày đó, không sửa mức phạt.

## 30-09-2026: tự ghi nghỉ không phép sau mốc Ca 1 / Ca 2

Operator requests current-day automatic absence after (strictly greater than)
15:00 Ca 1 / 17:00 Ca 2, weekday/weekend catalog penalties and employee notices.
The complete FaceGate archive refresh invokes this rule with a caller-owned
transaction, separate from cache publication. Raw evidence must be nonempty,
complete, no more than five minutes old and synchronized after the cutoff;
unresolved identities suppress the batch. Only active scheduled, mapped,
participating employees without scans qualify. Existing non-late leave records
are preserved; late registration still requires attendance by the cutoff.

Admin can disable the rule or either shift in Nội quy. Default is enabled per
operator instruction. It processes today's date only, with normal restart retry;
no historical backfill. Official reason/penalty is selected for the actual VN
weekday (Saturday/Sunday use the weekend reason), using existing progressive
penalty rules. No catalog fallback or new hardcoded amount. Existing leave and
Auto Check unique events prevent repeat penalties. Later arrival does not silently
erase a committed absence; management must review/adjust it.

Leave/event/notification outbox are atomic. The new notification family has native
employee + reception + management + admin audiences and in_app/popup/push channels.
Disabling notifications does not disable the business rule. Generic penalty
notification is handed off to this outbox once, avoiding a duplicate notification
or bypass of its settings. No network I/O or nested pool connection under locks.
Deployment and actual production behavior are not yet verified.

## 30-09-2026: reuse of a retired employee name (New)

Operator read-only SQL shows New is soft-deleted/Đã nghỉ việc; inspected text
identity columns only link employees, vera_v2_active_device and vera_v2_user_profile.
This is not proof that arbitrary JSON history has no links. Creation may retire
an unused former directory identity under an opaque retired UUID name, retaining
its data and old auth UUID/device ownership. Old local sessions are revoked,
profile disabled, account permission overrides moved, and the new employee gets
a separate auth identity UUID; deterministic username UUID reuse is forbidden.
The entire retirement and creation share the existing directory transaction.

Active/temporarily absent accounts remain reserved, including linked rename
aliases. Unknown business text references and identity-bearing application JSON
block reuse pending explicit separation; this change does not claim unrestricted
reuse of all historical names. No automatic financial-history migration or raw
FaceGate evidence rewriting is performed. A failed creation rolls retirement
back. Deployment/production creation has not been verified.

## 30-09-2026: two-hour absence grace and replacement

Operator screenshots show Linh Đan with both unpermitted late and full-day
absence penalties. The absence cutoff now waits two hours after the existing
15:00/17:00 required arrival anchors (17:00/19:00 VN). Immediately before writes,
read complete fresh FaceGate evidence again under the employee leave lock.
Replace only same-employee/day unpermitted rows; archive complete originals and
supersede their automatic events transactionally with the new absence. Failure
or duplicate rolls removal back. Preserve permitted registrations. Permitted
late requires a unique official half-day unpermitted catalog reason for the
actual weekday/weekend; missing/ambiguous catalog means review, never full-day
fallback or an invented fine. No historical repair or production writes performed.

Operator clarified half-day absence equivalents: Về sớm KHÔNG phép on weekdays,
Về sớm CUỐI TUẦN KHÔNG phép on Saturday/Sunday. Select those exact existing
catalog rules and their configured penalty/day values; do not invent a new rule.

## 30-09-2026: optional employee request from public booking (code change)

The operator requests an optional **Yêu cầu nhân viên** field above **Lời nhắn**
on the public booking form, listing only employees currently marked Đi làm in
the Live Tour roster. Booking service and phone are also optional; contact-form
phone remains required. For a booking dated today in Asia/Ho_Chi_Minh, the
selected employee's Live Tour Lịch hẹn value receives `YC HH:MM`. The backend
rechecks the roster under the existing Live Tour lock before writing. Requests
for later dates remain in the booking inbox and do not modify the board.
Website-added YC suffixes are tracked separately and removed at the next daily
rollover, preserving the other appointment text.

This intentionally adds the narrowly scoped Live Tour write that the original
booking-inbox implementation did not perform. It does not assign a worker,
service, room or invoice. The request is recorded in the inbox independently;
Live Tour marking is a follow-up operation after that commit. These are source
changes only: production API/plugin deployment, secret configuration and
readback are still pending. No customer booking was submitted and no production
Live Tour row was changed during implementation.
