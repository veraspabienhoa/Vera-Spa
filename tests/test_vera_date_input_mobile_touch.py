from pathlib import Path


def test_all_devices_keep_manual_text_and_native_calendar_hit_target():
    css = Path("web-v2/src/styles.css").read_text(encoding="utf-8")
    component = Path("web-v2/src/components/VeraDateInput.jsx").read_text(encoding="utf-8")

    assert '.vera-date-input > .vera-native-date-picker' in css
    assert 'pointer-events: auto;' in css
    assert '.vera-date-input > .vera-date-picker-button { pointer-events: none; }' in css
    assert 'type="text"' in component
    assert 'onChange={changeText}' in component
    assert 'className="vera-native-date-picker"' in component
    assert 'type="date"' in component
    assert 'onChange={pickDate}' in component
    assert 'showPicker' not in component


def test_vera_date_input_native_picker_exists_from_first_render():
    component = Path("web-v2/src/components/VeraDateInput.jsx").read_text(encoding="utf-8")
    assert "pickerReady" not in component
    assert "flushSync" not in component
