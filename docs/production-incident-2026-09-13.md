# Sự cố đăng nhập và tải dữ liệu ngày 13/09/2026

## 26-09-2026: sổ Thu Chi không giới hạn ngầm ngày và theo dữ liệu mới nhất

Theo yêu cầu tiếp theo, mặc định Tất cả của cả Manual và Auto đọc toàn bộ
dòng hiện có, kể cả trước 05-09-2025, không cắt theo kỳ TIP hoặc ngày cố định.
API và Excel nhận live_ledger, được truyền qua wrapper V2 thật. Khoảng ngày
hiển thị lấy ngày đầu có dữ liệu đến ngày mới nhất (ít nhất là hôm nay tại
Việt Nam); bộ lọc Tùy chỉnh và Ngày do người dùng chọn vẫn có hiệu lực.
API cũ và các thẻ tổng/TIP giữ kỳ báo cáo đã chọn; không đổi số tiền đã lưu.

Manual, Auto và Manual/TIP tự động dùng chung kiểm tra revision mỗi 5 giây
khi trang hiện, tải lại khi dữ liệu đổi hoặc sang ngày mới ở Việt Nam. Giữ
chặn cập nhật khi biểu mẫu đang sửa/lưu và giữ bộ lọc đang chọn. Nguồn cũ
vẫn tương thích, tránh thêm bộ hẹn giờ 30 giây trùng với revision poller.

Kiểm thử UI bao gồm dữ liệu trước mốc cũ, sau kỳ TIP, thêm/sửa/xóa, ngày mới,
giữ bộ lọc và tham số xuất. PostgreSQL/HTTP kiểm tra wrapper, Manual/Auto
tách nguồn, Excel, bộ lọc chủ động, quyền truy cập và revision qua nửa đêm.
Các dòng kiểm thử là giả lập; không chỉnh sửa hoặc xóa dữ liệu thực trên VPS.

## 26-09-2026: sổ Thu Chi Manual vẫn bị cắt theo kỳ báo cáo/TIP

Kết quả chạy trên VPS do người dùng cung cấp lúc 22:46 xác nhận ngày 24-09:
Manual có 3 dòng, Thu 49.250.000đ, Chi 54.202.000đ; Auto Thu 49.250.000đ,
Chi Nhập mua 121.000đ, dịch vụ 22.000.000đ, TIP 27.250.000đ. Có 73 hóa đơn,
tổng hóa đơn và báo cáo chênh 0. Chưa biết nội dung từng dòng chi Manual,
không kết luận hoặc xóa khoản 54.081.000đ chênh nguồn khi chưa đối chiếu.

Ảnh 22:55: sổ chọn Tất cả nhưng hiển thị khoảng 05-09-2025–21-09-2026,
bộ lọc Ngày là 24-09-2026, kết quả rỗng. Lỗi mã: capability v2 đã tách
nguồn Manual/Auto nhưng vẫn gửi report_end của phần tổng/TIP cho sổ Manual.
API cắt khoảng trước ngày cần xem, sau đó frontend lọc ngày 24 thành rỗng.

Với nguồn độc lập v2, chỉ sổ Auto theo ngày chốt báo cáo. Sổ Manual và Excel
không gửi report_end, dùng bộ lọc riêng; vẫn giữ canonical để lấy sổ server
trong khoảng hỗ trợ 05-09-2025 đến hôm nay. API cũ giữ hành vi tương thích.
Sửa một đầu khoảng Từ/Đến sẽ giữ đầu còn lại đang hiển thị khi chuyển từ
preset sang Tùy chỉnh. Không đổi kỳ TIP đã lưu, quyền ghi, hoặc dòng tiền.

Hồi quy UI tái hiện thất bại trên mã cũ, kiểm tra 3 dòng sau ngày chốt 21,
tổng theo bộ lọc, tham số Excel và chỉnh khoảng ngày mà không phát lệnh ghi.
Hồi quy PostgreSQL/HTTP kiểm tra bảng và nội dung Excel cùng ngày 24, ngày
chốt vẫn 21 và quyền 403. Số tiền từng dòng trong fixture là giả lập, không
được coi là nội dung 3 dòng thật trên VPS. Bản sửa cần CI và triển khai.

## 26-09-2026: nhãn hóa đơn đã thanh toán đếm trang thay vì tổng bộ lọc

Ảnh lúc 22:18–22:19 ICT chọn cùng ngày 26-09: Báo cáo ghi 64 hóa đơn,
Live Tour ghi 50. Mã xác nhận endpoint collections mặc định 50 dòng/trang,
trả total trước phân trang, nhưng LiveTourInvoicesPanel hiển thị
visibleInvoices.length. Dùng total của chính phản hồi/bộ lọc hiện tại cho
nhãn tổng; ghi riêng số đang hiển thị và trang. Giữ phân trang 50 để không
tải lại toàn bộ lịch sử. Không dùng số 64 cố định, không thay đổi hóa đơn.
Không hiện tổng/dữ liệu trang cũ khi đang đổi trang hoặc đổi bộ lọc.

Live Tour bên trong cũng dùng bộ lọc và nhãn ngày effective_at hoặc
business_date theo Ngày giờ hóa đơn như trang Báo cáo độc lập và SQL Auto;
không dùng ngày tạo thay ngày hóa đơn ở các bảng này. Hồi quy API và UI
kiểm tra 64 hóa đơn qua 2 trang (50 + 14), hóa đơn nhiều dòng nhân viên,
ngày tạo khác ngày hóa đơn, đổi bộ lọc và không có kết quả.

Người dùng nêu sổ nhập tới 24-09-2026, ngày đó Thu 49.250.000đ và Chi
121.000đ. Hai ảnh chỉ có số liệu ngày 26, chưa chứng minh số thật ngày 24.
Thêm vera_revenue_day_check.py cho người vận hành chạy cục bộ trên VPS:
đọc một ngày, trả tổng Manual, tổng Auto, số hóa đơn, tổng tiền hóa đơn
và chênh với báo cáo. Một kết nối REPEATABLE READ/read-only có thời hạn,
không import API hoặc gửi thông báo, không ghi dữ liệu; không xuất tên,
số hóa đơn hay bí mật kết nối. Không chạy tổng tiền trong workflow logs.
Kiểm thử PostgreSQL dùng tiền mẫu đúng mốc đối chiếu, mốc UTC/VN và dòng
đã xóa; không coi mẫu là xác minh dữ liệu production. Deploy c61380e đã
thành công trước báo lỗi này; bản sửa nhãn mới vẫn cần CI và deploy.

## 26-09-2026: Auto độc lập, ngày hóa đơn và Nhập mua làm nguồn chính

Yêu cầu lúc 21:11 thay thế quy tắc chung nguồn trước đây: Auto chỉ đọc thu từ
Live Tour (dịch vụ + TIP) và chi từ Nhập mua, không trộn lịch sử Manual. Manual
đọc riêng sổ nhập tay. Khoảng báo cáo vẫn từ 05-09-2025 đến ngày chốt; TIP có
khoảng riêng. Các kỳ lưu theo nguồn, lưu Auto không ghi đè kỳ Manual. Không
sao chép hoặc thay đổi giao dịch gốc khi chuyển chế độ. Capability version 2
phân biệt giao diện nguồn độc lập với API cũ.

Ngày hóa đơn dùng đúng cột đang hiển thị: effective_at, thiếu thì business_date,
theo lịch VN. Áp dụng cho lọc báo cáo, TIP, tổng Auto, danh sách và xuất Excel
báo cáo hóa đơn. Ngày mua vẫn theo purchase_date của Nhập mua.

Ảnh 14:09 UTC cho thấy ngày bắt đầu 25-09 đỏ nhưng TIP vẫn 400.380.000đ. Mã
VeraDateInput giữ draft khi ngoài max=ngày kết thúc cũ và không emit; đổi ngày
kết thúc có thể gửi ngày bắt đầu cũ. Bỏ min/max chéo giữa hai ô TIP, kiểm tra
khoảng ở cấp form, báo trạng thái draft, hủy phản hồi cũ và che tổng chưa khớp
kỳ. Nhập bắt đầu trước kết thúc được hỗ trợ; nhập dở/sai không gửi ngày cũ hoặc
lưu kỳ cũ. Kiểm thử một ngày 25-09 có TIP giả lập 15.450.000đ theo chứng cứ
người dùng; số này là mốc đối chiếu, không được gán cố định trong mã nghiệp vụ.

Nhập mua và báo cáo mua trong Doanh thu dùng cùng list_entries PostgreSQL,
người đặt lấy note và người nhập lấy entered_by. Endpoint đọc báo cáo mua
riêng chỉ yêu cầu quyền Doanh thu; bộ lọc mua không bị cắt bởi kỳ TIP, không
quay về nguồn Google khi dữ liệu trống. Tổng và số dòng theo toàn bộ kết quả
lọc, trước phân trang. Giữ poll revision 5 giây khi trang hiện và không đang
lưu/nhập; sửa/xóa Nhập mua làm thay đổi revision. Kiểm thử so sánh API gốc và
báo cáo qua thêm/sửa/xóa, hơn 100 dòng, quyền và ngày ngoài kỳ TIP.

Deploy #36247109031 đã thành công ở 53e6281 trước yêu cầu này. Các kiểm thử và
thay đổi ở đây cần CI và deploy mới; chưa chứng minh tổng tiền thật trên VPS.


## 26-09-2026: TIP giữa Báo cáo và Doanh thu lọc theo hai loại ngày

Người dùng báo cùng kỳ 16–24-09-2026: Báo cáo 230.310.000đ, Doanh thu
315.720.000đ. Khác với hai ảnh trước (khác năm bắt đầu), đây là yêu cầu đối
chiếu cùng kỳ. Deploy #36246228618 chạy 3536ae5; schema gate xác nhận Live
Tour active, parity ok, revision 6042. Chưa đọc hóa đơn/journal production
để quy toàn bộ chênh 85.410.000đ cho một nhóm giao dịch cụ thể.

Mã có sai khác xác định: ReportPage/filterTourRows và list API ưu tiên
effective_at → booked_at → created_at → business_date, theo ngày lịch VN.
SQL Doanh thu ưu tiên business_date (ngày nghiệp vụ có thể khác ngày lịch),
đồng thời lọc trước theo business_date. Vì vậy giao dịch qua ngày hoặc chỉnh
lùi ngày có thể thuộc hai kỳ khác nhau. SQL nay dùng cùng thứ tự ngày lịch;
bỏ bộ lọc business_date cũ để không loại nhầm giao dịch đã chỉnh ngày. Timestamp
không có offset được hiểu theo giờ VN, không phụ thuộc timezone PostgreSQL.
TIP và phần Thu tự động dùng chung biểu thức này. Lịch sử Manual đến 24-09,
ngày mua hàng, số tiền và ngày gốc hóa đơn không bị ghi lại.

Fallback TIP trình duyệt và ReportPage dùng chung tourRowDate, giữ đọc ngày
legacy dd/mm/yyyy và chuẩn hóa timestamp không múi giờ theo VN. Kiểm thử
PostgreSQL/HTTP và JS tái hiện dữ liệu giả lập có tổng 315.720.000 nhưng chỉ
230.310.000 thuộc kỳ ngày lịch, so với bộ lọc báo cáo thực tế; đồng thời kiểm
tra lưu/mở lại kỳ, Manual/Auto, mốc chuyển nguồn, UTC, ngày chỉnh lùi, deleted
rows và timezone DB khác VN. Không coi ví dụ này là đối chiếu giao dịch thật.
Cần Deploy VPS Production và làm mới cả Báo cáo lẫn Doanh thu để đối chiếu
cùng kỳ, không lọc thêm nhân viên/khách/dịch vụ/số hóa đơn ở trang Báo cáo.

## 26-09-2026: HTTP 500 Doanh thu do lớp đối soát V2 thiếu tham số mới

Người dùng báo HTTP 500 lúc 20:35 sau Deploy VPS Production #36245308189.
Workflow xác nhận đã chạy commit d2ba255 và hai health endpoint thành công;
điều đó không kiểm tra được API đối soát có xác thực. Chưa lấy journal trực
tiếp từ VPS. Đọc chuỗi installer production xác định purchase_reconcile_v2
thay route gốc nhưng không nhận/chuyển tiếp canonical và report_end mới.
Khi gọi hàm gốc trực tiếp, các mặc định Query(False)/Query(None) vẫn là đối
tượng FastAPI, không được phân giải thành bool/None. Nhánh min(end, report_end)
vì thế phát TypeError trước khi đọc database. Đã tái hiện phép gọi này cục bộ.

Lớp V2 nhận và chuyển tiếp cả hai tham số, giữ ngày chốt và nguồn báo cáo.
Mặc định của hai tham số ở các route dùng bool/None Python; FastAPI vẫn phân
giải/kiểm tra kiểu query HTTP. Không thay đổi dữ liệu, phép tính, quyền hoặc
thông báo nghiệp vụ. Fixture PostgreSQL nay cài cả wrapper V2 đúng production,
vô hiệu hóa gửi thông báo chỉ trong test. Hồi quy kiểm tra Manual/Auto, ngày
24-09-2026, client không gửi tham số mới, lỗi nhập ngày/bool và quyền 403.
CI trước đây chỉ cài route gốc nên bỏ sót lỗi lắp ghép; phải kiểm tra route
thực tế sau deploy, không dùng CI hoặc health để khẳng định đã hết lỗi VPS.

## 26-09-2026: báo cáo Manual/Auto chung nguồn và cùng kỳ trong một phản hồi

Ảnh 19:44 có TIP ở ô nhập 230.310.000đ nhưng thẻ TIP 266.720.000đ. Đây là
bằng chứng giao diện đang ghép hai kết quả khác kỳ. Mã dùng một request summary
đọc kỳ đã lưu và request tip-summary đọc kỳ đang chọn; polling có thể ghi đè
thẻ TIP trước khi lượt đọc TIP hoàn tất. Workflow VPS #36242291544 thành công
ở commit 169ea00 (PR #293), nhưng ảnh vẫn có nhãn cũ; chưa xác nhận bundle
trình duyệt đang dùng nên không kết luận chỉ do deployment hay cache.

Theo yêu cầu cùng kỳ phải bằng nhau, Manual và Auto dùng chung nguồn báo cáo:
lịch sử Manual từ 05-09-2025 đến 24-09-2026, thanh toán + TIP và Nhập mua từ
25-09-2026. Đầu kỳ TIP chỉ giới hạn TIP; Đến ngày chốt cả Thu, Chi và số dư.
Không sao chép/sửa/xóa giao dịch để ép khớp. Sổ nhập tay, kể cả các dòng sau
mốc chuyển đổi, vẫn giữ riêng và mở bằng Sổ nhập tay trong Manual; các dòng
sau mốc không cộng lại vào báo cáo chung. Bảng chung và Excel dùng cùng nguồn,
cùng ngày chốt; hàng tự tổng hợp chỉ đọc, lịch sử Manual vẫn giữ quyền sửa cũ.

API period-report trả toàn bộ tổng, TIP, số dư và ngày áp dụng trong một phản
hồi, sử dụng một kết nối REPEATABLE READ cho các truy vấn liên quan. Không
nhận số TIP do client gửi. Chế độ nhập vẫn kiểm tra quyền/khóa cũ. Report tổng
không còn jsonb_agg/toàn bộ entries lịch sử. report-period lưu chung ngày chọn,
đồng bộ metadata kỳ của client cũ; không sửa sổ tài chính. Frontend dùng một
đối tượng kết quả cho cả ô TIP và thẻ TIP, hủy/bỏ phản hồi cũ, giữ kỳ khi đổi
chế độ và polling. Capability version giữ tương thích VPS cũ/hybrid riêng.

Kiểm thử PostgreSQL so sánh cả hai chế độ trước/sau mốc chuyển đổi, tổng bảng
và Excel, dữ liệu Manual sau mốc vẫn còn, lưu/đổi chế độ, kiểm tra ngày/quyền và
hóa đơn bị sửa đồng thời giữa lượt đọc tổng và TIP. UI kiểm tra một request
cho kết quả chung, ngày đang chọn, phản hồi trễ, lưu và đổi chế độ. CI phải đạt
trước merge. Chưa đối chiếu giao dịch thực tế production; cần Deploy VPS
Production và tải lại bundle mới. Không xem CI là bằng chứng tổng tiền thật.

## 26-09-2026: ô Đến ngày điều khiển toàn bộ tổng Auto

Người dùng làm rõ lúc 19:13: chính ô Đến ngày trong khung TIP phải chốt cả
Tổng thu/Tổng chi, không yêu cầu một bộ chọn báo cáo riêng. Yêu cầu này thay
thế thiết kế hai ngày độc lập ở PR #292. Bỏ form Chọn ngày báo cáo; Auto gửi
khoảng 05-09-2025 đến tipEnd khi người dùng nhập/chọn ngày hợp lệ. Báo cáo tới
ngày dùng end_date trả về từ API. Ngày bắt đầu kỳ TIP chỉ ảnh hưởng khoản TIP.
Giữ ngày đã chọn qua refresh, polling và lưu TIP; nút Dùng ngày này đưa cả
báo cáo và TIP về ngày kinh doanh hiện tại. Khi mở trang, kỳ TIP đã lưu cũng
được dùng để chốt tổng Auto. Manual giữ cách tính cũ. Nhập ngày chưa đủ/sai
không phát request tính mới hoặc lưu nhầm ngày cũ; xóa ngày không tải lại tổng
đến hôm nay. Không ghi/sao chép giao dịch hoặc thay đổi mốc chuyển nguồn.

Kiểm thử tương tác gồm chọn trực tiếp 24-09, đổi ngày bắt đầu TIP, refresh,
lưu, quay về ngày hiện tại, mở kỳ đã lưu và ngày không hợp lệ. PostgreSQL đã
có kiểm thử summary với khoảng tùy chọn đến 24-09 đối chiếu Manual. CI vẫn
phải đạt trước khi merge; cần Deploy VPS Production để áp dụng giao diện.

## 26-09-2026: chọn ngày chốt cho tổng Doanh thu Auto

Ảnh 18:49 cho thấy người dùng chỉnh Đến ngày trong kỳ TIP thành 24-09 nhưng
Báo cáo tới ngày vẫn 26-09. Xác nhận summaryRange ở frontend cố định là all;
API summary đã nhận start/end nhưng chưa có điều khiển nối tới tham số này.
Bổ sung form Chọn ngày báo cáo / Xem báo cáo ngay trong thẻ Báo cáo tới ngày
cho Auto, lọc từ 05-09-2025 đến ngày chọn (bao gồm cả ngày cuối). Nút Đến hôm
nay trở lại báo cáo cập nhật theo ngày hiện tại. Kỳ TIP độc lập và có nhãn rõ.
Ngày báo cáo hiển thị dùng end_date thực tế từ API; current_date vẫn là ngày
kinh doanh để không đổi quy ước chọn TIP. Bộ lọc được giữ khi refresh/polling;
không sửa dữ liệu thu chi, chế độ dùng chung hoặc kỳ TIP đã lưu. Lưu TIP tính
lại Còn lại từ tổng đang xem, không lấy số dư toàn thời gian trong phản hồi.

Kiểm thử tương tác gồm ngày TIP không đổi tổng, ngày báo cáo gửi đúng khoảng,
trả về hôm nay, giữ bộ lọc khi cập nhật và lưu TIP không ghi đè số dư đang lọc.
PostgreSQL đối chiếu Auto và Manual cùng kỳ đến 24-09, loại giao dịch ngày 25
khỏi tổng và xác nhận đọc không sửa sổ. Cần Deploy VPS Production sau CI;
chưa đối chiếu từng giao dịch/tổng tiền của cơ sở dữ liệu production.

## 26-09-2026: Lương hành chánh lấy thưởng combo và loại tài khoản không tính lương

Ảnh người dùng cho thấy lượt bán combo theo nhân viên ở Lịch làm việc khác
tiền Bán combo trong bảng lương. Mã cũ chỉ lấy default_combo_sales và không
truy vấn vera_work_schedule_combo_sale. Bản sửa đếm mỗi dòng bán trong kỳ
(tháng hiện tại đến hôm nay), theo username, nhân 100.000đ; không cộng thêm
mức mặc định hoặc cờ combo_sold cũ. Hai nguồn tính lương lịch/chấm công dùng
cùng phép tính; bảng tổng hợp đọc số lượt một lần cho tất cả bộ phận. Khi
người dùng bấm tính lại sẽ lấy số mới; không tự sửa số tiền lịch sử đã chốt.

Lương KTV đã kiểm tra cờ Không tính lương nhưng ba truy vấn nhân viên hành
chánh còn thiếu điều kiện. Thêm điều kiện ở API, ẩn các tài khoản đã đánh dấu
trong bản nháp/lịch sử mở để sửa; từ chối yêu cầu lưu/hoàn thành/xuất có tài
khoản bị loại từ tab cũ. Chỉ lọc bản hiển thị, giữ nguyên lịch sử lưu gốc.

Bổ sung lọc tên không dấu và bộ phận trên dữ liệu đã tải. Tổng tiền và Excel
theo bộ lọc; lưu nháp/hoàn thành giữ toàn bộ bảng, không xóa các dòng tạm ẩn.
Trên mobile bỏ khung input nằm trong ô bảng, giữ số tiền, chỉnh sửa và focus.

Video cho thấy mở Cấu hình lương dẫn tới màn hình khôi phục; chưa có trace
production để kết luận ngoại lệ khởi đầu. Xác nhận đường khôi phục trước đây
đặt ở trang Lương chung nên retry chỉ reset module KTV, không reset module
Cấu hình vừa lỗi. Cô lập Suspense/error boundary từng tab, retry đúng module
và giữ tab khác/dữ liệu đang nhập. Kiểm thử mở cấu hình có dòng thực, quyền
Admin, lỗi import giả lập rồi retry, lọc/chỉnh/lưu/xuất và PostgreSQL cho nguồn
combo, biên ngày, cờ loại nhân viên, bảo toàn lịch sử. Cần Deploy VPS Production
và đối chiếu bảng nháp thực tế; không xem CI là lần tính/gửi lương production.

## 26-09-2026: bỏ vùng thông báo rỗng trên toàn bộ trang

Người dùng đánh dấu các khoảng trống trên 20 trang. Đối chiếu ảnh và mã xác
nhận StableFeedback vẫn tạo ô cao 52px (64px trên mobile) khi không có thông
báo: một ô trong AppShell, ô còn lại trong nội dung nhiều trang. Đăng ký nghỉ
đang dùng bản khôi phục, nên khoảng đánh dấu nằm ở khung chung. Lương và Lịch
sử checkin cũng được sửa qua khung chung, không thay đổi dữ liệu nghiệp vụ.

Ẩn hoàn toàn ô rỗng bằng hidden/display:none để ô không chiếm chiều cao hoặc
khoảng cách grid/flex. Giữ phần tử bao và nội dung lỗi/kết quả khi có thông báo;
không remount bảng, bộ lọc hoặc form lân cận, không thêm popup hay request.
Live Tour tiếp tục chỉ dùng overlay hóa đơn chờ thanh toán như trước. Thay đổi
chỉ ở component/CSS dùng chung và kiểm thử, không chạm mã mật khẩu/định danh,
API, giao dịch, quyền hay dữ liệu. Kiểm thử kiểm tra ô rỗng ẩn, thông báo hiện,
chuyển trạng thái giữ bảng/focus/scroll và luồng mở Đăng ký nghỉ. JSDOM không
đo pixel thực; vẫn cần Deploy VPS Production để áp dụng frontend thực tế.

## 26-09-2026: mốc lịch sử Doanh thu và cập nhật Auto khi đang mở trang

Người dùng sửa mốc bắt đầu thành 05-09-2025 và xác nhận giữ sổ Manual đến hết
24-09-2026, lấy thanh toán/TIP/Nhập mua từ 25-09-2026. File xuất do người dùng
cung cấp có 923 giao dịch trong khoảng lịch sử này. Không đưa dữ liệu tài chính
của file vào repository và không import lại vào PostgreSQL.

Auto đọc hai khoảng không giao nhau trong cùng một câu SQL: lịch sử Manual
chưa xóa trước mốc chuyển đổi, giao dịch hệ thống chưa xóa từ mốc chuyển đổi.
Bảng, tổng tiền, đối chiếu và Excel cùng dùng phép tính này; không tạo bản sao
giao dịch và không gộp nhầm hai khoản hợp lệ chỉ vì cùng ngày/số tiền. TIP trong
kỳ vẫn tính theo khoảng đã chọn, không cộng thêm vào tổng Thu lịch sử. Các nút
Admin Sửa/Xóa/Import hiện đủ nhưng tiếp tục khóa trong Auto theo xác nhận của
người dùng; tổng theo bộ lọc và Excel vẫn hoạt động.

Trang Auto kiểm tra dấu thay đổi mỗi 5 giây khi đang hiển thị. API có kiểm tra
quyền chỉ trả mã băm của bộ đếm/revision và ngày Việt Nam, không tải JSON hóa
đơn hoặc toàn sổ trong lượt kiểm tra. Chỉ khi dấu đổi mới tải lại số liệu; dừng
lượt kiểm tra khi tab ẩn, tránh request chồng nhau, đợi tác vụ/lựa chọn đang lưu
hoàn tất. Đây là cập nhật bằng polling, không phải thông báo đẩy tức thời.
Kiểm tra hạn mức Đăng ký nghỉ đặt nút và kết quả trong cùng hàng hai cột có
giới hạn chiều rộng, bỏ vùng giữ chỗ rỗng cũ.

Kiểm thử bao gồm khoảng chuyển đổi, giao dịch giá trị bằng nhau, đọc lặp không
ghi thêm, Excel có bộ lọc, thay đổi/xóa nguồn, quyền ghi và polling ẩn/bận/lỗi.
Chưa xác minh số dư thực tế hoặc thao tác tài chính trên production. Cần Deploy
VPS Production để cập nhật cả API lẫn frontend thực tế; Pages riêng không đủ.

## 26-09-2026 15:32: frontend production vẫn ở bản VPS trước các sửa UI

Ảnh mới vẫn có hai vùng giữ chỗ Live Tour, và người dùng không mở được Đăng ký
nghỉ ở desktop/mobile. Đã kiểm tra trực tiếp DOM trang đăng nhập tại
`app.veraspa.vn`: URL gốc và URL có reload đều nhận `index-COQl75VV.js` cùng
`index-BzLSJTZQ.css`. Log Deploy VPS Production #545 (run 36223625705, 13:23 ICT)
build chính entry này vào frontend-next tại commit
`745a46028fbfa93fe0261c30738dbfb2c9fee284` (#282).

Ngược lại, artifact GitHub Pages của main `f8461efd` (run 36229456931) chứa
`index-CFjHMqmu.js` và `index-CTTwSQva.css`. Vì vậy đã xác nhận các sửa #284–287
chưa nằm trong giao diện được domain thật phục vụ; không thể quy lỗi chỉ cho
cache của người dùng. Hướng dẫn trước đó “frontend-only không cần deploy VPS”
không đúng với hosting hiện tại. Không đổi DNS, khóa DB, idempotency hay dữ liệu.

Main đã bỏ các vùng giữ chỗ và có bản Đăng ký nghỉ được khôi phục. Kiểm thử lại
42 trường hợp Live Tour/leave route/navigation đạt. Triển khai main lên VPS theo
yêu cầu người dùng để đưa các thay đổi này vào nơi thực sự phục vụ frontend.
Thêm dấu commit/entry vào build và kiểm tra cả HTML canonical lẫn URL tải mới ở
cuối Deploy VPS. Metadata không chứa biến môi trường, token hay dữ liệu cá nhân.
Lỗi đối chiếu phải làm workflow thất bại, không tự sửa routing hay xóa cache.

Ghi nhận này xác minh sai lệch phiên bản từ DOM/artifact/log triển khai. Chưa có
phiên đăng nhập production trong trình duyệt bảo trì để kiểm thử thao tác thật;
không xem CI, health hoặc metadata thành bằng chứng một lần ghi nghiệp vụ.

## 26-09-2026: Doanh thu Auto dùng chung, chờ triển khai VPS

Rà soát xác nhận Auto cũ lấy `subtotal/service_money` trong report nhưng thanh
toán thực tế ghi `total` đã phân bổ, chưa lấy Nhập mua và chỉ chọn chế độ trên
trình duyệt. Bản sửa cộng `total - tip` và `tip` theo ngày Việt Nam; tổng Thu
bao gồm TIP, tổng Chi lấy `amount` của Nhập mua chưa xóa, từ 05-09-2026 đến
ngày hiện tại. Bảng Thu/Chi, tổng số và Excel dùng cùng phép tính. Vé combo
đã thu khi bán không bị tính lại khi dùng lượt. Không tạo bản sao giao dịch.

Admin lưu chế độ dùng chung có revision trên server; mọi API ghi Manual
(tạo/sửa/xóa/import/TIP nhập số tiền) kiểm tra chế độ trong cùng transaction và
cùng khóa ngắn với lệnh đổi chế độ. Thao tác đang ghi được hoàn tất; lệnh cạnh
tranh trả 409 để thử lại, không hủy kết nối. Auto lưu riêng khoảng ngày TIP,
số tiền tính trên server, giữ nguyên sổ Manual và cấu hình TIP Manual.

Kiểm thử bổ sung bao gồm giao diện năm vai trò, PostgreSQL qua HTTP, giảm giá,
combo, xóa hóa đơn, biên ngày Việt Nam, xuất Excel và tranh chấp đổi chế độ.
Chưa truy cập PostgreSQL production hoặc xác minh doanh số thực tế. Sau deploy
VPS cần đối chiếu commit, `/v2/auth/health`, `/v2/health` và Thu/Chi ngày 05-09-2026
với hóa đơn đã thanh toán và Nhập mua; không suy ra production đúng chỉ từ CI.

## 25-09-2026: quyền trạm điện thoại, IP FaceGate và độ phủ ánh xạ, chưa triển khai

Mục Quản lý thiết bị trước đây chỉ cho Admin dù trạm điện thoại cần người vận
hành được phân quyền. Bản sửa thêm các quyền tách biệt để xem/sửa hồ sơ, dùng
trạm điện thoại, xác nhận chấm công, xem lịch sử, ánh xạ FaceGate và đổi IP máy.
Kiểm tra quyền thực hiện ở API; điều hướng và nút thao tác chỉ hiển thị theo
quyền. Admin có thể cấp riêng từng quyền trong mục Phân quyền.

Hồ sơ FaceGate hiện chỉ lưu IP nhưng truy vấn vẫn đọc endpoint tĩnh của máy chủ.
Bản sửa giới hạn IP thiết bị hiện tại trong mạng nội bộ 192.168.1.0/24, lấy
địa chỉ đã lưu trước khi thực hiện I/O và dùng riêng trong phạm vi một lệnh;
không giữ kết nối DB khi truy cập máy. Mật khẩu không lưu trong hồ sơ hoặc mã,
vẫn lấy từ biến môi trường bí mật của máy chủ. Có phép thử đăng nhập chỉ trả
trạng thái, không trả chi tiết tài khoản. Khi IP thay đổi, ánh xạ ở IP cũ không
được tính là đã xác nhận cho máy hiện tại; Admin cần kiểm tra lại từng hồ sơ và
mã TimeSoft. Trang Lịch sử checkin hiển thị số nhân viên chưa có ánh xạ hợp lệ.

Không tự gán nhân viên theo tên hiển thị trên máy, không tự đưa FaceGate vào
tính công/lương khi chưa xác minh đầy đủ danh tính, ngữ nghĩa trạng thái máy
và sự tương ứng với mã TimeSoft. Chưa truy cập được LAN và dữ liệu production để
kiểm tra IP mới, xác nhận danh sách toàn bộ hồ sơ hay bật nguồn tính công.

## 25-09-2026: trạm điện thoại chụp ảnh / quét mã / chấm công, chưa triển khai

Trang Quản lý thiết bị đã lưu hồ sơ điện thoại nhưng không có đường truyền dữ liệu.
Bản sửa bổ sung trạm camera trong ứng dụng qua HTTPS: Admin đăng nhập trên điện
thoại, chọn hồ sơ thiết bị đang bật, chụp JPEG tối đa 2 MB hoặc quét/nhập mã rồi
gửi sự kiện có mã UUID tới PostgreSQL; Admin ở máy khác xem ảnh và sự kiện theo
quyền. Ảnh chỉ trả về cho Admin và không cache; sự kiện cũ được xóa khi có sự
kiện mới sau 7 ngày. Sự kiện chấm công chỉ vào nguồn chấm công khi Admin xem
ảnh và xác nhận cụ thể. Lệnh xác nhận ghi nguồn `mobile_admin_confirmed` qua
`record_checkin`, giữ cùng giao dịch với dấu đã xác nhận và khóa hàng để chống
ghi hai lần. Điện thoại không tự động xác minh khuôn mặt; xác nhận chấm công có
thể kết thúc kỳ nghỉ theo quy tắc HR hiện có. Luồng này không tự phát sinh
FaceGate / TimeSoft event hoặc đổi công thức lương.

Web Bluetooth chỉ nhận diện ngoại vi BLE mà trình duyệt hỗ trợ; ứng dụng web
không thể điều khiển Wi-Fi Direct Android hoặc Multipeer Connectivity iOS trực
tiếp. Trạm điện thoại mới truyền qua API HTTPS khi hai máy có mạng và không
khẳng định ghép nối Wi-Fi Direct cấp hệ điều hành. Chưa xác minh thiết bị,
PostgreSQL hoặc một lần xác nhận thực tế trên production.

## 24-09-2026: kênh Popup và nhóm nhận thông báo, chưa triển khai

Rà soát mã xác nhận Popup trước đây dùng chung trạng thái `in_app`, còn
`vera_v2_notification_channel_setting` chỉ cho phép hai kênh. Bản sửa mở rộng
CHECK constraint cho `popup` mà giữ nguyên các hàng cũ; hàng gửi Popup được
lọc theo người nhận, nhóm, trạng thái kênh và ngày hiện tại trước khi trả về.
Nhóm tùy chỉnh lưu tài khoản đang hoạt động trong bảng riêng có RLS và thu hồi
quyền trực tiếp, chỉ Admin quản lý; xóa nhóm đang được tuyến gửi sử dụng sẽ bị
từ chối. Danh sách loại thông báo bổ sung từng thao tác API đã đăng ký; mỗi
loại mới chỉ gửi sau khi Admin bật hoặc cấu hình tuyến nhận. Không đổi xác
thực, dữ liệu chấm công, penalty hay doanh thu.

Chưa kiểm tra migration PostgreSQL và popup trên production; sau triển khai
cần đối chiếu commit backend và frontend, hai health endpoint, một lượt tạo
nhóm/gửi popup thử với tài khoản đúng quyền và từ chối tài khoản khác.

## 24-09-2026: lọc nhắc nghỉ giữa ca và nội dung đào tạo, chưa triển khai

Rà soát mã xác nhận quy tắc gửi `attendance_break` có thể bao gồm Admin khi
nhắm nhóm rộng. Bản sửa bỏ Admin khỏi sự kiện `attendance-break-reminder` ở lúc
ghi hàng đợi; kiểm tra lại trước khi gửi push và khi đọc hộp thư/chi tiết để
chặn cả thông báo còn chờ. Cảnh báo vào lại trễ vẫn theo quy tắc hiện hành.
Không thay đổi phép tính chấm công, hạn nghỉ, hình phạt hay giao dịch nguồn.

Thông báo hoàn tất buổi đào tạo nay lấy ngày và giờ của bản ghi đào tạo trong
cùng kết nối để tạo nội dung giờ bắt đầu/kết thúc và số giờ; chi tiết giao diện
dùng các trường có sẵn. Chưa xác minh dữ liệu PostgreSQL hoặc thiết bị thật trên
production; cần kiểm tra luồng gửi và hai health endpoint sau triển khai.

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
