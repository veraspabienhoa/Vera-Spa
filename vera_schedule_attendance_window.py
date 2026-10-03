"""VERA schedule attendance window, including earlier/later overtime."""
from datetime import time


def attendance_window(row):
    start, end = str(row.get("start_time") or ""), str(row.get("end_time") or "")
    if str(row.get("shift_code") or "").strip().casefold() in {"", "nghỉ", "nghi"}:
        return "", ""
    overtime = str(row.get("overtime_shift") or "")
    left, right = str(row.get("overtime_start_time") or ""), str(row.get("overtime_end_time") or "")
    if not overtime or not left or not right:
        return start, end
    def minutes(value):
        clock = time.fromisoformat(value)
        return clock.hour * 60 + clock.minute
    try:
        a, b, c, d = map(minutes, (start, end, left, right))
    except ValueError:
        return start, end
    if b <= a:
        b += 1440
    if d <= c:
        d += 1440
    if overtime == "Từ giờ tới giờ":
        # Custom after-midnight extensions follow an overnight main shift.
        # Named Ca 1/2 always start on the schedule date.
        offset = 1440 if b >= 1440 and c <= b % 1440 and d <= a else 0
        c, d = c+offset, d+offset
    a, b = min(a, c), max(b, d)
    if b-a >= 1440:
        return start, end  # Downstream clock-only fields cannot express >=24h.
    def clock(value):
        value %= 1440
        return f"{value//60:02d}:{value%60:02d}"
    return clock(a), clock(b)
