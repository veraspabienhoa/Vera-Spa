from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_successful_leave_create_is_not_reclassified_when_refresh_fails():
    source = (ROOT / "web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")

    assert "const afterSuccessfulCreate = options?.afterSuccessfulCreate === true" in source
    assert "if (!afterSuccessfulCreate) setError('')" in source
    assert "Lịch nghỉ đã được lưu, nhưng chưa thể làm mới dữ liệu hiển thị" in source
    assert "await load({ afterSuccessfulCreate: true })" in source

    success = source.index("setMessage('Đã ghi lịch nghỉ THÀNH CÔNG')")
    refresh = source.index("await load({ afterSuccessfulCreate: true })", success)
    assert success < refresh
