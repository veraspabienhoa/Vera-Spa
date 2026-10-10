"""Complete, Vietnamese training-report exports from an already-authorized DTO.

No database access or authorization belongs here. PDF uses the reference card
template; PNG retains its full, paginated drawing model without clipping.
"""
from __future__ import annotations

from datetime import date, datetime, time
from io import BytesIO
import math
from pathlib import Path
import re
from threading import RLock
from typing import Any
import unicodedata
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


class ReportExportTooLarge(ValueError):
    """A lossless PNG would exceed the bounded pixel allocation."""


class ReportExportUnavailable(RuntimeError):
    """A required export dependency, such as Vietnamese fonts, is unavailable."""


# At 144 dpi, one A4 page is about two million pixels. Bound both dimensions
# and total allocation (RGB plus encoder overhead); PDF has no page-count cap.
PNG_SCALE = 2
MAX_PNG_PIXELS = 36_000_000
MAX_PNG_HEIGHT = 30_000
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 40.0
BODY_WIDTH = PAGE_WIDTH - MARGIN * 2
BODY_TOP = 70.0
BODY_BOTTOM = PAGE_HEIGHT - 47.0
VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")
FONT_ROOTS = (Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/local/share/fonts"))
REGULAR_FONT = "VeraTrainingReport"
BOLD_FONT = "VeraTrainingReportBold"
_FONT_LOCK = RLock()
GREEN = "#173d2f"
INK = "#233e34"
MUTED = "#62766c"
PALE = "#eef4ef"
GRID = "#d8e3dc"
GOLD = "#ac8024"
BLUE = "#3878a4"
PURPLE = "#8759a0"
SERIES = (("craft", "Tay nghề", GREEN), ("communication", "Giao tiếp", BLUE),
          ("attitude", "Thái độ", GOLD), ("conduct", "Tác phong", PURPLE))
SCORE_FIELDS = (("craft_score", "Tay nghề"), ("communication_score", "Giao tiếp"),
                ("attitude_score", "Thái độ"), ("discipline_score", "Kỷ luật"),
                ("appearance_score", "Ngoại hình"), ("hygiene_score", "Vệ sinh"),
                ("attendance_score", "Chuyên cần"))
DETAIL_SERIES = tuple((key, label, color) for (key, label), color in zip(
    SCORE_FIELDS, (GREEN, BLUE, GOLD, PURPLE, "#b45b47", "#25847d", "#6b7084")))
ROLE_LABELS = {"leader": "Trưởng nhóm", "quanly": "Quản lý", "admin": "Quản trị viên",
               "employee": "Nhân viên", "all": "Tất cả"}
STATUS_LABELS = {"completed": "Hoàn thành", "submitted": "Đã nộp", "draft": "Bản nháp",
                 "assigned": "Đã phân công", "pending": "Chờ xử lý", "cancelled": "Đã hủy"}
RATING_LABELS = {"excellent": "Xuất sắc", "good": "Tốt", "average": "Trung bình",
                 "weak": "Yếu", "all": "Tất cả"}


def _fonts() -> tuple[Path, Path]:
    paths = []
    for filename in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
        path = next((root / filename for root in FONT_ROOTS if (root / filename).is_file()), None)
        if path is None:
            raise ReportExportUnavailable(
                "Không tìm thấy phông chữ tiếng Việt DejaVu Sans. "
                "Vui lòng cài đặt fonts-dejavu-core trên máy chủ để xuất báo cáo."
            )
        paths.append(path)
    with _FONT_LOCK:
        for name, path in zip((REGULAR_FONT, BOLD_FONT), paths):
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(path)))
    return paths[0], paths[1]


def _text(value: Any, empty: str = "Chưa có") -> str:
    if value is None or value == "":
        return empty
    return unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n").replace("\r", "\n")


def _date(value: Any) -> str:
    if value is None or value == "":
        return "Chưa có"
    if isinstance(value, datetime):
        value = value.astimezone(VIETNAM) if value.tzinfo else value
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%Y")
    raw = str(value)
    try:
        if "T" in raw or " " in raw:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return _date(parsed)
        return date.fromisoformat(raw).strftime("%d-%m-%Y")
    except ValueError:
        return _text(value)


def _datetime(value: Any) -> str:
    if value is None or value == "":
        return "Chưa có"
    if isinstance(value, date) and not isinstance(value, datetime):
        return _date(value)
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(VIETNAM)
        return parsed.strftime("%d-%m-%Y %H:%M:%S") + " (giờ Việt Nam)"
    except (TypeError, ValueError):
        return _text(value)


def _time(value: Any) -> str:
    if value is None or value == "":
        return "Chưa có"
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return _text(value)


def _score(value: Any, maximum: int) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 1 <= number <= maximum else None


def _score_label(value: Any, maximum: int) -> str:
    number = _score(value, maximum)
    return "Chưa có" if number is None else f"{number:g}/{maximum}"


def _width(value: str, size: float, bold: bool = False) -> float:
    return pdfmetrics.stringWidth(value, BOLD_FONT if bold else REGULAR_FONT, size)


def _wrap(value: Any, width: float, size: float, bold: bool = False) -> list[str]:
    """Wrap all text, including unbroken identifiers, without truncation."""
    result: list[str] = []
    for paragraph in _text(value).split("\n"):
        if not paragraph.strip():
            result.append("")
            continue
        line = ""
        for word in re.findall(r"\S+", paragraph):
            candidate = f"{line} {word}" if line else word
            if _width(candidate, size, bold) <= width:
                line = candidate
                continue
            if line:
                result.append(line)
                line = ""
            if _width(word, size, bold) <= width:
                line = word
                continue
            part, part_width = "", 0.0
            for char in word:
                char_width = _width(char, size, bold)
                if part and part_width + char_width > width:
                    result.append(part)
                    part, part_width = "", 0.0
                part += char
                part_width += char_width
            line = part
        if line:
            result.append(line)
    return result or [""]


class _Layout:
    """Small point-coordinate drawing model shared by vector PDF and Pillow."""

    def __init__(self, employee: str, *, png: bool = False):
        self.pages: list[list[tuple]] = []
        self.employee = employee
        self.png = png
        self.y = BODY_TOP
        self.new_page()

    @property
    def commands(self) -> list[tuple]:
        return self.pages[-1]

    def new_page(self) -> None:
        if self.png:
            _check_png_size(len(self.pages) + 1)
        self.pages.append([])
        self.y = BODY_TOP
        self.rect(MARGIN, 24, 4, 24, GREEN)
        self.text("VERA SPA", MARGIN + 13, 24, size=12, bold=True)
        self.text("BÁO CÁO ĐÀO TẠO & PHÁT TRIỂN", MARGIN + 13, 41, size=7.5, color=MUTED)
        self.line(MARGIN, 59, PAGE_WIDTH - MARGIN, 59, GRID)

    def ensure(self, height: float) -> None:
        if self.y + height > BODY_BOTTOM:
            self.new_page()

    def text(self, text: Any, x: float, y: float, *, size: float = 9.2,
             bold: bool = False, color: str = INK, anchor: str = "left") -> None:
        self.commands.append(("text", _text(text, ""), x, y, size, bold, color, anchor))

    def rect(self, x: float, y: float, width: float, height: float, color: str) -> None:
        self.commands.append(("rect", x, y, width, height, color))

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str = GRID, width: float = .7) -> None:
        self.commands.append(("line", x1, y1, x2, y2, color, width))

    def circle(self, x: float, y: float, radius: float, color: str) -> None:
        self.commands.append(("circle", x, y, radius, color))

    def polygon(self, points: list[tuple[float, float]], color: str, *, fill: str | None = None) -> None:
        self.commands.append(("polygon", points, color, fill))

    def paragraph(self, value: Any, *, size: float = 9.2, bold: bool = False,
                  color: str = INK, indent: float = 0, gap: float = 5) -> None:
        leading = size * 1.5
        for text in _wrap(value, BODY_WIDTH - indent, size, bold):
            self.ensure(leading)
            self.text(text, MARGIN + indent, self.y, size=size, bold=bold, color=color)
            self.y += leading
        self.y += gap

    def field(self, label: str, value: Any) -> None:
        self.paragraph(f"{label}: {_text(value)}")

    def note(self, label: str, value: Any) -> None:
        self.ensure(33)
        self.paragraph(label, bold=True, size=9, gap=2)
        self.paragraph(value, indent=10, gap=8)

    def section(self, number: str, title: str, subtitle: str | None = None, *, reserve: float = 47) -> None:
        self.ensure(max(85, 45 + (32 if subtitle else 0) + reserve))
        self.y += 7
        self.rect(MARGIN, self.y, BODY_WIDTH, 29, PALE)
        self.text(number, MARGIN + 9, self.y + 7, size=10, bold=True, color=GOLD)
        self.text(title, MARGIN + 34, self.y + 6, size=11, bold=True)
        self.y += 38
        if subtitle:
            self.paragraph(subtitle, size=8.3, color=MUTED, gap=9)

    def record(self, title: str) -> None:
        self.ensure(80)
        self.line(MARGIN, self.y, PAGE_WIDTH - MARGIN, self.y)
        self.y += 8
        self.paragraph(title, bold=True, size=10.3, gap=7)

    def finish(self) -> list[list[tuple]]:
        total = len(self.pages)
        for index, page in enumerate(self.pages, 1):
            page.append(("line", MARGIN, PAGE_HEIGHT - 34, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 34, GRID, .7))
            page.append(("text", "VERA SPA | Báo cáo đào tạo đầy đủ", MARGIN, PAGE_HEIGHT - 26, 7.4, False, MUTED, "left"))
            page.append(("text", f"Trang {index}/{total}", PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 26, 7.4, False, MUTED, "right"))
        return self.pages


def _check_png_size(page_count: int) -> tuple[int, int]:
    width = math.ceil(PAGE_WIDTH * PNG_SCALE)
    height = math.ceil(PAGE_HEIGHT * PNG_SCALE) * page_count
    if height > MAX_PNG_HEIGHT or width * height > MAX_PNG_PIXELS:
        raise ReportExportTooLarge(
            "Báo cáo quá dài để xuất PNG đầy đủ an toàn. "
            "Vui lòng chọn PDF hoặc thu hẹp bộ lọc thời gian/nội dung."
        )
    return width, height


def _line_chart(layout: _Layout, items: list[dict], *, skill: bool = False) -> None:
    if not items:
        layout.paragraph("Chưa có dữ liệu trong phạm vi bộ lọc.", color=MUTED)
        return
    series = (("skill_score", "Tay nghề", GREEN),) if skill else DETAIL_SERIES
    maximum = 6 if skill else 5
    chunk_size = 24 if skill else 18
    for offset in range(0, len(items), chunk_size):
        chunk = items[offset:offset + chunk_size]
        height = 219 if skill else 250
        layout.ensure(height)
        top = layout.y
        layout.text(f"Bản ghi {offset + 1}-{offset + len(chunk)} / {len(items)}", MARGIN, top, size=8, color=MUTED)
        left, right = MARGIN + 34, PAGE_WIDTH - MARGIN - 8
        chart_top, bottom = top + 29, top + 159
        for value in range(1, maximum + 1):
            y = bottom - (value - 1) / (maximum - 1) * (bottom - chart_top)
            layout.line(left, y, right, y)
            label = ("E", "D", "C", "B", "A", "A+")[value - 1] if skill else str(value)
            layout.text(label, left - 10, y - 5, size=8, color=MUTED, anchor="right")
        layout.line(left, chart_top, left, bottom, MUTED)
        xs = [left + (right - left) * i / (len(chunk) - 1) if len(chunk) > 1 else (left + right) / 2 for i in range(len(chunk))]
        for key, _, color in series:
            previous = None
            for x, item in zip(xs, chunk):
                value = _score(item.get(key), maximum)
                if value is None:
                    previous = None  # A gap means missing; never connect through it.
                    continue
                y = bottom - (value - 1) / (maximum - 1) * (bottom - chart_top)
                if previous:
                    layout.line(*previous, x, y, color, 1.6)
                layout.circle(x, y, 2.7, color)
                previous = (x, y)
        # Five full date labels fit at A4 width; every record is still plotted.
        tick_indexes = sorted({round(i * (len(chunk) - 1) / min(4, max(1, len(chunk) - 1))) for i in range(min(5, len(chunk)))})
        for i in tick_indexes:
            label = _date(chunk[i].get("training_date" if skill else "end_date"))
            x = xs[i]
            anchor = "left" if i == 0 else "right" if i == len(chunk) - 1 else "center"
            layout.text(label, x, bottom + 8, size=7, color=MUTED, anchor=anchor)
        legend_y = bottom + 28
        legend_columns = min(4, len(series))
        for i, (_, label, color) in enumerate(series):
            x = MARGIN + (i % legend_columns) * (BODY_WIDTH / legend_columns)
            y = legend_y + (i // legend_columns) * 18
            layout.line(x, y + 6, x + 13, y + 6, color, 2)
            layout.text(label, x + 19, y, size=8)
        legend_rows = math.ceil(len(series) / legend_columns)
        layout.text("Ô trống là chưa có điểm; các điểm được xếp theo thứ tự bản ghi.", MARGIN, legend_y + legend_rows * 18, size=7.5, color=MUTED)
        layout.y = top + height


def _radar(layout: _Layout, item: dict | None) -> None:
    if not item:
        layout.paragraph("Chưa có đánh giá tổng hợp đã nộp.", color=MUTED)
        return
    layout.field("Đợt gần nhất", item.get("cycle_name"))
    layout.field("Ngày kết thúc", _date(item.get("end_date")))
    layout.ensure(270)
    top = layout.y
    cx, cy, radius = MARGIN + BODY_WIDTH / 2, top + 112, 79
    # Clockwise: craft, communication, attitude, conduct.
    axes = [(0, -1), (1, 0), (0, 1), (-1, 0)]
    for level in range(1, 6):
        ring = [(cx + ax * radius * level / 5, cy + ay * radius * level / 5) for ax, ay in axes]
        layout.polygon(ring, GRID)
        layout.text(str(level), cx + 4, cy - radius * level / 5 - 2, size=6.5, color=MUTED)
    values = [_score(item.get(key), 5) for key, _, _ in SERIES]
    points = [(cx + ax * radius * value / 5, cy + ay * radius * value / 5) if value is not None else None for (ax, ay), value in zip(axes, values)]
    if all(point is not None for point in points):
        layout.polygon(points, GREEN)
    else:
        for i, point in enumerate(points):
            other = points[(i + 1) % len(points)]
            if point is not None and other is not None:
                layout.line(*point, *other, GREEN, 1.4)
    for (ax, ay), point in zip(axes, points):
        layout.line(cx, cy, cx + ax * radius, cy + ay * radius, GRID)
        if point is not None:
            layout.circle(*point, 3, GREEN)
    positions = [(cx, cy - radius - 23, "center"), (cx + radius + 13, cy - 7, "left"),
                 (cx, cy + radius + 13, "center"), (cx - radius - 13, cy - 7, "right")]
    for (key, label, _), (x, y, anchor) in zip(SERIES, positions):
        layout.text(label, x, y, size=8.5, bold=True, anchor=anchor)
        layout.text(_score_label(item.get(key), 5), x, y + 14, size=8, color=MUTED, anchor=anchor)
    layout.y = top + 246
    layout.paragraph("Thang điểm 1-5. Điểm chưa có được để trống, không quy đổi thành 0.", size=8, color=MUTED)


def _build_layout(report: dict, *, png: bool = False) -> list[list[tuple]]:
    employee = report.get("employee") or {}
    username = report.get("employee_username") or employee.get("username")
    layout = _Layout(_text(username), png=png)
    layout.paragraph("Báo cáo đào tạo", size=23, bold=True, gap=4)
    layout.paragraph("Tiến độ tay nghề và đánh giá tổng hợp", size=11, color=MUTED, gap=15)
    layout.field("Nhân viên", employee.get("full_name") or username)
    layout.field("Tài khoản", username)
    if employee.get("department"):
        layout.field("Bộ phận", employee["department"])
    if employee.get("role"):
        layout.field("Vai trò", ROLE_LABELS.get(employee["role"], employee["role"]))
    start, end = report.get("date_from"), report.get("date_to")
    layout.field("Khoảng thời gian", f"{_date(start) if start else 'Không giới hạn đầu'} đến {_date(end) if end else 'Không giới hạn cuối'}" if start or end else "Tất cả thời gian")
    filters = report.get("filters") or {}
    layout.field("Vai trò người đánh giá", ROLE_LABELS.get(filters.get("evaluator_role", "all"), filters.get("evaluator_role")))
    layout.field("Xếp loại", RATING_LABELS.get(filters.get("rating", "all"), filters.get("rating")))
    if filters.get("q"):
        layout.field("Từ khóa", filters["q"])
    progress = list(report.get("progress") or [])
    evaluations = list(report.get("evaluations") or [])
    details = list(report.get("evaluation_details") or [])
    history = list(report.get("history") or [])
    layout.paragraph(f"{len(progress)} buổi đào tạo  |  {len(evaluations)} đợt đánh giá  |  {len(details)} phiếu đánh giá", bold=True, size=10, gap=5)
    layout.paragraph("Các ngày được trình bày theo dd-mm-yyyy; thời gian theo múi giờ Việt Nam. Nội dung dài được tiếp tục ở trang sau.", size=8, color=MUTED, gap=6)

    layout.section("01", "Tiến bộ tay nghề", "Thang tay nghề: E = 1, D = 2, C = 3, B = 4, A = 5, A+ = 6.", reserve=219 if progress else 35)
    _line_chart(layout, progress, skill=True)
    layout.section("02", "Năng lực tổng hợp gần nhất", reserve=320 if report.get("latest_radar") else 35)
    _radar(layout, report.get("latest_radar"))
    layout.section("03", "Diễn biến từng tiêu chí đánh giá", "Bảy tiêu chí của từng phiếu đã nộp, trên thang 1-5; theo ngày kết thúc đợt và mã phiếu.", reserve=250 if details else 35)
    ordered_details = sorted(details, key=lambda item: (str(item.get("end_date") or ""), str(item.get("id") or "")))
    _line_chart(layout, ordered_details)
    # Keep aggregate values distinct from the seven raw-criterion chart.
    if evaluations:
        layout.ensure(110)
        layout.paragraph("Điểm trung bình tổng hợp theo đợt", bold=True, size=10, gap=7)
    for index, item in enumerate(evaluations, 1):
        layout.record(f"Đợt {index}: {_text(item.get('cycle_name'))} | {_date(item.get('end_date'))}")
        layout.field("Mã đợt", item.get("cycle_id"))
        for key, label, _ in SERIES:
            layout.field(label, _score_label(item.get(key), 5))

    layout.section("04", "Nhật ký đào tạo đầy đủ", f"Toàn bộ {len(progress)} buổi đào tạo trong dữ liệu báo cáo.")
    if not progress:
        layout.paragraph("Chưa có buổi đào tạo phù hợp.", color=MUTED)
    for index, item in enumerate(progress, 1):
        layout.record(f"Buổi {index} | {_date(item.get('training_date'))} | {_time(item.get('start_time'))} - {_time(item.get('end_time'))}")
        layout.field("Mã buổi", item.get("id"))
        layout.note("Nội dung đào tạo", item.get("topic"))
        layout.field("Người đào tạo", item.get("trainer_username"))
        layout.field("Người đánh giá", item.get("evaluator_name"))
        layout.field("Vai trò người đánh giá", ROLE_LABELS.get(item.get("evaluator_role"), item.get("evaluator_role")))
        layout.field("Mức tay nghề", item.get("skill_grade"))
        layout.field("Điểm tay nghề", _score_label(item.get("skill_score"), 6))
        layout.field("Thái độ học tập", item.get("learning_attitude"))
        layout.field("Trạng thái", STATUS_LABELS.get(item.get("status"), item.get("status")))
        layout.field("Ngày tạo", _datetime(item.get("created_at")))
        layout.note("Điểm mạnh", item.get("strengths"))
        layout.note("Cần cải thiện", item.get("improvements"))
        layout.note("Ghi chú", item.get("notes"))

    layout.section("05", "Chi tiết đánh giá đã nộp", f"Toàn bộ {len(details)} phiếu, bao gồm từng tiêu chí và tất cả nhận xét.")
    if not details:
        layout.paragraph("Chưa có phiếu đánh giá đã nộp phù hợp.", color=MUTED)
    for index, item in enumerate(details, 1):
        layout.record(f"Phiếu {index}: {_text(item.get('cycle_name'))}")
        layout.field("Mã phiếu", item.get("id"))
        layout.field("Mã đợt", item.get("cycle_id"))
        layout.field("Ngày bắt đầu đợt", _date(item.get("start_date")))
        layout.field("Ngày kết thúc đợt", _date(item.get("end_date")))
        layout.field("Người đánh giá", item.get("evaluator_name"))
        layout.field("Tài khoản người đánh giá", item.get("evaluator_username"))
        layout.field("Vai trò người đánh giá", ROLE_LABELS.get(item.get("evaluator_role"), item.get("evaluator_role")))
        layout.field("Trạng thái", STATUS_LABELS.get(item.get("status"), item.get("status")))
        layout.field("Thời điểm nộp", _datetime(item.get("submitted_at")))
        for key, label in SCORE_FIELDS:
            layout.field(label, _score_label(item.get(key), 5))
        layout.note("Điểm mạnh", item.get("strengths"))
        layout.note("Cần cải thiện", item.get("improvements"))
        layout.note("Nhận xét", item.get("comments"))

    layout.section("06", "Lịch sử theo bộ lọc", f"{len(history)} bản ghi trong lịch sử báo cáo.")
    if not history:
        layout.paragraph("Chưa có lịch sử phù hợp.", color=MUTED)
    for index, item in enumerate(history, 1):
        kind = {"daily": "Đào tạo", "comprehensive": "Đánh giá tổng hợp"}.get(item.get("type"), _text(item.get("type")))
        layout.record(f"{index}. {_date(item.get('date'))} | {kind}")
        layout.field("Mã bản ghi", item.get("id"))
        layout.field("Nội dung", item.get("title"))
        layout.field("Người đánh giá", item.get("evaluator_name"))
        layout.field("Vai trò", ROLE_LABELS.get(item.get("evaluator_role"), item.get("evaluator_role")))
        layout.field("Xếp loại", item.get("rating_label") or RATING_LABELS.get(item.get("rating"), "Chưa có"))
    return layout.finish()


def _render_pdf(pages: list[list[tuple]], report: dict) -> bytes:
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    employee = report.get("employee") or {}
    pdf.setTitle("Báo cáo đào tạo - " + _text(employee.get("full_name") or employee.get("display_name")
                                             or report.get("employee_username") or employee.get("username")))
    pdf.setAuthor("VERA SPA")
    for page in pages:
        for command in page:
            kind, *args = command
            if kind == "text":
                value, x, y, size, bold, color, anchor = args
                pdf.setFont(BOLD_FONT if bold else REGULAR_FONT, size)
                pdf.setFillColor(color)
                draw = pdf.drawRightString if anchor == "right" else pdf.drawCentredString if anchor == "center" else pdf.drawString
                draw(x, PAGE_HEIGHT - y - size, value)
            elif kind == "rect":
                x, y, width, height, color = args
                pdf.setFillColor(color)
                pdf.rect(x, PAGE_HEIGHT - y - height, width, height, fill=1, stroke=0)
            elif kind == "roundrect":
                x, y, width, height, radius, fill, border = args
                pdf.setFillColor(fill)
                pdf.setStrokeColor(border)
                pdf.setLineWidth(.6)
                pdf.roundRect(x, PAGE_HEIGHT - y - height, width, height, radius, fill=1, stroke=1)
            elif kind == "line":
                x1, y1, x2, y2, color, width = args
                pdf.setStrokeColor(color)
                pdf.setLineWidth(width)
                pdf.line(x1, PAGE_HEIGHT - y1, x2, PAGE_HEIGHT - y2)
            elif kind == "circle":
                x, y, radius, color = args
                pdf.setFillColor(color)
                pdf.circle(x, PAGE_HEIGHT - y, radius, fill=1, stroke=0)
            elif kind == "polygon":
                points, color, fill = args
                path = pdf.beginPath()
                path.moveTo(points[0][0], PAGE_HEIGHT - points[0][1])
                for x, y in points[1:]:
                    path.lineTo(x, PAGE_HEIGHT - y)
                path.close()
                pdf.setStrokeColor(color)
                pdf.setLineWidth(.8)
                if fill:
                    pdf.setFillColor(fill)
                pdf.drawPath(path, fill=int(bool(fill)), stroke=1)
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def _render_png(pages: list[list[tuple]], font_paths: tuple[Path, Path]) -> bytes:
    width, height = _check_png_size(len(pages))
    image = Image.new("RGB", (width, height), "white")
    try:
        draw = ImageDraw.Draw(image)
        fonts: dict[tuple[float, bool], Any] = {}
        page_height = math.ceil(PAGE_HEIGHT * PNG_SCALE)
        for index, page in enumerate(pages):
            y_offset = page_height * index
            def point(x: float, y: float) -> tuple[float, float]:
                return x * PNG_SCALE, y * PNG_SCALE + y_offset
            for command in page:
                kind, *args = command
                if kind == "text":
                    value, x, y, size, bold, color, anchor = args
                    key = (size, bold)
                    if key not in fonts:
                        fonts[key] = ImageFont.truetype(str(font_paths[int(bold)]), round(size * PNG_SCALE))
                    # Baseline anchors align precisely with the vector PDF model.
                    draw.text(point(x, y + size), value, font=fonts[key], fill=color,
                              anchor={"left": "ls", "right": "rs", "center": "ms"}[anchor])
                elif kind == "rect":
                    x, y, w, h, color = args
                    draw.rectangle((*point(x, y), *point(x + w, y + h)), fill=color)
                elif kind == "line":
                    x1, y1, x2, y2, color, w = args
                    draw.line((point(x1, y1), point(x2, y2)), fill=color, width=max(1, round(w * PNG_SCALE)))
                elif kind == "circle":
                    x, y, radius, color = args
                    draw.ellipse((*point(x - radius, y - radius), *point(x + radius, y + radius)), fill=color)
                elif kind == "polygon":
                    points, color, fill = args
                    vertices = [point(x, y) for x, y in points]
                    if fill:
                        draw.polygon(vertices, fill=fill)
                    draw.line(vertices + [vertices[0]], fill=color, width=2)
            if index:
                draw.line((0, y_offset, width, y_offset), fill=GRID, width=2)
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()
    finally:
        image.close()


def render_training_report(report: dict, format: str) -> bytes:
    """Render an already-filtered, unpaginated report DTO as PDF or full PNG.

    The caller owns access checks, filtering and choosing the filename. Invalid
    formats raise ValueError; oversized PNG raises ReportExportTooLarge so an API
    can return 413. Missing fonts raise ReportExportUnavailable, never a corrupt
    Vietnamese fallback. All output is generated in memory without temp files.
    """
    file_format = str(format).lower()
    if file_format not in {"pdf", "png"}:
        raise ValueError("Định dạng báo cáo phải là PDF hoặc PNG.")
    fonts = _fonts()
    if file_format == "pdf":
        from vera_web_v2_training_report_pdf import build_pdf_layout
        return _render_pdf(build_pdf_layout(report), report)
    return _render_png(_build_layout(report, png=True), fonts)
