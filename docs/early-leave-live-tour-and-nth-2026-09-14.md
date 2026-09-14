# Về sớm sau nghỉ giữa ca và Người thứ N — 14/09/2026

Bản sửa dựa trên ZIP commit d222b66d0edea0d56e5e1610790e5e5147ad2d87.
Chưa push hoặc deploy; không truy cập/chỉnh dữ liệu production.

## Live Tour

- Đọc chấm công trước khi tính trạng thái lịch nghỉ trong cùng giao dịch.
- Khi có lý do chứa “Về sớm”, có giờ ra hôm nay nhưng chưa có giờ quay lại,
  tự chuyển Đi làm thành Nghỉ phép và để trống Vào ca. Chỉ có lịch đăng ký
  mà chưa có bằng chứng ra ngoài thì không chuyển trạng thái.
- Nhận cả trường hợp chấm công đã phân loại giờ ra thành check-out về sớm.
- Giữ nguyên dịch vụ, booking, phòng, thời gian dịch vụ, hóa đơn và tiền phạt.
- Khi có giờ quay lại thật hoặc lịch về sớm bị sửa/xóa, áp dụng lại lịch hiện
  hành; vẫn giữ Nghỉ phép nếu còn một lý do nghỉ cả ngày.
- Tác vụ nền hiện có (15 giây) dùng cùng luồng dữ liệu mới. Các lần đọc dùng
  lại kết nối của giao dịch, không mở kết nối lồng hoặc gửi thông báo trong khóa.
- Giữ cơ chế kết thúc nghỉ thủ công đã được cấp quyền và đối chiếu danh tính
  nhân viên không mơ hồ. Lỗi/mất dữ liệu chấm công không được suy ra là quay lại.

## Người thứ N

- Luồng sửa/xóa đã gọi tính lại nhóm cũ và nhóm mới, nhưng bộ truy vấn cũ chỉ
  chọn source_sheet_id của MainData. Nay tính trên mọi bản ghi cùng ngày trong
  PostgreSQL, kể cả bản ghi không có dòng Sheets.
- Giữ thứ tự source_row/id, các nhóm nghỉ/đi trễ/về sớm không phép riêng biệt,
  số tiền cơ bản từ Nội quy và công tắc lũy tiến cuối tuần.
- Cập nhật bằng record_uid, giữ nguồn gốc bản ghi. Chỉ các dòng MainData hợp
  lệ mới được gửi sang bản sao Sheets, không ghi dòng 0 hoặc nguồn khác.
- Không thay đổi quyền sửa/xóa lịch nghỉ, nhóm 1–5 hoặc quyền Admin cấu hình.
- Đây là sửa cho các lần cập nhật tiếp theo, không tự chạy sửa tài chính hàng
  loạt trên dữ liệu cũ và chưa chứng minh nguyên nhân duy nhất trên production.

## Kiểm chứng

Các test mới: test_early_leave_live_projection.py và
test_progressive_rebalance_all_sources.py. Bao gồm chuyển trạng thái, quay lại,
xóa lịch, lặp nhiều lần không ghi revision thừa, nguồn dữ liệu hỗn hợp, tính lại
hai nhóm và công tắc cuối tuần. Cần nghiệm thu tài khoản thật sau triển khai.
