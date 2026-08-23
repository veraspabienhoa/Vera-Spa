# VERA SPA ĐỒNG NAI

Frontend mới chạy **song song** với Streamlit hiện tại. Mục tiêu là chuyển từng module, bắt đầu với `📅 Đăng ký nghỉ`, mà không làm gián đoạn người dùng production.

## Kiến trúc

- React + Vite: giao diện web/mobile.
- Supabase Auth: phiên đăng nhập Web V2.
- Supabase/PostgreSQL: database canonical hiện có.
- Python API: mọi thao tác nghiệp vụ nhạy cảm (đăng ký/sửa/xóa nghỉ, tính phép/phạt, record_uid, log, mirror Google Sheets).
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
- `VITE_VERA_DEMO_MODE=1`: chỉ dùng phát triển giao diện local.

## Nguyên tắc dữ liệu

Frontend không UPDATE/DELETE trực tiếp `leave_records`. Các write phải đi qua Python API để giữ nguyên business rules hiện tại, đặc biệt `record_uid`, phép năm, Nội quy/phạt, audit log và Google Sheet mirror.

## GitHub Pages

Workflow `.github/workflows/vera-web-v2-pages.yml` build `web-v2` và deploy artifact lên Pages. Lần đầu cần vào repository **Settings → Pages → Build and deployment → Source: GitHub Actions**.

Sau khi Pages được bật, site dự kiến ở:

`https://veraspabienhoa.github.io/Vera-Spa/`

Các config public của frontend có thể đặt bằng GitHub repository Variables:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_VERA_API_BASE_URL`

Không dùng GitHub Pages để chứa secret server-side.

## Kích hoạt bản pilot trên `main`

1. Chạy `supabase_web_v2_pilot_hardening.sql`, `supabase_web_v2_penalty_permission_default.sql` và `supabase_web_v2_daily_stats.sql` một lần trong Supabase SQL Editor.
2. Đảm bảo Cloud Run đã triển khai service `vera-spa-api` từ `cloudbuild.yaml`.
3. Có thể mở **Settings → Secrets and variables → Actions → Variables** để ghi đè các giá trị public mặc định:
   - `VITE_SUPABASE_URL`: URL project Supabase.
   - `VITE_SUPABASE_ANON_KEY`: publishable/anon key dùng cho browser.
   - `VITE_VERA_API_BASE_URL`: URL của Cloud Run service `vera-spa-api`.
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
