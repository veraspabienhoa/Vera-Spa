# VERA SPA

Frontend mới chạy **song song** với Streamlit hiện tại. Các module đã chuyển gồm `📅 Đăng ký nghỉ`, `👥 Nhân viên` và `📜 Nội quy`, không làm gián đoạn người dùng production.

## Kiến trúc

- React + Vite: giao diện web/mobile.
- Python API tại `https://api.veraspa.vn`: cổng đăng nhập chính và mọi thao tác nghiệp vụ nhạy cảm.
- Supabase Auth: phát hành phiên đăng nhập ở phía máy chủ; trình duyệt chỉ gọi trực tiếp như đường dự phòng khi API không kết nối được.
- Supabase/PostgreSQL: database canonical hiện có.
- GitHub Pages: frontend hosting miễn phí.

**Không** đưa service-role key, mật khẩu PostgreSQL, TimeSoft credential hoặc Google credential vào `VITE_*` vì mọi biến Vite đều xuất hiện trong browser bundle.

## Chạy local

```bash
cd web-v2
npm install
cp .env.example .env.local
npm run dev
```

## Build

```bash
npm run build
```

## Biến môi trường

- `VITE_SUPABASE_URL`: Project URL của Supabase.
- `VITE_SUPABASE_ANON_KEY`: public anon key, chỉ dùng với RLS/Auth đúng cấu hình.
- `VITE_VERA_API_BASE_URL`: URL Python API của VERA SPA.

## Nguyên tắc dữ liệu

Frontend không UPDATE/DELETE trực tiếp `leave_records`. Các write phải đi qua Python API để giữ nguyên business rules hiện tại, đặc biệt `record_uid`, phép năm, Nội quy/phạt, audit log và Google Sheet mirror.

Mục **Nhân viên** cũng chỉ ghi qua Python API. Màn hình này tập trung danh sách hồ sơ, thêm/xóa nhân viên, trạng thái làm việc, khóa đăng nhập và phân ca. Export `.xlsx` không chứa mật khẩu/token; Import `.xlsx` chỉ cập nhật tài khoản đã tồn tại và kiểm tra toàn bộ file trước khi ghi.

Mục **Nội quy** giữ toàn bộ cột/dòng động của bảng `LoaiNghi`. PostgreSQL `official_policy/leave_rules` là dữ liệu chính thức; một lần ghi chỉ thành công khi kiểm tra hợp lệ, đúng phiên bản và đồng bộ được worksheet `LoaiNghi`. Chỉ Admin/Quản lý mặc định được sửa hoặc Import; các vai trò còn lại chỉ xem và Export, trừ khi được cấu hình khác tại Phân quyền.

## Web production — xác minh ngày 26-09-2026

`app.veraspa.vn` hiện phục vụ giao diện được build trong **Deploy VPS Production**.
Log lần chạy #545 build `index-COQl75VV.js` tại commit `745a460`; trình duyệt mới
vẫn nhận chính entry này lúc 15:32 dù Pages đã triển khai commit `f8461efd`.
Vì vậy, sửa giao diện cũng cần chạy Deploy VPS Production cho đúng commit main.
Không kết luận trang thật đã cập nhật chỉ từ workflow GitHub Pages thành công.

Vite xuất `build-info.json` chỉ chứa commit nguồn và tên entry script. Cuối
Deploy VPS Production, `vera_web_release_check.py` đối chiếu commit này với
commit yêu cầu và entry trong HTML của cả URL gốc lẫn URL tải mới. Nếu khác,
workflow báo lỗi để kiểm tra origin/cache; không tự thay DNS hoặc bỏ xác thực.
Kiểm tra này xác minh phiên bản, không thay thế kiểm thử đăng nhập và nghiệp vụ.

### Bản build GitHub Pages

Workflow `.github/workflows/vera-web-v2-pages.yml` vẫn build `web-v2` và deploy artifact lên Pages. Kết quả này không xác minh frontend mà domain production đang phục vụ.

Địa chỉ duy nhất dành cho người dùng là custom domain:

`https://app.veraspa.vn/`

File `public/CNAME` giữ custom domain này trong artifact Pages. Không công bố
đường dẫn Pages theo tên repository làm địa chỉ truy cập cho người dùng.

Các config public của frontend có thể đặt bằng GitHub repository Variables:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_VERA_API_BASE_URL`

Không dùng GitHub Pages để chứa secret server-side.

Web V2 không có đường đăng nhập Demo hoặc chế độ bỏ qua xác thực. Đăng nhập ưu tiên `api.veraspa.vn`; mọi trang nghiệp vụ chỉ hiển thị sau khi API xác minh phiên Supabase và hồ sơ VERA đang hoạt động.

## Kích hoạt bản pilot trên `main`

1. Chạy `supabase_web_v2_pilot_hardening.sql`, `supabase_web_v2_penalty_permission_default.sql` và `supabase_web_v2_daily_stats.sql` một lần trong Supabase SQL Editor.
2. Đảm bảo Cloud Run đã triển khai service `vera-spa-api` từ `cloudbuild.yaml`.
3. Có thể mở **Settings → Secrets and variables → Actions → Variables** để ghi đè các giá trị public mặc định:
   - `VITE_SUPABASE_URL`: URL project Supabase.
   - `VITE_SUPABASE_ANON_KEY`: publishable/anon key dùng cho browser.
   - `VITE_VERA_API_BASE_URL`: `https://api.veraspa.vn`.
4. Mở **Settings → Pages → Build and deployment** và chọn **GitHub Actions**.
5. Commit các file Web V2 vào `main`. Workflow `Deploy VERA SPA Web V2` sẽ tự lint, build và deploy.

Workflow có sẵn các giá trị public production của VERA; repository Variables chỉ dùng khi cần đổi project/API mà không sửa workflow.

## Quyền và an toàn pilot

- Python API đọc quyền `leave`/`leave_create` và trạng thái khóa đăng ký trực tiếp từ PostgreSQL trước mỗi lần ghi.
- Mọi tài khoản ngoài Admin chỉ nhận và đăng ký lịch nghỉ cho chính tài khoản đang đăng nhập; Admin được chọn nhân viên khác.
- Quyền `employee_penalty_view` (`💰 Lịch nghỉ · Xem tiền phạt vi phạm`) được quản lý tại **Phân quyền chức năng**. Admin luôn có quyền; các vai trò/tài khoản khác mặc định không có và chỉ thấy khi Admin chủ động cấp.
- `supabase_web_v2_penalty_permission_default.sql` là baseline một lần để thu hồi các cấp quyền xem tiền phạt cũ trước khi áp dụng mặc định Admin-only.
- Ngày hiển thị trong Web V2 dùng định dạng `dd/mm/yyyy`.
- Bộ lọc thống kê hỗ trợ Hôm qua/Hôm nay/Tuần này/Tuần sau/Tháng này/Tháng sau/Tùy chỉnh. Bảng theo ngày lấy trực tiếp từ PostgreSQL và dùng cấu hình `leave_rules/daily_quota` để cảnh báo khi Có phép hoặc Phát sinh đã đủ hạn mức.
- Các RPC dự phòng chỉ cấp `EXECUTE` cho `authenticated` và `service_role`; `anon` bị thu hồi quyền.
- Tài khoản hệ thống `admin` không được cộng vào thống kê nhân viên đang làm việc.
