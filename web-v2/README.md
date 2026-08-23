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
