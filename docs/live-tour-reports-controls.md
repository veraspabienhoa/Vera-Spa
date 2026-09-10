# Live Tour: báo cáo, ngày giờ hóa đơn và điều khiển

Yêu cầu nguồn: `f61f76bec7ec84511e0b7ce8b11a9bb00dfb13ee.webarchive`, đối chiếu lại với `84fb79b460dba57ddb3d5a02140bbf8b7dff6060.webarchive` khi tiếp tục ngày 10/09/2026.

## Thay đổi

- Gỡ điều khiển thêm/xóa/ẩn/hiện nhân viên và các nhánh xử lý cũ. Nhân viên hợp lệ lấy từ danh sách hệ thống; cờ ẩn cũ không còn loại nhân viên khỏi bảng. Gỡ các nút Đặt lịch nhanh, Đặt lịch, Đặt lịch hàng loạt và +30 phút khỏi ngăn điều khiển, cùng các form cũ. Booking qua phòng (double click) và nhân viên tiếp tục dùng dialog hiện hành.
- Đổi Break thành Nghỉ giữa ca. Chụp hình bảng tua xuất đầy đủ hàng và tất cả cột từ STT, bỏ banner phía trên; văn bản dài xuống dòng, giữ số 0, màu dòng và dấu tiếng Việt.
- Phiếu chờ và hóa đơn dịch vụ giữ giờ booking trong từng dòng. Hóa đơn lấy giờ booking sớm nhất khi gộp nhiều lượt. `effective_at` và ngày hóa đơn dùng giờ Việt Nam; `recorded_at`/`created_at` vẫn ghi thời điểm hệ thống thực sự tiếp nhận thanh toán. Không còn dùng Lùi 1 ngày khi thanh toán dịch vụ; bán combo riêng vẫn giữ quy tắc hiện hành.
- Hóa đơn cũ/phiếu cũ thiếu giờ booking giữ thời điểm đã lưu; không suy đoán giờ booking từ phiên mới của cùng nhân viên. Admin có thể sửa qua trường ngày giờ, có lý do và snapshot trước/sau. Sửa ngày phiếu chờ được giữ qua checkout; sửa ngày hóa đơn đã trả cập nhật các dòng doanh thu/TIP và lượt dùng combo liên quan, không đổi thời điểm ghi nhận hay số bill.
- Menu Báo cáo riêng: hóa đơn, doanh thu, TIP và combo. Sửa/xóa từ báo cáo dùng luồng điều chỉnh/hủy hóa đơn gốc, đồng bộ các sổ liên quan. Xóa một dòng báo cáo hóa đơn được ghi rõ là hủy toàn hóa đơn tương ứng; không cho sửa riêng số tổng làm lệch sổ.
- Bộ lọc ngày hôm qua, hôm nay, tuần trước/này, tháng trước/này, tùy chỉnh; tìm nhân viên, khách hàng, dịch vụ. Tuần bắt đầu thứ Hai; ngày theo Việt Nam. Nhân viên và dịch vụ phải khớp cùng dòng hóa đơn. Live Tour: Chờ thanh toán, Hóa đơn đã thanh toán, Báo cáo đều dùng bộ lọc này. Xuất báo cáo mang theo bộ lọc. Các sổ được đọc đầy đủ để tìm cả hóa đơn cũ, không cắt còn 500/1000 dòng trước khi lọc.
- Khách hàng và Live Tour đều có sửa/xóa khách hàng và combo đã mua. Sửa combo điều chỉnh lượt còn lại (từng dịch vụ khi có thành phần), giữ lượt đã dùng và hóa đơn bán ban đầu. Xóa là gỡ khỏi danh sách sử dụng, giữ bằng chứng giao dịch. Chặn khi còn booking/phiếu giữ chỗ; xóa khách hàng còn vé phải xử lý combo trước. Mọi điều chỉnh có lịch sử trước/sau và lý do.
- Rà soát tiếp: nối quyền sửa ngày giờ cho hộp Chờ thanh toán; hiển thị/xuất ngày giờ đã điều chỉnh; xuất báo cáo doanh thu/combo có đầy đủ số tiền và kiểm tra quyền xem thông tin khách. Xuất danh sách khách bỏ hồ sơ/combo đã xóa; lịch sử vẫn giữ nguyên. Bỏ danh sách loại trừ nhân viên thủ công cũ để mọi Leader/Nhân viên đủ điều kiện đều trở lại bảng từ danh sách hệ thống.

## Phân quyền

Các quyền mới không kế thừa quyền thanh toán hay quản trị danh mục. Admin có đầy đủ quyền theo cơ chế hiện hành; mặc định Lễ tân/Quản lý không được sửa/xóa combo khách. Có thể cấp riêng trong Phân quyền:

| Quyền | Phạm vi |
| --- | --- |
| `live_tour_invoice_date_edit` | Ngày giờ hóa đơn; cần thêm quyền sửa/xem loại hóa đơn tương ứng |
| `live_tour_customers_edit` | Sửa hồ sơ; cần Xem khách hàng |
| `live_tour_customers_delete` | Xóa hồ sơ; cần Xem khách hàng |
| `live_tour_customer_combo_edit` | Sửa combo đã mua; cần Xem khách hàng |
| `live_tour_customer_combo_delete` | Xóa combo đã mua; cần Xem khách hàng |
| `live_tour_reports_edit` | Sửa báo cáo hóa đơn; cần Xem báo cáo và hóa đơn đã thanh toán |
| `live_tour_reports_delete` | Hủy hóa đơn từ báo cáo; cần Xem báo cáo và hóa đơn đã thanh toán |

Quyền tạo khách hàng vẫn đi cùng thanh toán. Trang Báo cáo có endpoint riêng, không yêu cầu quyền xem bảng tua. Phản hồi sửa báo cáo không trả bảng nhân viên. Nhật ký khách hàng không lưu trong cache trình duyệt.

## Kiểm tra và triển khai

- Xác nhận khi tiếp tục: toàn bộ pytest **682 đạt**; ESLint **0 lỗi, 3 cảnh báo có sẵn**; Vite production build thành công. Kiểm tra mới bao phủ báo cáo Excel có tiền và phân quyền thông tin khách, giờ phiếu chờ đã sửa, danh sách khách sau xóa và phục hồi nhân viên từ danh sách hệ thống.
- GitHub kích hoạt thêm Payroll 3.8 CI khi App.jsx đổi: hai kiểm tra cũ còn tham chiếu hàm đã thay bằng đối trừ nợ qua save hook và nhãn/nơi đặt nút sửa/xóa đã đổi từ trước trên main. Cập nhật hai kiểm tra theo luồng hiện tại, giữ kiểm tra trạng thái nợ, hook lưu, hành động sửa/xóa và không tạo nút lưu trùng; không đổi logic lương, triggers hoặc bước kiểm tra bắt buộc.
- Kiểm thử API: bảo toàn giờ booking sau khi nhân viên nhận lượt mới; sửa ngày cần quyền riêng và đồng bộ sổ; từ chối dữ liệu sai không ghi dở dang; phân quyền khách/combo; vé thành phần và giữ chỗ; báo cáo và export; ảnh toàn bảng; các mốc tuần/tháng theo Việt Nam.
- Build React và ESLint. Có fixture chỉ đọc cho `/preview?page=reports` và `/preview?page=customers`, không gọi API sản xuất. Trình duyệt trong phiên làm việc chặn localhost, nên chưa hoàn tất kiểm tra trực quan qua trình duyệt.
- Sau merge, chạy **Deploy VPS Production** và **Deploy VERA SPA Web V2** trên cùng commit `main`. Chạy API trước rồi giao diện. Không cần thay schema PostgreSQL; dữ liệu JSON có thêm trường thời điểm, dấu xóa và lịch sử.
- Kiểm tra sau deploy: mở Báo cáo và Khách hàng trên điện thoại; thử mở/đóng dialog; kiểm tra bộ lọc; tải ảnh bảng tua. Đối chiếu quyền bằng tài khoản Lễ tân/Quản lý trước khi cấp các quyền mới.
