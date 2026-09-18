from pathlib import Path


def test_mobile_revenue_summary_is_two_by_two_and_does_not_ellipsis_amounts():
    css = Path("web-v2/src/components/LiveTourRevenueSummary.css").read_text(encoding="utf-8")

    mobile = css.split("@media(max-width:650px){", 1)[1]
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in mobile
    assert "white-space:nowrap;overflow:visible;text-overflow:clip" in mobile
    assert "font-size:clamp(16px,4.8vw,22px)" in mobile
