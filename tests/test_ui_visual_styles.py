import pytest
from pydantic import ValidationError
from vera_web_v2_ui_layout import LayoutItem, validate_items, REGISTRY


def test_visual_settings_roundtrip_with_layout():
    key = next(key for key, item in REGISTRY.items() if item.get('label') and not item.get('locked'))
    item = LayoutItem(width=180, appearance={'normal': {'background': '#ffffff', 'shadow': 'raised'}, 'depth': 3, 'hover_lift': 2})
    result = validate_items({key: item})[key]
    assert result['width'] == 180
    assert result['appearance']['normal']['background'] == '#ffffff'
    assert result['appearance']['depth'] == 3


@pytest.mark.parametrize('appearance', [
    {'normal': {'background': 'red;display:none'}},
    {'hover': {'shadow': 'url(https://bad)'}},
    {'radius': -1}, {'glass_blur': 21}, {'hover_lift': 7},
    {'font_family': 'arbitrary'}, {'transition_ms': 9999},
])
def test_visual_settings_reject_unsafe_or_unbounded_values(appearance):
    with pytest.raises(ValidationError):
        LayoutItem(appearance=appearance)
