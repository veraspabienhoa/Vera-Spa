from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_profile_header_save_delegates_to_the_real_react_button():
    source = (ROOT / "web-v2/src/lib/employeeProfileHeaderSaveFix.js").read_text(encoding="utf-8")
    main = (ROOT / "web-v2/src/main.jsx").read_text(encoding="utf-8")

    assert ".vera-profile-save-top" in source
    assert "event.stopImmediatePropagation()" in source
    assert "saveButton.click()" in source
    assert "startEmployeeProfileHeaderSaveFix()" in main


def test_cccd_button_opens_a_separate_window_and_uses_new_label():
    source = (ROOT / "web-v2/src/lib/employeeCccdTabViewer.js").read_text(encoding="utf-8")

    assert "Mở CCCD trong Window mới" in source
    assert "popup=yes,width=1280,height=900" in source
    assert "Trình duyệt đang chặn Window mới" in source
