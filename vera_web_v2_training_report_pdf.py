"""A4 card template for the PDF export; the existing PNG model stays separate.

Drawing coordinates are points measured from the top of each A4 page. Every
text field is wrapped before layout, and journal/history continuations get new
cards rather than stretching a screenshot or clipping a fixed-height box.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import time
import math

import vera_web_v2_training_report_export as shared

MARGIN = 24.0
TOP = 20.0
BOTTOM = shared.PAGE_HEIGHT - 27.0
WIDTH = shared.PAGE_WIDTH - 2 * MARGIN
INSET = 14.0
X = MARGIN + INSET
CONTENT_WIDTH = WIDTH - 2 * INSET
GOLD_WASH = "#fff2bd"
CARD_BORDER = "#dae4d9"
HISTORY_BLUE = "#eef6ff"
HISTORY_BORDER = "#b9d4f0"
HISTORY_ACCENT = "#2b75ad"
EVALUATION_GOLD = "#fff7df"
EVALUATION_BORDER = "#e5d19f"
PLACEHOLDER = "#f4f6f5"
BODY_SIZE = 7.4
LEADING = 11.1
TITLE_SIZE = 11.4


def _lines(value, width=CONTENT_WIDTH, *, size=BODY_SIZE, bold=False, color=shared.INK):
    return [(text, size, bold, color) for text in shared._wrap(value, width, size, bold)]


def _sort_date(value):
    # ISO dates are already normalized by the report DTO; keep ordering independent
    # of the visible dd-mm-yyyy presentation.
    return str(value or "")


def _clock(value):
    if not value:
        return "Chưa có"
    try:
        parsed = value if isinstance(value, time) else time.fromisoformat(str(value))
        return parsed.isoformat() if parsed.second or parsed.microsecond else parsed.strftime("%H:%M")
    except (TypeError, ValueError):
        return shared._text(value)


def _hours(item):
    try:
        start = item.get("start_time")
        end = item.get("end_time")
        start = start if isinstance(start, time) else time.fromisoformat(str(start))
        end = end if isinstance(end, time) else time.fromisoformat(str(end))
        seconds = ((end.hour - start.hour) * 3600 + (end.minute - start.minute) * 60
                   + end.second - start.second)
        return seconds / 3600 if seconds > 0 else None
    except (TypeError, ValueError):
        return None


def _number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _hours_text(items):
    values = [_hours(item) for item in items]
    known = [value for value in values if value is not None]
    if not known:
        return "Chưa có giờ"
    label = _number(sum(known)) + " giờ"
    missing = len(values) - len(known)
    return label + (f" · {missing} buổi chưa có giờ" if missing else "")


class _CardLayout:
    def __init__(self):
        self.pages = [[]]
        self.y = TOP
        self._card = None

    @property
    def commands(self):
        return self.pages[-1]

    def text(self, value, x, y, *, size=BODY_SIZE, bold=False, color=shared.INK, anchor="left"):
        self.commands.append(("text", shared._text(value, ""), x, y, size, bold, color, anchor))

    def rect(self, x, y, width, height, color):
        self.commands.append(("rect", x, y, width, height, color))

    def rounded(self, x, y, width, height, fill, border, radius=8):
        self.commands.append(("roundrect", x, y, width, height, radius, fill, border))

    def line(self, x1, y1, x2, y2, color=shared.GRID, width=.6):
        self.commands.append(("line", x1, y1, x2, y2, color, width))

    def circle(self, x, y, radius, color):
        self.commands.append(("circle", x, y, radius, color))

    def polygon(self, points, color, fill=None):
        self.commands.append(("polygon", points, color, fill))

    def new_page(self):
        assert self._card is None
        self.pages.append([])
        self.y = TOP

    def open(self, title, *, minimum=70):
        assert self._card is None
        if self.y + minimum > BOTTOM:
            self.new_page()
        self._card = (len(self.commands), self.y)
        self.y += 15
        # Even an unusually long display name can continue without clipping.
        for value, size, bold, color in _lines(title, size=TITLE_SIZE, bold=True, color=shared.GREEN):
            if self.y + 34 > BOTTOM:
                self.close()
                self.new_page()
                self._card = (len(self.commands), self.y)
                self.y += 15
            self.text(value, X, self.y, size=size, bold=bold, color=color)
            self.y += 16
        self.y += 7

    def close(self):
        assert self._card is not None
        index, start = self._card
        height = self.y + 11 - start
        self.commands[index:index] = [
            ("rect", MARGIN, start, WIDTH, height, GOLD_WASH),
            ("roundrect", MARGIN + 4, start + 3, WIDTH - 8, height - 6, 9, "#ffffff", CARD_BORDER),
        ]
        self.y = start + height + 8
        self._card = None

    def continuation(self, title):
        self.close()
        self.new_page()
        self.open(title)

    def paragraph(self, value, *, title, bold=False, color=shared.INK, size=BODY_SIZE, gap=3):
        for text, size, bold, color in _lines(value, size=size, bold=bold, color=color):
            if self.y + size * 1.5 + gap + 11 > BOTTOM:
                self.continuation(title)
            self.text(text, X, self.y, size=size, bold=bold, color=color)
            self.y += size * 1.5
        self.y += gap

    def finish(self):
        assert self._card is None
        for index, page in enumerate(self.pages, 1):
            page.append(("text", f"Trang {index}/{len(self.pages)}", shared.PAGE_WIDTH - MARGIN,
                         shared.PAGE_HEIGHT - 16, 6.5, False, shared.MUTED, "right"))
        return self.pages


def _journal(layout, report, progress):
    employee = report.get("employee") or {}
    name = (employee.get("full_name") or employee.get("display_name")
            or report.get("employee_username") or employee.get("username") or "Chưa có tên")
    title = "Nhật ký đào tạo · " + shared._text(name)
    continuation = "Nhật ký đào tạo (tiếp)"
    layout.open(title, minimum=110)
    groups = defaultdict(list)
    for item in sorted(progress, key=lambda row: (_sort_date(row.get("training_date")),
                       str(row.get("start_time") or ""), str(row.get("id") or "")), reverse=True):
        groups[_sort_date(item.get("training_date"))].append(item)
    layout.paragraph(f"{len(groups)} ngày · {len(progress)} buổi · {_hours_text(progress)}",
                     title=continuation, color=shared.MUTED, gap=3)
    scope = []
    start, end = report.get("date_from"), report.get("date_to")
    if start or end:
        scope.append(f"Khoảng: {shared._date(start) if start else 'Không giới hạn đầu'} đến "
                     f"{shared._date(end) if end else 'Không giới hạn cuối'}")
    filters = report.get("filters") or {}
    role = filters.get("evaluator_role")
    if role and role != "all":
        scope.append("Người đánh giá: " + shared.ROLE_LABELS.get(role, shared._text(role)))
    rating = filters.get("rating")
    if rating and rating != "all":
        scope.append("Xếp loại: " + shared.RATING_LABELS.get(rating, shared._text(rating)))
    if filters.get("q"):
        scope.append("Từ khóa: " + shared._text(filters["q"]))
    if scope:
        layout.paragraph(" · ".join(scope), title=continuation, size=7, color=shared.MUTED, gap=5)
    if not progress:
        layout.paragraph("Chưa có buổi đào tạo trong khoảng đã chọn.", title=continuation, color=shared.MUTED)
        layout.close()
        return
    widths = (CONTENT_WIDTH * .22, CONTENT_WIDTH * .18, CONTENT_WIDTH * .60)
    edges = (X, X + widths[0], X + widths[0] + widths[1], X + CONTENT_WIDTH)

    def header():
        if layout.y + 45 > BOTTOM - 11:
            layout.continuation(continuation)
        top = layout.y
        for column, heading in enumerate(("NGÀY", "GIỜ ĐÀO TẠO", "NỘI DUNG VÀ ĐÁNH GIÁ TỪNG BUỔI")):
            layout.text(heading, edges[column] + 5, top + 5, size=5.9, bold=True, color=shared.MUTED)
        for edge in edges:
            layout.line(edge, top, edge, top + 17, shared.GREEN)
        layout.line(X, top, edges[-1], top, shared.GREEN)
        layout.line(X, top + 17, edges[-1], top + 17, shared.GREEN)
        layout.y += 17

    header()
    for day, items in groups.items():
        content = []
        for index, item in enumerate(items):
            if index:
                content.extend(_lines("", widths[2] - 10))
            hours = _hours(item)
            label = f"{_clock(item.get('start_time'))}-{_clock(item.get('end_time'))} · "
            label += _number(hours) + " giờ" if hours is not None else "Chưa có giờ"
            content.extend(_lines(label, widths[2] - 10, bold=True))
            content.extend(_lines(f"{shared._text(item.get('topic'), 'Đào tạo hằng ngày')} · Người đào tạo: "
                                  f"{shared._text(item.get('trainer_name') or item.get('trainer_username') or item.get('evaluator_name'))}", widths[2] - 10))
            if item.get("evaluator_name") and item.get("evaluator_name") != (item.get("trainer_name") or item.get("trainer_username")):
                content.extend(_lines(f"Người đánh giá: {item['evaluator_name']}", widths[2] - 10))
            content.extend(_lines(f"Tay nghề: {shared._text(item.get('skill_grade'), 'Chưa có')} · "
                                  f"Tinh thần: {shared._text(item.get('learning_attitude'), 'Chưa có')}", widths[2] - 10))
            for key, label in (("strengths", "Điểm mạnh"), ("improvements", "Cần cải thiện"), ("notes", "Nhận xét")):
                content.extend(_lines(f"{label}: {shared._text(item.get(key), '—')}", widths[2] - 10))
        columns = [_lines(shared._date(day), widths[0] - 10),
                   _lines(_hours_text(items), widths[1] - 10, bold=True), content]
        total = max(map(len, columns))
        offset = 0
        while offset < total:
            available = math.floor((BOTTOM - 11 - layout.y - 11) / LEADING)
            # Keep a normal day together; only split a day larger than a full card.
            full_capacity = math.floor((BOTTOM - TOP - 38 - 17 - 22) / LEADING)
            if available < 2 or (offset == 0 and total <= full_capacity and total > available):
                layout.continuation(continuation)
                header()
                available = math.floor((BOTTOM - 11 - layout.y - 11) / LEADING)
            take = min(total - offset, available)
            height = take * LEADING + 11
            top = layout.y
            for col, lines in enumerate(columns):
                selected = lines[offset:offset + take]
                # Date/hours repeat on a continued row for context, without losing
                # any original lines when those fields themselves need wrapping.
                if offset and not selected and col < 2:
                    selected = lines[:take]
                for row, (value, size, bold, color) in enumerate(selected):
                    layout.text(value, edges[col] + 5, top + 5 + row * LEADING,
                                size=size, bold=bold, color=color)
            for edge in edges:
                layout.line(edge, top, edge, top + height, shared.GREEN)
            layout.line(X, top + height, edges[-1], top + height, shared.GREEN)
            layout.y += height
            offset += take
            if offset < total:
                layout.continuation(continuation)
                header()
    layout.close()


def _history_items(report):
    """Keep the complete supplied history and all source records, without duplicates."""
    result = [dict(item) for item in report.get("history") or []]
    for kind, key, day_key, title_key in (("daily", "progress", "training_date", "topic"),
                                          ("comprehensive", "evaluation_details", "end_date", "cycle_name")):
        lookup = {str(item.get("id")): item for item in report.get(key) or [] if item.get("id") is not None}
        present = set()
        for history in result:
            if history.get("type") != kind:
                continue
            identifier = str(history.get("id"))
            present.add(identifier)
            detail = dict(lookup.get(identifier) or {})
            detail.update(history.get("detail") or {})
            history["detail"] = detail
        for item in report.get(key) or []:
            if str(item.get("id")) not in present:
                result.append({"type": kind, "date": item.get(day_key), "id": item.get("id"),
                               "title": item.get(title_key), "evaluator_name": item.get("evaluator_name"), "detail": item})
    return sorted(result, key=lambda item: (_sort_date(item.get("date")), str(item.get("type") or ""),
                                           str(item.get("id") or "")), reverse=True)


def _history(layout, report):
    items = _history_items(report)
    continuation = "Lịch sử Đào tạo & Đánh giá (tiếp)"
    layout.open(f"Lịch sử Đào tạo & Đánh giá ({len(items)})", minimum=125)
    if not items:
        layout.paragraph("Chưa có lịch sử trong khoảng đã chọn.", title=continuation, color=shared.MUTED)
    date_width = 69.0
    body_x = X + date_width + 9
    body_width = CONTENT_WIDTH - date_width - 18
    for item in items:
        detail = item.get("detail") or {}
        daily = item.get("type") == "daily"
        category = "ĐÀO TẠO HẰNG NGÀY" if daily else "ĐÁNH GIÁ TỔNG HỢP"
        accent = HISTORY_ACCENT if daily else shared.GOLD
        lines = _lines(category, body_width, size=6.3, bold=True, color=accent)
        lines += _lines(shared._text(item.get("title")), body_width, bold=True)
        rating = item.get("rating_label") or shared.RATING_LABELS.get(item.get("rating"), "Chưa có")
        lines += _lines(f"Người thực hiện: {shared._text(item.get('evaluator_name') or detail.get('evaluator_name'))} · "
                        f"Xếp loại: {rating}", body_width)
        if daily:
            lines += _lines(f"Kỹ năng: {shared._text(detail.get('skill_grade'))} · "
                            f"Tinh thần: {shared._text(detail.get('learning_attitude'))}", body_width)
        else:
            if detail.get("cycle_name") and detail.get("cycle_name") != item.get("title"):
                lines += _lines(f"Đợt: {detail['cycle_name']}", body_width)
            lines += _lines(f"Thời gian: {shared._date(detail.get('start_date'))} đến {shared._date(detail.get('end_date') or item.get('date'))}", body_width)
            for key, label in shared.SCORE_FIELDS:
                lines += _lines(f"{label}: {shared._score_label(detail.get(key), 5)}", body_width)
        for key, label in (("strengths", "Điểm mạnh"), ("improvements", "Cần cải thiện"),
                           ("notes" if daily else "comments", "Nhận xét")):
            lines += _lines(f"{label}: {shared._text(detail.get(key), '—')}", body_width)
        date_lines = _lines(shared._date(item.get("date")), date_width - 12, bold=True, color=shared.GOLD)
        offset = 0
        while offset < max(len(lines), len(date_lines)):
            available = math.floor((BOTTOM - 11 - layout.y - 20) / LEADING)
            full_capacity = math.floor((BOTTOM - TOP - 38 - 31) / LEADING)
            remaining = max(len(lines), len(date_lines)) - offset
            if available < 3 or (offset == 0 and remaining <= full_capacity and remaining > available):
                layout.continuation(continuation)
                available = math.floor((BOTTOM - 11 - layout.y - 20) / LEADING)
            take = min(remaining, available)
            top = layout.y
            height = take * LEADING + 14
            layout.rounded(X, top, CONTENT_WIDTH, height, HISTORY_BLUE if daily else EVALUATION_GOLD,
                           HISTORY_BORDER if daily else EVALUATION_BORDER, 6)
            layout.line(X + 1, top + 6, X + 1, top + height - 6, accent, 2)
            if offset == 0:
                badge_width = shared._width(category, 6.3, True) + 6
                layout.rounded(body_x - 3, top + 6, badge_width, 10,
                               "#d9ecff" if daily else "#fae5a8",
                               "#d9ecff" if daily else "#fae5a8", 4)
            dates = date_lines[offset:offset + take] or date_lines[:take]
            for index, (value, size, bold, color) in enumerate(dates):
                layout.text(value, X + 8, top + 7 + index * LEADING, size=size, bold=bold, color=color)
            for index, (value, size, bold, color) in enumerate(lines[offset:offset + take]):
                layout.text(value, body_x, top + 7 + index * LEADING, size=size, bold=bold, color=color)
            layout.y += height + 6
            offset += take
            if offset < max(len(lines), len(date_lines)):
                layout.continuation(continuation)
    layout.close()


def _placeholder(layout, text, x, y, width):
    lines = _lines(text, width - 20, size=7.3, color=shared.MUTED)
    height = max(40, len(lines) * 11 + 16)
    layout.rounded(x, y, width, height, PLACEHOLDER, PLACEHOLDER, 6)
    for index, (value, size, bold, color) in enumerate(lines):
        layout.text(value, x + width / 2, y + (height - len(lines) * 11) / 2 + index * 11,
                    size=size, bold=bold, color=color, anchor="center")


def _plot(layout, items, x, y, width, *, skill):
    series = (("skill_score", "Tay nghề", shared.GOLD),) if skill else shared.DETAIL_SERIES
    maximum = 6 if skill else 5
    left, right = x + 17, x + width - 5
    top, bottom = y + 8, y + (78 if skill else 100)
    for value in range(1, maximum + 1):
        point_y = bottom - (value - 1) / (maximum - 1) * (bottom - top)
        layout.line(left, point_y, right, point_y)
        label = ("E", "D", "C", "B", "A", "A+")[value - 1] if skill else str(value)
        layout.text(label, left - 9, point_y - 3, size=5.9, color=shared.MUTED, anchor="right")
    xs = [left + (right - left) * i / (len(items) - 1) if len(items) > 1 else (left + right) / 2 for i in range(len(items))]
    for key, _, color in series:
        previous = None
        for point_x, item in zip(xs, items):
            value = shared._score(item.get(key), maximum)
            if value is None:
                previous = None
                continue
            point_y = bottom - (value - 1) / (maximum - 1) * (bottom - top)
            if previous is not None:
                layout.line(*previous, point_x, point_y, color, 1.4)
            layout.circle(point_x, point_y, 1.9, shared.GREEN if skill else color)
            previous = point_x, point_y
    ticks = min(3 if skill else 5, len(items))
    indices = sorted({round(index * (len(items) - 1) / max(1, ticks - 1)) for index in range(ticks)})
    for index in indices:
        value = shared._date(items[index].get("training_date" if skill else "end_date"))
        # Tick labels have separate lanes; malformed/long date data wraps too.
        lane = (right - left) / max(1, ticks - 1) if ticks > 1 else width - 20
        labels = shared._wrap(value, min(lane - 3, 85), 5.7)
        anchor = "left" if index == 0 and len(items) > 1 else "right" if index == len(items) - 1 and len(items) > 1 else "center"
        for row, label in enumerate(labels):
            layout.text(label, xs[index], bottom + 7 + row * 8, size=5.7, color=shared.MUTED, anchor=anchor)
    if not skill:
        for index, (_, label, color) in enumerate(series):
            legend_x = x + (index % 4) * width / 4
            legend_y = bottom + 25 + (index // 4) * 14
            layout.line(legend_x, legend_y + 5, legend_x + 11, legend_y + 5, color, 1.7)
            layout.text(label, legend_x + 16, legend_y, size=7)


def _radar(layout, item, x, y, width):
    if not item or all(shared._score(item.get(key), 5) is None for key, _, _ in shared.SERIES):
        _placeholder(layout, "Chưa có đủ dữ liệu năng lực trong khoảng đã chọn.", x, y, width)
        return
    cx, cy, radius = x + width / 2, y + 65, 40
    axes = [(0, -1), (1, 0), (0, 1), (-1, 0)]
    for level in range(1, 6):
        ring = [(cx + ax * radius * level / 5, cy + ay * radius * level / 5) for ax, ay in axes]
        layout.polygon(ring, shared.GRID)
        layout.text(str(level), cx + 3, cy - radius * level / 5 - 3, size=5, color=shared.MUTED)
    points = []
    for (key, _, _), (ax, ay) in zip(shared.SERIES, axes):
        layout.line(cx, cy, cx + ax * radius, cy + ay * radius)
        value = shared._score(item.get(key), 5)
        points.append((cx + ax * radius * value / 5, cy + ay * radius * value / 5) if value is not None else None)
    if all(point is not None for point in points):
        layout.polygon(points, shared.GREEN)
    else:
        for index, point in enumerate(points):
            other = points[(index + 1) % len(points)]
            if point is not None and other is not None:
                layout.line(*point, *other, shared.GREEN, 1.4)
    for point in points:
        if point is not None:
            layout.circle(*point, 2.2, shared.GREEN)
    positions = [(cx, cy - radius - 22, "center"), (cx + radius + 8, cy - 8, "left"),
                 (cx, cy + radius + 5, "center"), (cx - radius - 8, cy - 8, "right")]
    for (key, label, _), (px, py, anchor) in zip(shared.SERIES, positions):
        layout.text(label, px, py, size=6.6, bold=True, anchor=anchor)
        layout.text(shared._score_label(item.get(key), 5), px, py + 10, size=6.5, color=shared.MUTED, anchor=anchor)


def _chart_pair(layout, progress, radar):
    chunk_size = 12
    chunks = [progress[offset:offset + chunk_size] for offset in range(0, len(progress), chunk_size)] or [[]]
    height = 173.0
    gap = 8.0
    card_width = (WIDTH - 8 - gap) / 2
    for number, chunk in enumerate(chunks):
        if layout.y + height > BOTTOM:
            layout.new_page()
        top = layout.y
        layout.rect(MARGIN, top, WIDTH, height, GOLD_WASH)
        for column, title in enumerate(("Tiến độ kỹ năng" + (" (tiếp)" if number else ""), "Năng lực kỳ gần nhất")):
            card_x = MARGIN + 4 + column * (card_width + gap)
            layout.rounded(card_x, top + 3, card_width, height - 6, "#ffffff", CARD_BORDER, 9)
            layout.text(title, card_x + 10, top + 15, size=TITLE_SIZE, bold=True, color=shared.GREEN)
            if column == 0:
                if chunk:
                    _plot(layout, chunk, card_x + 10, top + 39, card_width - 20, skill=True)
                    caption = (f"{len(progress)} buổi trong khoảng đã chọn · Điểm thiếu để trống." if len(chunks) == 1 else
                               f"Buổi {number * chunk_size + 1}-{number * chunk_size + len(chunk)}/{len(progress)} · Điểm thiếu để trống.")
                    for index, (value, size, bold, color) in enumerate(_lines(caption, card_width - 20, size=7, color=shared.MUTED)):
                        layout.text(value, card_x + 10, top + 143 + index * 10, size=size, color=color)
                else:
                    _placeholder(layout, "Chưa có dữ liệu tiến độ trong khoảng đã chọn.", card_x + 10, top + 39, card_width - 20)
            else:
                _radar(layout, radar, card_x + 10, top + 36, card_width - 20)
        layout.y += height + 8


def _evaluation_chart(layout, report):
    details = sorted(report.get("evaluation_details") or [], key=lambda row: (_sort_date(row.get("end_date")), str(row.get("id") or "")))
    continuation = "Biểu đồ đánh giá (tiếp)"
    layout.open("Biểu đồ đánh giá", minimum=220 if details else 89)
    if not details:
        _placeholder(layout, "Chưa có đợt đánh giá tổng hợp trong khoảng đã chọn.", X, layout.y, CONTENT_WIDTH)
        layout.y += 40
    else:
        for offset in range(0, len(details), 18):
            if layout.y + 182 + 11 > BOTTOM:
                layout.continuation(continuation)
            chunk = details[offset:offset + 18]
            _plot(layout, chunk, X, layout.y, CONTENT_WIDTH, skill=False)
            layout.y += 155
            layout.paragraph(f"Phiếu {offset + 1}-{offset + len(chunk)}/{len(details)} · Bảy tiêu chí đã nộp, thang 1-5. Điểm thiếu để trống.",
                             title=continuation, size=7, color=shared.MUTED, gap=8)
    aggregates = report.get("evaluations") or []
    if aggregates:
        layout.paragraph("Điểm trung bình tổng hợp theo đợt", title=continuation, bold=True, size=8.4, gap=5)
        for item in aggregates:
            layout.paragraph(f"{shared._text(item.get('cycle_name'))} · {shared._date(item.get('end_date'))}", title=continuation, bold=True)
            layout.paragraph(" · ".join(f"{label}: {shared._score_label(item.get(key), 5)}" for key, label, _ in shared.SERIES), title=continuation, gap=6)
    layout.close()


def build_pdf_layout(report):
    """Build the reference-order PDF without mutating the complete report DTO."""
    layout = _CardLayout()
    progress = sorted(report.get("progress") or [], key=lambda row: (_sort_date(row.get("training_date")),
                       str(row.get("start_time") or ""), str(row.get("id") or "")))
    _journal(layout, report, progress)
    _history(layout, report)
    _chart_pair(layout, progress, report.get("latest_radar"))
    _evaluation_chart(layout, report)
    return layout.finish()
