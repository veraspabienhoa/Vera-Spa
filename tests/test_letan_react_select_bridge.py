from pathlib import Path


def test_letan_three_choice_proxy_updates_react_controlled_select():
    source = (
        Path(__file__).resolve().parents[1]
        / "web-v2/src/pages/LeaveListTypeColumn.jsx"
    ).read_text(encoding="utf-8")

    bridge = source.split("const setReactSelectValue", 1)[1].split(
        "const ensureLetanThreeChoiceProxy", 1
    )[0]
    proxy_change = source.split("proxy.addEventListener('change'", 1)[1].split(
        "proxy.replaceChildren", 1
    )[0]

    assert "window.HTMLSelectElement.prototype" in bridge
    assert "nativeSetter.call(select, value)" in bridge
    assert "new Event('input', { bubbles: true })" in bridge
    assert "new Event('change', { bubbles: true })" in bridge
    assert "setReactSelectValue(select, nativeOption.value)" in proxy_change
    assert "select.value = nativeOption.value" not in proxy_change
