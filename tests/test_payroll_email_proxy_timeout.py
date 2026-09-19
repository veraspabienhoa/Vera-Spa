from pathlib import Path


def test_payroll_smtp_connect_timeout_is_bounded_below_proxy_timeout():
    backend = Path("vera_web_v2_payroll.py").read_text(encoding="utf-8")

    assert 'smtplib.SMTP("smtp.gmail.com", 587, timeout=8)' in backend
    assert 'smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=8)' in backend


def test_ktv_payroll_email_is_sent_in_small_non_retrying_batches():
    page = Path("web-v2/src/pages/PayrollPageEnhanced.jsx").read_text(encoding="utf-8")

    assert "const batchSize = 3" in page
    assert "for (let offset = 0; offset < rows.length; offset += batchSize)" in page
    assert "rows: chunk" in page
    assert "không tự thử lại để tránh gửi email trùng" in page
    assert "setEmailProgress({ processed:" in page
    assert "Đang gửi ${emailProgress.processed}/${emailProgress.total}…" in page


def test_legacy_payroll_email_uses_same_batched_transport():
    page = Path("web-v2/src/pages/PayrollPage.jsx").read_text(encoding="utf-8")

    assert "const batchSize = 3" in page
    assert "rows: chunk" in page
    assert "không tự thử lại để tránh gửi email trùng" in page