"""Force TimeSoft to recalculate attendance before VERA reads check-in data.

The TimeSoft ReportEmployeeCheckIn page can expose incomplete summary rows until
its "Tính lại ngày công" action has run.  Both the frequent snapshot job and the
daily Auto Check job already authenticate with Playwright, so this patch performs
the same UI action an operator would perform before cookies are converted to the
requests session used by SearchElastic.

Fail closed by default: if the recalculation control cannot be found/clicked,
do not ingest potentially stale check-in data.  Set TIMESOFT_REQUIRE_RECALCULATE=0
only for emergency rollback.
"""
from __future__ import annotations

from datetime import datetime
import os
import re
from urllib.parse import urljoin


RELEASE = "timesoft-recalculate-checkin-2026-08-31-v1"


def _truthy(value: str, default: bool = True) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _today_range(ts) -> str:
    today = datetime.now(ts.VN_TZ).date().strftime("%d/%m/%Y")
    return f"{today} - {today}"


def _set_today_range_if_present(ts, page) -> bool:
    """Best-effort set the visible report date range to today.

    TimeSoft normally opens this report on today's range already.  This helper
    only changes an input that visibly contains a dd/mm/yyyy - dd/mm/yyyy range;
    it deliberately ignores ordinary text/search fields.
    """
    wanted = _today_range(ts)
    date_range_re = re.compile(
        r"\b\d{1,2}/\d{1,2}/\d{4}\s*-\s*\d{1,2}/\d{1,2}/\d{4}\b"
    )
    try:
        inputs = page.locator("input")
        for index in range(min(inputs.count(), 40)):
            node = inputs.nth(index)
            try:
                if not node.is_visible():
                    continue
                value = str(node.input_value() or "").strip()
                placeholder = str(node.get_attribute("placeholder") or "").strip()
            except Exception:
                continue
            if not date_range_re.search(value) and not date_range_re.search(placeholder):
                continue
            try:
                node.click(timeout=3000)
                node.fill(wanted, timeout=4000)
            except Exception:
                try:
                    node.evaluate(
                        "(el, value) => { el.value = value; "
                        "el.dispatchEvent(new Event('input', {bubbles:true})); "
                        "el.dispatchEvent(new Event('change', {bubbles:true})); }",
                        wanted,
                    )
                except Exception:
                    continue
            try:
                node.press("Enter")
            except Exception:
                pass
            try:
                node.press("Tab")
            except Exception:
                pass
            page.wait_for_timeout(300)
            ts._log(f"TIMESOFT RECALC: phạm vi ngày {wanted}")
            return True
    except Exception:
        pass
    return False


def _visible_recalculate_control(page):
    selectors = [
        'button:has-text("Tính lại ngày công")',
        'a:has-text("Tính lại ngày công")',
        'input[type="button"][value*="Tính lại ngày công"]',
        'input[type="submit"][value*="Tính lại ngày công"]',
        'button:has-text("Tính lại công")',
        'a:has-text("Tính lại công")',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for index in range(min(loc.count(), 12)):
                node = loc.nth(index)
                if node.is_visible() and node.is_enabled():
                    return node
        except Exception:
            continue

    # Text fallback for TimeSoft themes that render the label inside nested spans.
    try:
        candidates = page.locator("button, a, input[type='button'], input[type='submit']")
        for index in range(min(candidates.count(), 100)):
            node = candidates.nth(index)
            try:
                if not node.is_visible() or not node.is_enabled():
                    continue
                label = str(node.inner_text() or node.get_attribute("value") or "").strip()
            except Exception:
                continue
            normalized = " ".join(label.lower().split())
            if "tính lại ngày công" in normalized or "tính lại công" in normalized:
                return node
    except Exception:
        pass
    return None


def _accept_dialog(dialog) -> None:
    try:
        dialog.accept()
    except Exception:
        try:
            dialog.dismiss()
        except Exception:
            pass


def _confirm_modal_if_present(page) -> None:
    selectors = [
        '.modal:visible button:has-text("Đồng ý")',
        '.modal:visible button:has-text("Xác nhận")',
        '.modal:visible button:has-text("OK")',
        '.modal:visible button:has-text("Có")',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for index in range(min(loc.count(), 6)):
                node = loc.nth(index)
                if node.is_visible() and node.is_enabled():
                    node.click(timeout=5000)
                    return
        except Exception:
            continue


def recalculate_today(ts, page) -> None:
    report_url = urljoin(ts.BASE_URL + "/", ts.REPORT_CHECKIN_PAGE.lstrip("/"))
    page.goto(report_url, wait_until="domcontentloaded", timeout=35000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(700)

    final_url = str(page.url or "")
    if "/user/login" in final_url.lower():
        raise RuntimeError("TimeSoft quay lại trang đăng nhập trước khi Tính lại ngày công.")

    _set_today_range_if_present(ts, page)
    control = _visible_recalculate_control(page)
    if control is None:
        raise RuntimeError("Không tìm thấy nút 'Tính lại ngày công' trên báo cáo check-in TimeSoft.")

    try:
        page.once("dialog", _accept_dialog)
    except Exception:
        pass

    ts._log("TIMESOFT RECALC: bắt đầu Tính lại ngày công trước khi đọc check-in")
    control.click(timeout=10000)
    page.wait_for_timeout(500)
    _confirm_modal_if_present(page)

    # The action is AJAX on current TimeSoft versions.  Do not read SearchElastic
    # until its network activity settles; then allow a short UI/model commit gap.
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        # Some pages keep background requests open forever. A bounded grace wait
        # still preserves the required click-before-read ordering.
        page.wait_for_timeout(5000)
    page.wait_for_timeout(1200)

    # Fail if TimeSoft exposes an obvious visible error after recalculation.
    try:
        error_text = str(ts._login_error_text(page) or "").strip()
    except Exception:
        error_text = ""
    if error_text and any(token in error_text.lower() for token in ("lỗi", "error", "thất bại", "failed")):
        raise RuntimeError(f"TimeSoft Tính lại ngày công báo lỗi: {error_text[:240]}")

    ts._log("TIMESOFT RECALC: hoàn tất; bắt đầu lấy dữ liệu check-in")


def install(ts) -> None:
    if getattr(ts, "_recalculate_checkin_patch_release", "") == RELEASE:
        return

    original_login = ts._login_with_playwright
    required = _truthy(os.getenv("TIMESOFT_REQUIRE_RECALCULATE", "1"), True)

    def login_with_recalculate(page, verify_url: str):
        ok, message = original_login(page, verify_url)
        if not ok:
            return ok, message
        try:
            recalculate_today(ts, page)
        except Exception as exc:
            if required:
                return False, f"Không Tính lại ngày công trước khi đồng bộ: {type(exc).__name__}: {exc}"
            ts._log(
                "TIMESOFT RECALC WARN (emergency bypass): "
                f"{type(exc).__name__}: {exc}"
            )
        return True, f"{message}; recalculate-checkin"

    ts._login_with_playwright = login_with_recalculate
    ts._recalculate_checkin_patch_release = RELEASE
