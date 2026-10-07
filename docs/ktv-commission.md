# Hoa hồng Leader và Nhân viên

Admin cấu hình tại Nhân sự → Hoa hồng dịch vụ & sản phẩm. Mặc định tắt,
0%; có tỷ lệ dịch vụ và sản phẩm riêng cho từng bộ phận. Bộ phận Nhân sự
được sử dụng, độc lập với quyền tài khoản. TIP vẫn hưởng 100%.

Khi bật, hóa đơn thanh toán mới lưu tỷ lệ, bộ phận và căn cứ tính. Thay đổi
cấu hình áp dụng cho hóa đơn mới; tắt không xóa hoa hồng đã ghi nhận. Hóa đơn
cũ chưa có căn cứ không được tự tính hồi tố. Bảng lương đã hoàn thành không
tự thay đổi: tính lại lương và lưu lại nếu cần đối soát hóa đơn đã sửa/hủy.

- Dịch vụ/sản phẩm bán riêng: tiền dòng hóa đơn sau giảm giá, không gồm TIP.
  Giảm giá hóa đơn phân bổ theo giá trị các dòng; dòng có cả hai loại phân bổ
  theo giá trị mặt hàng. Làm tròn hoa hồng từng loại/từng dòng đến đồng.
- Combo: giá đã mua / tổng số vé của gói đã mua × số vé thực trừ cho nhân viên.
  Không dùng số vé còn lại, giá danh mục hiện tại, hoặc tính lúc bán combo.
  Giá trị combo và số vé được lưu ở lượt thanh toán nên thay giá gói sau đó
  không đổi hoa hồng đã ghi nhận.
- Sản phẩm bán riêng: đánh dấu Loại doanh thu trong Cài đặt → Dịch vụ.
  Mặc định danh mục hiện có là dịch vụ; loại được chụp vào dòng booking.
  Dòng không gán nhân viên hoặc nhân viên ngoài Leader/Nhân viên không hưởng.

Lương KTV lấy TIP từ báo cáo và hoa hồng từ hóa đơn còn hiệu lực, cùng kỳ.
Tiền Lương = TIP + hoa hồng dịch vụ + hoa hồng sản phẩm. Các khoản phụ cấp,
ứng/phạt, tích lũy và khấu trừ tiếp tục theo quy tắc hiện tại. Có thể tính lương
khi chỉ có hoa hồng, không có TIP. Giao diện nháp hiện chi tiết dưới tiền lương,
không thêm cột. Chi tiết cũng lưu cùng bản nháp/lịch sử, không thêm cột Excel.

Sửa hóa đơn tính lại hoa hồng bằng tỷ lệ gốc và giá/giảm giá đã sửa; hủy hóa
đơn loại khỏi nguồn tính lương, giữ dấu vết đối soát. Dùng cùng kết nối DB với
nghiệp vụ thanh toán/tính lương; không thêm mạng hoặc kết nối lồng trong khóa.
