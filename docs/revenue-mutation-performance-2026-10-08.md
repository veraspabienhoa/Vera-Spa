# Thu/Chi: giảm dữ liệu đọc trong thao tác ghi — 08-10-2026

Tiếp tục từ main `84ce651c23669b4db16cb75ed8c72edfe511a7b5` (PR #499).

## Thay đổi

- Xóa một khoản thu/chi không còn đọc và serialize toàn bộ sổ để lấy nội dung
  thông báo. Dùng bản ghi đã SELECT theo khóa chính và FOR UPDATE trong hàm
  xóa, cùng phiên bản ghi vào audit. Thông báo chỉ được đăng ký sau commit.
- Lưu Tiền TIP dùng một truy vấn SUM/MAX của các dòng chưa xóa. Database trả
  một dòng tổng thay vì tất cả dòng lịch sử; không dựng ngày/giờ/nhãn/người nhập
  cho từng dòng. Giữ phạm vi tổng toàn sổ hiện hữu, ngày Việt Nam khi thiếu
  transaction_date, kỳ mặc định và kỳ nhập tay, phản hồi balance và quyền ghi.

Truy vấn tổng vẫn phải xử lý các dòng active tại database. Chưa thêm cache,
index hoặc thay đổi cấu trúc ledger. Không coi đây là O(1) tại database hay
bằng chứng toàn hệ thống nhanh 100 lần. Đường xóa chỉ lấy một dòng nghiệp vụ;
đường lưu TIP chỉ truyền một dòng tổng về Python, độc lập số dòng lịch sử.

## Kiểm tra

35 kiểm thử cục bộ đạt, gồm giới hạn đọc khi xóa, chi tiết thông báo khớp audit,
quyền/ngày nhập Việt Nam, lỗi không gửi thông báo, kỳ TIP và balance, hồi quy
revenue, attendance connection reuse, auth pool, outbox và VPS diagnostics.
Một kiểm thử PostgreSQL đối chiếu SUM/MAX với list_entries (ngày null qua
nửa đêm Việt Nam, dòng đã xóa, sổ rỗng) chờ CI PostgreSQL biệt lập.

## Trạng thái triển khai tại thời điểm kiểm tra

GitHub main CI #37673191187 đạt cho `84ce651c`; frontend deploy #37673191383
đạt. Lần Deploy VPS Production gần nhất #37653051322 đạt tại `e734dd90`,
trước PR #499. Đây là bằng chứng workflow, chưa phải phép xác minh runtime
hiện tại hoặc tác vụ nghiệp vụ. Cần deploy backend tương ứng, xác minh SHA,
cả auth/business health và thử thao tác được kiểm soát trước khi kết luận
hiệu quả production. Lượt cập nhật mã này không chạy deploy VPS.
