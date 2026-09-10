# Live Tour — các tab bị khối phòng che khi cuộn

## Lỗi quan sát trên production

Ở màn hình desktop 1348 × 926, cuộn xuống cuối trang rồi bấm tab
“Hóa đơn đã thanh toán”. Khối phòng vẫn ghim trong toàn trang và che nút tab.
Kiểm tra vị trí giữa nút cho thấy phần tử nhận chuột thuộc khối phòng;
tab không đổi. Dùng bàn phím Enter trên cùng nút vẫn đổi được tab.

## Sửa

Bao khối phòng ghim và bảng nhân viên trong một vùng riêng. Khối phòng tiếp tục
ghim khi xem bảng nhân viên, rồi cuộn ra khỏi màn hình trước các mục Điều khiển,
hóa đơn, khách hàng, báo cáo và lịch sử. Giữ khoảng cách giữa khối phòng và bảng.
Không đổi xử lý booking, phân quyền, hóa đơn hoặc dữ liệu server.

## Kiểm tra

- Production trước sửa: admin mở được mẫu sửa hóa đơn chờ và đã thanh toán;
  cả hai nút lưu bị khóa khi chưa nhập lý do. Nhóm Quản lý hiển thị đủ các quyền
  mới và bốn quyền sửa/xóa mặc định chưa bật.
- Chỉ xem dữ liệu, mở rồi đóng mẫu; không lưu, thanh toán, hủy hóa đơn hay cấp quyền.
- Bản sửa: 29 bài kiểm frontend Live Tour, ESLint và build Vite đạt.
- Sau deploy Web V2 cần xác nhận lại bằng chuột: cuộn xuống cuối trang, chuyển
  các tab, mở/đóng mẫu sửa, rồi cuộn lên kiểm tra khối phòng vẫn ghim trong bảng.

Chỉ cần triển khai giao diện Web V2 cho bản sửa này.
