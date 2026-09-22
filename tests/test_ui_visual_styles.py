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


def test_custom_elements_validate_and_keep_plain_text():
    from fastapi import HTTPException
    item=LayoutItem(custom_kind='text',custom_text='<script>plain text only</script>',custom_page='settings')
    assert validate_items({'l-custom-demo':item})['l-custom-demo']['custom_text'].startswith('<script>')
    with pytest.raises(HTTPException): validate_items({'l-other':item})
    with pytest.raises(HTTPException): validate_items({'l-custom-demo':LayoutItem(custom_kind='box')})
    with pytest.raises(HTTPException): validate_items({'l-custom-demo':LayoutItem(custom_kind='box',custom_page='settings',custom_anchor='l-custom-demo')})
    locked=next(key for key,value in REGISTRY.items() if value.get('locked'))
    with pytest.raises(HTTPException): validate_items({locked:LayoutItem(hidden=True)})
    assert validate_items({'l-title':LayoutItem(hidden=True)})['l-title']['hidden'] is True


def test_unbounded_finite_font_sizes_and_italic_round_trip():
    from vera_web_v2_ui_layout import LayoutItem
    from pydantic import ValidationError
    import pytest
    for size in (0, 0.5, 8, 96, 4096):
        item = LayoutItem(font_size=size, appearance={"font_size": size, "font_style": "italic", "font_weight": 700})
        restored = LayoutItem.model_validate_json(item.model_dump_json())
        assert restored.font_size == size
        assert restored.appearance.font_size == size
        assert restored.appearance.font_style == "italic"
    for size in (-1, float("inf"), float("nan")):
        with pytest.raises(ValidationError):
            LayoutItem(font_size=size)
        with pytest.raises(ValidationError):
            LayoutItem(appearance={"font_size": size})
