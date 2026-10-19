# Kéo sắp xếp và chỉnh Mobile trên desktop

Admin mở Giao diện tại trang cần chỉnh, chọn Tùy chỉnh. Kéo sắp xếp là chế độ mặc định: kéo thành phần tới trước/sau một thành phần khác hoặc tới nhóm khác cùng biểu mẫu. Vạch chỉ vị trí thả hoạt động cả ở khoảng trống giữa các nút và trên các dòng đã xuống hàng. Các nhóm được đăng ký bằng UiToolbar hỗ trợ chuyển khung; bảng nghiệp vụ và các thành phần khóa không phải đích thả.

Ô lọc có nhãn cố định trong UiToolbar có định danh theo nhóm và nhãn, không theo vị trí. Việc xuất hiện/ẩn một ô tùy chọn không đổi định danh các ô còn lại. LiveTourSearchSelect chuyển cả nhãn và điều khiển; callback nghiệp vụ được giữ qua React portal.

Lưu áp dụng bố cục của thiết bị đã chọn. Hủy bỏ bản xem trước; Mặc định đặt lại bản nháp để Admin xem trước rồi lưu. Quyền sửa vẫn chỉ dành cho Admin và được kiểm tra phía server.

Trên desktop, chọn “Chỉnh Mobile trên desktop”. Khung cùng nguồn mở đúng trang với viewport 360/390/430 px, áp dụng media query mobile thật. Trong khung chọn Tùy chỉnh, thao tác bằng chuột và Lưu. Chế độ Desktop bị khóa trong khung này để tránh lưu nhầm. Đóng khung sẽ hỏi xác nhận vì bản nháp chưa lưu nằm trong khung. Các tab/bộ lọc của trang trong khung có trạng thái riêng; chỉ bố cục được lưu dùng chung.

Không truyền token qua URL hoặc thông điệp giữa các cửa sổ. Khung sử dụng đăng nhập và kiểm tra quyền hiện có. Source changes only; deployment remains separate.
