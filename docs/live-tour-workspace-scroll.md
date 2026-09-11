# Live Tour — hiển thị đầy đủ bảng nhân viên

## Cập nhật theo yêu cầu ngày 11/09/2026

Không ghim khối phòng/Điều khiển và không dịch chuyển tiêu đề bảng theo trang.
Bảng nhân viên giữ chiều cao tự nhiên, hiển thị mọi dòng trong danh sách đã lọc.
Cuộn trang đưa các khối phía trên ra khỏi màn hình, giúp chúng không che nhân viên.
Cuộn ngang vẫn có trên màn hình không đủ chiều rộng cho các cột.

Trong phiên trình duyệt kiểm tra, Live Tour có đủ 37 dòng, bảng cao 1.547 px và
không có phần tràn dọc. Khi cuộn trang 500 px, khối phía trên vẫn ghim đến khoảng
650 px và tiêu đề bảng dịch xuống 489 px, khiến vùng nhìn thấy nhân viên rất thấp.
Đây là lý do chỉ bỏ giới hạn chiều cao/ẩn thanh cuộn dọc chưa giải quyết được.

Bản sửa gỡ listener cuộn/ResizeObserver dùng để dịch tiêu đề, cùng các ref và
CSS ghim liên quan ở cả Live Tour và Bảng tua. Section và bảng dùng chiều cao tự
nhiên; số dòng không bị giới hạn bằng phân trang hoặc cắt mảng trong giao diện.

Kiểm tra hồi quy yêu cầu khối trên/tiêu đề nằm trong luồng trang và giữ đầy đủ
`displayedRecords.map`. Sau triển khai, tải lại trang rồi xác nhận có thể xem tới
nhân viên cuối cùng mà không bị khối phòng che; kiểm tra cả hai đường dẫn truy cập.

## Bối cảnh trước cập nhật

Ở màn hình desktop 1348 × 926, cuộn xuống cuối trang rồi bấm tab
“Hóa đơn đã thanh toán”. Khối phòng vẫn ghim trong toàn trang và che nút tab.
Kiểm tra vị trí giữa nút cho thấy phần tử nhận chuột thuộc khối phòng;
tab không đổi. Dùng bàn phím Enter trên cùng nút vẫn đổi được tab.

### Cách xử lý trước đây

Bao khối phòng ghim và bảng nhân viên trong một vùng riêng. Khối phòng tiếp tục
ghim khi xem bảng nhân viên, rồi cuộn ra khỏi màn hình trước các mục Điều khiển,
hóa đơn, khách hàng, báo cáo và lịch sử. Giữ khoảng cách giữa khối phòng và bảng.
Không đổi xử lý booking, phân quyền, hóa đơn hoặc dữ liệu server.

### Kiểm tra trước đây

- Production trước sửa: admin mở được mẫu sửa hóa đơn chờ và đã thanh toán;
  cả hai nút lưu bị khóa khi chưa nhập lý do. Nhóm Quản lý hiển thị đủ các quyền
  mới và bốn quyền sửa/xóa mặc định chưa bật.
- Chỉ xem dữ liệu, mở rồi đóng mẫu; không lưu, thanh toán, hủy hóa đơn hay cấp quyền.
- Bản sửa: 29 bài kiểm frontend Live Tour, ESLint và build Vite đạt.
- Sau deploy Web V2 cần xác nhận lại bằng chuột: cuộn xuống cuối trang, chuyển
  các tab, mở/đóng mẫu sửa, rồi cuộn lên kiểm tra khối phòng vẫn ghim trong bảng.

Chỉ cần triển khai giao diện Web V2 cho bản sửa này.
