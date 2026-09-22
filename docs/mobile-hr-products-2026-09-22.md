# Mobile, nghỉ phép, đào tạo và sản phẩm — 22-09-2026

## Giao diện
- Bảng dịch vụ/khách hàng dùng đầy đủ cột trong chiều rộng mobile; nhãn xuống dòng, không ẩn dữ liệu. Khách hàng: Lịch sử đứng trước Sửa/Xóa; chi tiết combo ở cột Combo.
- Nhóm Sao chép ô đến Lưu lịch thành lưới hai cột trên mobile. Bỏ nhãn Đã tự lưu; giữ trạng thái đang lưu/lỗi và Excel chưa lưu.
- Tab lương, nguồn doanh thu, đào tạo, hợp đồng và tablist dùng chung cùng một hàng trên mobile; nội dung nút có thể xuống dòng.
- Auto Check bỏ phần Giảm tải hệ thống và các request điều khiển cache TourVera từ trang đó. Không thay đổi cơ chế phạt/cảnh báo còn hoạt động.

## Phép năm
- Tổng quan gồm đơn pending và approved; JOIN hồ sơ đang hoạt động, loại hồ sơ đã xóa/nghỉ việc, đếm người duy nhất. Tô nổi bật từ 3 người/ngày; dữ liệu bộ phận giữ thống kê tỷ lệ.
- Xóa projection của đơn bị xóa/từ chối để tránh thống kê tồn dư.
- Chấp nhận check-in sau ngày kết thúc dự kiến; dùng múi giờ Việt Nam, lấy lần check-in sớm nhất đã lưu từ ngày bắt đầu nghỉ; xử lý lại log trùng khi đơn vừa được duyệt. Giữ sửa tay của Admin.
- Tác vụ TimeSoft tự đồng bộ ngày quay lại sau khi lưu snapshot, độc lập việc mở trang Chấm công và trạng thái Auto Check. Dùng giao dịch riêng, không gọi mạng trong giao dịch. Lỗi được ghi loại lỗi và thử lại chu kỳ sau.
- Chỉ suy ra từ check-in thực sự có trong dữ liệu; không tạo ngày quay lại giả cho lịch sử thiếu dữ liệu.

## Đào tạo
- Danh sách nhân viên có kết quả theo quyền hiện có, bấm tên để xem đầy đủ báo cáo.
- Bảng từng ngày: tổng giờ, từng buổi bắt đầu/kết thúc, chủ đề, người đào tạo, tay nghề, tinh thần, điểm mạnh/cần cải thiện/nhận xét.
- Tải đủ các trang lịch sử thay vì dừng 50 dòng. Bộ lọc ngày đồng bộ cả bảng và biểu đồ; biểu đồ kỹ năng, radar và tiêu chí tổng hợp giữ dữ liệu gốc.

## QR thanh toán
Trong Live Tour → Danh mục → Cài đặt thanh toán, bật Màn hình QR cho khách hàng và đặt kích thước cửa sổ/mã QR. Từ QR hóa đơn hoặc thanh toán bấm Mở màn hình QR cho khách, kéo cửa sổ sang màn hình phụ của cùng máy. Trên điện thoại trình duyệt có thể mở tab riêng. Đây không phải ghép đôi thiết bị độc lập.
QR dùng đúng ngân hàng/số tiền của hóa đơn, không thay tài khoản người nhận. Cập nhật khi đổi tiền; đóng khi kết thúc màn hình hóa đơn. Có phản hồi khi popup bị chặn hoặc ảnh QR lỗi. Không lưu hóa đơn/token vào localStorage hay URL riêng.

## Sản phẩm
Admin → Cài đặt → Cài đặt sản phẩm: mã, tên, nhóm, đơn vị, giá, trạng thái đang/ngừng dùng, ghi chú. PostgreSQL lưu độc lập trong `vera_product_catalog`, tạo bảng/index trong giao dịch khi truy cập. Chặn trùng mã không phân biệt hoa thường và sửa bằng revision; quyền Admin kiểm tra ở API. Không phát sinh kho, doanh thu hoặc hóa đơn sản phẩm trong đợt này.

## Kiểm chứng
- 1.341 Python tests đạt (gồm 10 ca mới về thống kê, check-in, QR settings và sản phẩm).
- Build đạt; lint không lỗi, còn hai cảnh báo hook có sẵn.
- Hai test tính giờ và test cửa sổ QR đạt, bổ sung vào CI. Toàn bộ frontend ở lần chạy rộng: 154 đạt, 5 lỗi; đối chiếu mã gốc tái hiện đúng 5 lỗi (3 clipboard, 1 kiểm tra source border, 1 source revenue), không do thay đổi này. Test QR mới chạy riêng đạt.
- Cloud Browser không truy cập được preview localhost (ERR_BLOCKED_BY_CLIENT); chưa xác minh hình ảnh trên điện thoại thực.
- Chưa deploy hoặc đối chiếu dữ liệu production.
