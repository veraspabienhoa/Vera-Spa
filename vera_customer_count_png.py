"""Complete, read-only customer-count PNGs from the PDF export's summary.

Sections are stacked into one image instead of capturing a paginated browser
view. Refuse reports exceeding the pixel budget rather than omitting dates or
reducing the type to an unreadable size. Only one image is allocated per worker.
"""
from datetime import date, datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import BoundedSemaphore

from PIL import Image, ImageDraw, ImageFont

from vera_customer_count_pdf import VN


WIDTH = 1600
SECTION_HEIGHT = 1000
SECTION_GAP = 24
DAYS_PER_SECTION = 14
MAX_IMAGE_HEIGHT = 32760
MAX_IMAGE_PIXELS = 50_000_000
RENDER_SLOT = BoundedSemaphore(1)
GREEN, PALE, BLUE = '#194b3b', '#edf5f0', '#4f81bd'
GRID, WHITE, BACKGROUND = '#c8d9cf', '#ffffff', '#e5ebe7'
SIZE_MESSAGE = 'Báo cáo quá dài để tạo một ảnh PNG đầy đủ. Hãy chọn khoảng ngày ngắn hơn hoặc xuất PDF.'


class CustomerCountImageTooLarge(ValueError):
    """No image was produced because it would omit data or exceed safe bounds."""


@lru_cache(maxsize=12)
def _font(size, bold=False):
    name = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    for root in (Path('/usr/share/fonts/truetype/dejavu'),
                 Path('/opt/codex/runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts')):
        path = root / name
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    raise RuntimeError('Máy chủ cần font DejaVu Sans để xuất ảnh PNG tiếng Việt.')


def _display_day(value):
    return date.fromisoformat(value).strftime('%d-%m-%Y') if value else 'Không rõ ngày'


def _wrap(text, font, width):
    """Wrap complete filter values, including long unbroken invoice numbers."""
    lines, line = [], ''
    for word in str(text).split():
        candidate = f'{line} {word}' if line else word
        if font.getlength(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = ''
        for char in word:
            if line and font.getlength(line + char) > width:
                lines.append(line)
                line = ''
            line += char
    if line:
        lines.append(line)
    return lines or ['']


def _layout(summary, filters):
    daily = summary['daily']
    dated = [day for day, _ in daily if day]
    start = filters.get('date_from') or (min(dated) if dated else '')
    end = filters.get('date_to') or (max(dated) if dated else '')
    if start and end:
        # customer_counts intentionally bounds zero-day expansion at ten years.
        # A wider requested/inferred range must not produce a deceptively short
        # PNG merely because the sparse summary has omitted its empty days.
        span = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        if span > (MAX_IMAGE_HEIGHT // SECTION_HEIGHT) * DAYS_PER_SECTION:
            raise CustomerCountImageTooLarge(SIZE_MESSAGE)
    descriptions = [f'{label}: {_display_day(filters[key]) if key == "date" else filters[key]}'
                    for key, label in [('date', 'Ngày'), ('employee', 'Nhân viên'),
                                       ('customer', 'Khách hàng'), ('service', 'Dịch vụ'),
                                       ('bill_no', 'Số hóa đơn'), ('total_amount', 'Tổng tiền')]
                    if filters.get(key) not in (None, '')]
    filter_lines = _wrap(' | '.join(descriptions) or 'Các bộ lọc khác: Tất cả', _font(18), WIDTH - 128)
    section_height = SECTION_HEIGHT + (len(filter_lines) - 1) * 26
    section_count = max(1, (len(daily) + DAYS_PER_SECTION - 1) // DAYS_PER_SECTION)
    image_height = section_count * section_height + (section_count - 1) * SECTION_GAP
    if image_height > MAX_IMAGE_HEIGHT or WIDTH * image_height > MAX_IMAGE_PIXELS:
        raise CustomerCountImageTooLarge(SIZE_MESSAGE)
    chunks = [daily[i:i + DAYS_PER_SECTION] for i in range(0, len(daily), DAYS_PER_SECTION)] or [[]]
    return chunks, filter_lines, section_height, image_height


def _draw_section(draw, *, top, height, index, sections, chunk, summary, filters, filter_lines, generated_at):
    left, right = 64, WIDTH - 64
    usable = right - left
    draw.rectangle((0, top, WIDTH - 1, top + height - 1), fill=WHITE)

    def text(x, y, value, *, size=20, bold=False, anchor='lt', color=GREEN):
        draw.text((x, top + y), str(value), font=_font(size, bold), fill=color, anchor=anchor)

    text(left, 44, 'VERA SPA | SỐ LƯỢNG KHÁCH', size=38, bold=True)
    start, end = filters.get('date_from') or '', filters.get('date_to') or ''
    scope = f'{_display_day(start) if start else "Tất cả"} đến {_display_day(end) if end else "Tất cả"}'
    text(left, 108, f'Theo bộ lọc: {scope}')
    for line_index, line in enumerate(filter_lines):
        text(left, 146 + 26 * line_index, line, size=18)
    offset = (len(filter_lines) - 1) * 26
    y = 190 + offset
    draw.rectangle((left, top + y, right, top + y + 112), fill=PALE)
    metrics = [('TỔNG KHÁCH (SỐ HÓA ĐƠN)', summary['total']),
               ('NGÀY CÓ KHÁCH', sum(count > 0 for day, count in summary['daily'] if day)),
               ('CAO NHẤT / NGÀY', max((count for day, count in summary['daily'] if day), default=0))]
    for column, (label, value) in enumerate(metrics):
        x = left + column * usable / 3 + 22
        text(x, y + 18, label, size=18)
        text(x, y + 52, value, size=38, bold=True)
    text(left, 327 + offset, 'Một hóa đơn = một lượt khách; mỗi hóa đơn chỉ được tính một lần.', size=18)
    text(right, 362 + offset, f'Phần {index + 1} / {sections}', size=18, anchor='rt')

    if chunk:
        plot_left, plot_right = left + 48, right - 8
        plot_top, plot_bottom = 410 + offset, 704 + offset
        maximum = max(count for _, count in summary['daily'])
        step = max(1, (maximum + 4) // 5)
        scale_max = step * 6
        for tick in range(7):
            y = plot_bottom - (plot_bottom - plot_top) * tick / 6
            draw.line((plot_left, top + y, plot_right, top + y), fill=GRID, width=1)
            text(plot_left - 12, y, step * tick, size=16, anchor='rm')
        slot = (plot_right - plot_left) / len(chunk)
        for column, (day, count) in enumerate(chunk):
            center = plot_left + slot * (column + .5)
            bar_top = plot_bottom - count / scale_max * (plot_bottom - plot_top)
            if count:
                draw.rectangle((center - slot * .30, top + bar_top,
                                center + slot * .30, top + plot_bottom), fill=BLUE)
            text(center, bar_top - 12, count, size=18, bold=True, anchor='mb')
            text(center, plot_bottom + 16, _display_day(day) if day else 'Không rõ', size=14, anchor='mt')

        table_top, row_height = 773 + offset, 52
        widths = [108] + [(usable - 196) / len(chunk)] * len(chunk) + [88]
        cells = [['Ngày'] + [_display_day(day) for day, _ in chunk] + ['Cộng'],
                 ['Số khách'] + [str(count) for _, count in chunk] + [str(sum(count for _, count in chunk))]]
        for row_index, row in enumerate(cells):
            x = left
            y = table_top + row_index * row_height
            for value, width in zip(row, widths):
                draw.rectangle((x, top + y, x + width, top + y + row_height),
                               fill=PALE if row_index == 0 else WHITE, outline=GRID, width=1)
                size = 13 if row_index == 0 else 18
                while size > 10 and _font(size, row_index == 1).getlength(str(value)) > width - 12:
                    size -= 1
                text(x + width / 2, y + row_height / 2, value,
                     size=size, bold=row_index == 1, anchor='mm')
                x += width
    else:
        text(left, 436 + offset, 'Không có hóa đơn khớp bộ lọc.', size=24)
    if summary['missing_id_rows']:
        text(left, 901 + offset,
             f"Có {summary['missing_id_rows']} dòng thiếu mã hóa đơn, không đưa vào số khách.", size=18)
    text(left, height - 36,
         f"Lập lúc {generated_at.astimezone(VN).strftime('%d-%m-%Y %H:%M')} | Theo dữ liệu đã thanh toán", size=16)
    text(right, height - 36, f'Phần {index + 1} / {sections}', size=16, anchor='rt')


def customer_count_png(summary, filters, *, generated_at=None):
    """Render every summary date, or return a clear error without a partial PNG."""
    if not RENDER_SLOT.acquire(blocking=False):
        raise RuntimeError('Máy chủ đang tạo ảnh PNG khác. Vui lòng thử lại sau ít giây.')
    try:
        chunks, filter_lines, section_height, image_height = _layout(summary, filters)
        generated_at = generated_at or datetime.now(VN)
        with Image.new('RGB', (WIDTH, image_height), BACKGROUND) as image:
            draw = ImageDraw.Draw(image)
            for index, chunk in enumerate(chunks):
                _draw_section(draw, top=index * (section_height + SECTION_GAP), height=section_height,
                              index=index, sections=len(chunks), chunk=chunk, summary=summary, filters=filters,
                              filter_lines=filter_lines, generated_at=generated_at)
            output = BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
    except (MemoryError, OSError) as exc:
        raise RuntimeError('Không thể tạo ảnh PNG đầy đủ. Hãy thử khoảng ngày ngắn hơn hoặc xuất PDF.') from exc
    finally:
        RENDER_SLOT.release()
