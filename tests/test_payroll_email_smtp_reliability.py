from pathlib import Path


def test_payroll_email_smtp_trims_secret_and_falls_back_between_gmail_ports():
    payroll = Path("vera_web_v2_payroll.py").read_text(encoding="utf-8")

    assert "def _open_payroll_smtp(sender: str, password: str):" in payroll
    assert 'secret = str(password or "").strip()' in payroll
    assert 'smtplib.SMTP("smtp.gmail.com", 587, timeout=8)' in payroll
    assert "smtp.starttls()" in payroll
    assert 'smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=8)' in payroll
    assert "smtp.login(username, secret)" in payroll
    assert "Gmail từ chối đăng nhập SMTP" in payroll


def test_ktv_payroll_email_uses_resilient_smtp_helper():
    payroll = Path("vera_web_v2_payroll.py").read_text(encoding="utf-8")

    assert 'password = str(os.getenv("SMTP_APP_PASSWORD", "") or "").strip()' in payroll
    assert "smtp = _open_payroll_smtp(sender, password)" in payroll
    assert "Không kết nối/xác thực được Gmail để gửi bảng lương" in payroll


def test_department_payroll_reuses_same_smtp_transport():
    department = Path("vera_web_v2_department_payroll.py").read_text(encoding="utf-8")

    assert 'password = str(os.getenv("SMTP_APP_PASSWORD", "") or "").strip()' in department
    assert "smtp = payroll._open_payroll_smtp(sender, password)" in department
    assert "Không kết nối/xác thực được Gmail để gửi bảng lương" in department
