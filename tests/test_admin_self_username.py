from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_profile_exposes_self_username_rename():
    page = (ROOT / "web-v2/src/pages/ProfilePage.jsx").read_text(encoding="utf-8")
    api = (ROOT / "web-v2/src/lib/api.js").read_text(encoding="utf-8")

    assert "ĐỔI TÊN ĐĂNG NHẬP ADMIN" in page
    assert "user?.role === 'admin'" in page
    assert "veraApi.renameSystemName(currentUsername, nextUsername)" in page
    assert "window.setTimeout(onPasswordChanged, 1500)" in page
    assert "renameSystemName: (username, systemName)" in api
    assert "/system-name`" in api


def test_existing_backend_preserves_auth_identity_and_references():
    backend = (ROOT / "vera_web_v2_system_name.py").read_text(encoding="utf-8")
    login = (ROOT / "supabase/functions/vera-v2-login/index.ts").read_text(encoding="utf-8")

    assert "Chỉ Admin được đổi Tên hệ thống/Tên đăng nhập" in backend
    assert "ON UPDATE CASCADE" in backend
    assert '"leave_records"' in backend
    assert '"vera_v2_push_subscription"' in backend
    assert "Username renames keep the same auth_user_id" in login
