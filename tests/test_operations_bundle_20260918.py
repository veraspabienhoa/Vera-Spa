from pathlib import Path

from vera_leave_registration_shared import count_unique_leave_people, quota_group
from vera_web_v2_profile import _secure_text_equal


ROOT = Path(__file__).resolve().parents[1]


def test_special_paid_reasons_stay_visible_but_are_exempt_from_daily_quota():
    rows = [
        {"employee_name": "Normal", "leave_reason": "Nghỉ CÓ phép", "leave_type": "CÓ phép", "calculated_days": 1},
        {"employee_name": "Leader", "leave_reason": "Leader nghỉ phép theo chính sách", "leave_type": "Leader", "calculated_days": 1},
        {"employee_name": "Approved", "leave_reason": "Nghỉ bệnh có giấy khám hoặc được quản lý duyệt", "leave_type": "Được duyệt", "calculated_days": 1},
        {"employee_name": "Bereavement", "leave_reason": "Nghỉ đám hiếu", "leave_type": "CÓ phép", "calculated_days": 1},
        {"employee_name": "Video", "leave_reason": "Nghỉ phép quay video", "leave_type": "CÓ phép", "calculated_days": 1},
    ]

    assert quota_group("Leader nghỉ phép theo chính sách", "Leader") == ""
    assert quota_group("Nghỉ bệnh có giấy khám hoặc được quản lý duyệt", "Được duyệt") == ""
    assert quota_group("Nghỉ đám hiếu", "CÓ phép") == ""
    assert quota_group("Nghỉ phép quay video", "CÓ phép") == ""

    stats = count_unique_leave_people(rows)
    assert stats["total_leave"] == 5
    assert stats["paid"] == 1


def test_profile_password_compare_supports_non_ascii_text():
    assert _secure_text_equal("MậtKhẩuĐẹp123!", "MậtKhẩuĐẹp123!") is True
    assert _secure_text_equal("MậtKhẩuĐẹp123!", "MậtKhẩuKhác123!") is False


def test_requested_frontend_wiring_is_present():
    appearance = (ROOT / "web-v2/src/lib/liveTourAppearance.js").read_text(encoding="utf-8")
    appearance_page = (ROOT / "web-v2/src/pages/AppearanceSettingsPage.jsx").read_text(encoding="utf-8")
    reports = (ROOT / "web-v2/src/pages/LiveTourReportsPage.jsx").read_text(encoding="utf-8")
    live_tour = (ROOT / "web-v2/src/pages/LiveTourPage.jsx").read_text(encoding="utf-8")
    clipboard = (ROOT / "web-v2/src/lib/clipboardImage.js").read_text(encoding="utf-8")
    breakdown = (ROOT / "web-v2/src/components/LiveTourEmployeeRevenueBreakdown.jsx").read_text(encoding="utf-8")

    assert "desktop: mergeDevice(raw?.desktop, 1000)" in appearance
    assert "mobile: mergeDevice(raw?.mobile, 260)" in appearance
    assert "max={device === 'desktop' ? 1000 : 260}" in appearance_page

    assert "defaultTourYesterdayFilters" in reports
    assert "preset: 'yesterday'" in live_tour and "panel === 'reports'" in live_tour

    assert "LiveTourEmployeeRevenueBreakdown" in reports
    assert "Chụp biểu đồ" in breakdown
    assert "Chụp toàn bộ section & copy" not in breakdown
    assert "Biểu đồ dịch vụ theo nhân viên" in breakdown
    assert "Biểu đồ tiền TIP theo nhân viên" in breakdown
    assert "elementToPngBlob" in clipboard
