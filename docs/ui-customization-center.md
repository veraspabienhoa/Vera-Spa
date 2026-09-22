# Chỉnh bố cục VERA SPA

Chỉ Admin mở được menu Chỉnh bố cục và ghi cấu hình dùng chung. Các tài khoản khác vẫn nhận bố cục đã lưu. Mở trang cần chỉnh trước khi mở công cụ.

- **Sắp xếp**: bật chỉnh sửa, chọn thành phần rồi kéo trong cùng nhóm hoặc dùng Trước/Sau. Nút lưu, hủy, đóng và đăng xuất được khóa khi có nhãn cố định.
- **Nút bấm**: chọn khung cha của nhóm nút; chọn số dòng hoặc tự động. Vừa màn hình cho phép xuống thêm dòng trên màn hình hẹp thay vì thu nhỏ vùng bấm. Gom nút phụ chỉ áp dụng khi nhóm gồm các nút/liên kết; tab và nhóm lẫn ô nhập giữ nguyên cấu trúc.
- **Tên hiển thị**: chọn nút/menu/tab được đăng ký; nhập văn bản thuần, tối đa 100 ký tự. Nội dung dữ liệu động (tên nhân viên, số tiền, trạng thái nghiệp vụ) không đổi tên. Route và handler giữ nguyên.
- **Bảng & cột**: chỉnh độ rộng các cột có định danh ở bảng đang mở. Phần Live Tour dùng cấu hình cột chuyên biệt đã có: ẩn/hiện, thứ tự, độ rộng, cỡ chữ.
- **Phòng Live Tour**: toàn bộ cấu hình phòng và chữ trước đây ở Cài đặt/Giao diện. Bố trí phòng không thay đổi booking, số phòng hay giường.
- **Lịch sử**: 50 lần lưu bố cục chung gần nhất, người sửa và thời gian. Khôi phục theo Mobile/Desktop bằng phiên bản hiện tại, không ghi đè im lặng. Lịch sử này không chứa snapshot cấu hình phòng/cột Live Tour; phần đó giữ cơ chế mặc định/khôi phục riêng của Live Tour.

Bấm Lưu cho tất cả để áp dụng; Hủy để bỏ bản xem trước; Khôi phục thành phần hoặc Mặc định để chuẩn bị bản nháp mặc định rồi lưu. Đóng công cụ có xác nhận khi còn thay đổi chưa lưu. Tạm dùng bố cục mặc định tắt áp dụng tùy chỉnh chung nhưng giữ nguyên cấu hình để bật lại. Cấu hình phòng/cột Live Tour độc lập với công tắc này.

## Bảo trì

`data-ui-key` trong JSX là khóa ổn định đã lưu vào nguồn, không tạo lại khi đổi tên file, lớp CSS hay vị trí. Registry `vera_ui_registry.json` là allowlist backend/frontend. Không sửa khóa khi chỉ đổi nhãn. Nhóm tab lặp dùng khóa con dựa trên React key/id; phải duy trì React key ổn định.

`web-v2/scripts/register-ui.mjs` cấp khóa cho thành phần mới. Rà soát registry trước khi commit, đặc biệt trường locked và nội dung động. `wrap-ui-toolbars.mjs` chuyển nhóm sang UiToolbar, giữ ref/props. Không chạy các script để tạo lại các khóa cũ. Đăng nhập và khôi phục xác thực không nằm trong phạm vi tùy chỉnh.

Cấu hình cũ `l-*` vẫn được áp dụng qua định danh legacy. Khi chỉnh phần tử có khóa mới, cấu hình mới ưu tiên trên cùng phần tử. Cấu hình sai được bỏ qua; số phiên bản và khóa giao dịch được giữ khi ghi. Bảng `vera_ui_layout_audit` được tạo lười trong giao dịch khi lưu/đọc lịch sử; chưa có migration production chạy trước deployment.

Phạm vi hiện tại là cấu hình chung Admin. Tùy chọn cá nhân, đa ngôn ngữ và trình vẽ sơ đồ không gian không được bổ sung trong đợt này.
