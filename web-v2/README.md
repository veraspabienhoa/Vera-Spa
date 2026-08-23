# VERA SPA Web V2

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

1. Chạy `supabase_web_v2_pilot_hardening.sql` một lần trong Supabase SQL Editor.
2. Đảm bảo Cloud Run đã triển khai service `vera-spa-api` từ `cloudbuild.yaml`.
3. Trong GitHub, mở **Settings → Secrets and variables → Actions → Variables** và tạo:
   - `VITE_SUPABASE_URL`: URL project Supabase.
   - `VITE_SUPABASE_ANON_KEY`: publishable/anon key dùng cho browser.
   - `VITE_VERA_API_BASE_URL`: URL của Cloud Run service `vera-spa-api`.
4. Mở **Settings → Pages → Build and deployment** và chọn **GitHub Actions**.
5. Commit các file Web V2 vào `main`. Workflow `Deploy VERA SPA Web V2` sẽ tự lint, build và deploy.

Workflow cố ý dừng nếu thiếu một trong ba biến public ở trên để tránh phát hành một bản chỉ đọc hoặc đăng nhập lỗi mà không có cảnh báo.

## Quyền và an toàn pilot

- Python API đọc quyền `leave`/`leave_create` và trạng thái khóa đăng ký trực tiếp từ PostgreSQL trước mỗi lần ghi.
- Nhân viên/Leader chỉ nhận chính tài khoản của mình trong danh sách đăng ký; Admin/Quản lý/Lễ tân nhận danh sách nhân sự đủ điều kiện.
- Tiền phạt trong danh sách ngày được che ở phía server với mọi vai trò ngoài Admin.
- Các RPC dự phòng chỉ cấp `EXECUTE` cho `authenticated` và `service_role`; `anon` bị thu hồi quyền.
- Tài khoản hệ thống `admin` không được cộng vào thống kê nhân viên đang làm việc.
