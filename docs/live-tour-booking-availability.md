# Live Tour: chọn giường/phòng theo thời gian còn lại

## Quy tắc chọn nơi đặt lịch

- Giường có lịch **Đang chờ** không xuất hiện để đặt thêm lịch mới.
- Giường đang thực hiện có thời gian còn lại **từ 30 phút trở lên** không xuất hiện. Khi còn **dưới 30 phút**, giường xuất hiện cùng thời gian còn lại theo phút/giây.
- Dịch vụ PR áp dụng quy tắc này cho toàn bộ phòng. Nếu chọn một dịch vụ PR mới, phải xét tất cả dịch vụ hiện tại trong phòng; dùng thời gian còn lại lớn nhất trong các phiên đang phục vụ.
- Phiên chưa có mốc bắt đầu hoặc chưa xác định thời lượng không được coi là sắp xong. Phiên đã hết thời gian nhưng chưa Hoàn thành có thể nhận lịch chờ, với thông báo rõ trạng thái này.
- Quy tắc áp dụng cho hộp thoại booking mới, booking từ nhân viên/phòng và danh sách đặt lịch hàng loạt. Việc tính nhóm phòng dùng cấu hình khu vực, kể cả tên tùy chỉnh như “Phòng Sen”.
- Thời gian trong hộp thoại cập nhật theo đồng hồ của trang; không cần đóng/mở lại để giường chuyển qua ngưỡng 30 phút.

## Giữ lịch sắp tới và bắt đầu phục vụ

- Chọn giường sắp xong chỉ tạo **Đang chờ**. Server vẫn từ chối **Thực hiện** nếu phiên trước chưa Hoàn thành; không cho phép hai nhân viên thực hiện đồng thời trên cùng giường hoặc trong phòng đang khóa PR.
- Một lịch đang chờ giữ vị trí của nó, ngăn lịch thứ ba chiếm lại giường. Khi phiên trước Hoàn thành/chuyển chờ thanh toán, lịch mới có thể bắt đầu bằng các nút hiện có.
- Lịch đã được nhận vẫn có thể sửa nếu phiên trước được cộng thêm thời gian. Phép này chỉ giữ phạm vi giường/phòng đã đặt, không cho mở rộng sang giường đang có lịch chờ khác.
- Người đang phục vụ vẫn sửa hoặc hoàn tất dịch vụ được khi phía sau có lịch chờ; lịch chờ không bị xóa hay tính tua sớm.
- Thao tác cả phòng và hàng loạt giữ tính nguyên tử; revision và idempotency vẫn kiểm tra trên server. Một thiết bị không thể dựa vào danh sách cũ để đặt đè lịch vừa được thiết bị khác giữ.
- Dữ liệu tình trạng phòng phục vụ bộ lọc lấy từ mọi phiên đang mở, kể cả dòng ẩn hoặc ngoài danh sách nhân viên hiện tại; chỉ trả cho người có quyền vận hành và không chứa danh tính khách hàng. Không đổi schema hoặc thêm kết nối Excel/Google Sheets.

## Thao tác trên thẻ phòng

- **Bấm một lần:** xem danh sách nhân viên của phòng.
- **Bấm đúp:** mở booking nếu có quyền vận hành và không đang gửi thao tác khác.
- Phần chi tiết phòng cũng có nút **Đặt lịch** để dùng bằng bàn phím hoặc trên màn hình cảm ứng. Nút Thực hiện/Hoàn thành giữ nguyên chức năng.

## Kiểm tra

Các trường hợp mới kiểm tra ranh giới 30 phút/29 phút 59 giây, hết giờ, thời lượng chưa biết, giường đang chờ, khóa PR toàn phòng, nhiều phiên trong phòng, lịch chờ và cộng giờ, chống đặt trùng, quyền dữ liệu phòng, bộ lọc frontend và hành vi bấm đơn/bấm đúp.

```sh
python -m pytest -q tests/test_live_tour*.py tests/test_spa_management.py tests/test_service_catalog.py tests/test_global_open_new_tab.py tests/test_tour_room_availability.py tests/test_tour_leave_sync.py --tb=short
```

Kết quả: 309 test liên quan đạt, gồm 18 trường hợp mới. Frontend: `npm run lint` và `npm run build` tại `web-v2` thành công; còn 3 cảnh báo lint và cảnh báo chunk lớn có sẵn. Chưa nghiệm thu trực tiếp giao diện production; cần kiểm tra danh sách và thao tác phòng sau triển khai.

## Rà soát CI trước triển khai

- Toàn bộ `python -m pytest -q`: **556 test đạt** sau khi xử lý 7 lỗi tồn tại trên `main`.
- Sửa lỗi Đăng ký nghỉ: khi server đã lưu nhưng tải lại danh sách thất bại, giữ thông báo lưu thành công và thêm cảnh báo hướng dẫn bấm Làm mới, không ghi lại. Kiểm thử thực thi handler với lỗi ở từng API đọc, lưu thất bại và tải lại bình thường; giữ các lần đọc tuần tự và chỉ gửi một lần tạo lịch.
- Bốn kiểm thử đăng nhập được cập nhật theo gateway hiện tại: xác minh tài khoản PostgreSQL rồi đổi token Supabase tại server. Mock đúng ranh giới database/HTTP; vẫn kiểm tra từ chối sai mật khẩu, không lộ mật khẩu tạm, hồ sơ đã xác minh và cache token. Không sửa mã đăng nhập production.
- Kiểm thử TimeSoft kiểm tra entrypoint gọi đồng bộ thay vì cố định chuỗi phiên bản. Kiểm thử phân loại Vi phạm dùng cùng hàm chuẩn hóa tiếng Việt với hệ thống.
- Ba điều kiện CI cũ được cập nhật: CCCD được xác minh trong các API lưu hồ sơ; nhân viên tự sửa dùng danh sách lý do đúng ngày của từng dòng; nguồn payroll TimeSoft kiểm tra dataset và ngày thiếu thay vì nhãn release. Giữ nguyên các bước CI bắt buộc và cấu hình triển khai.
- Lint/build giao diện vẫn đạt; các cảnh báo đã ghi ở trên còn tồn tại. Chưa merge/deploy hoặc nghiệm thu production.
