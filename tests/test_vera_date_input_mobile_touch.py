from pathlib import Path


def test_touch_devices_use_real_native_date_input_as_full_field_hit_target():
    css = Path("web-v2/src/styles.css").read_text(encoding="utf-8")

    assert "@media (hover: none) and (pointer: coarse)" in css
    assert ".vera-date-input:not(:has(.vera-date-picker-button:disabled)) > .vera-native-date-picker" in css
    assert "width: 100% !important;" in css
    assert "height: 100% !important;" in css
    assert ".vera-date-input > .vera-date-picker-button" in css
    assert "pointer-events: none;" in css


def test_vera_date_input_keeps_native_date_control_for_ios_picker():
    component = Path("web-v2/src/components/VeraDateInput.jsx").read_text(encoding="utf-8")

    assert 'className="vera-native-date-picker"' in component
    assert 'type="date"' in component
    assert "onChange={pickDate}" in component
