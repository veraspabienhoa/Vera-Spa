"""Complete paginated residence tables from the authorized, bank-free projection."""
from vera_web_v2_training_report_export import (
    _fonts, _wrap, _render_pdf, _render_png, PAGE_WIDTH, PAGE_HEIGHT,
)


def render_residence(records, columns, format):
    fonts = _fonts()
    pages = []
    width = PAGE_WIDTH - 64
    groups = [columns[1:][i:i + 4] for i in range(0, len(columns) - 1, 4)]
    for group_index, group in enumerate(groups, 1):
        fields = [columns[0], *group]
        cell_width = width / len(fields)
        page = []
        y = 0

        def text(value, x, top, size=9, bold=False):
            page.append(('text', value, x, top, size, bold, '#173d2f', 'left'))

        def line(x1, y1, x2, y2):
            page.append(('line', x1, y1, x2, y2, '#879c98', .6))

        def draw_row(lines, height, header=False):
            nonlocal y
            if header:
                page.append(('rect', 32, y, width, height, '#e3efeb'))
            for index, values in enumerate(lines):
                x = 32 + index * cell_width
                line(x, y, x, y + height)
                for offset, value in enumerate(values):
                    text(value, x + 5, y + 5 + offset * 12, bold=header)
            line(32 + width, y, 32 + width, y + height)
            line(32, y, 32 + width, y)
            y += height
            line(32, y, 32 + width, y)

        def start_page():
            nonlocal page, y
            page = []
            pages.append(page)
            text('VERA SPA · DANH SÁCH TẠM TRÚ', 32, 24, 14, True)
            text(f'{len(records)} nhân viên · Nhóm thông tin {group_index}/{len(groups)}', 32, 46)
            y = 70
            headers = [_wrap(label, cell_width - 10, 9, True) for _, label in fields]
            draw_row(headers, max(map(len, headers)) * 12 + 10, True)

        start_page()
        if not records:
            text('Chưa có nhân viên tạm trú phù hợp.', 32, y + 12)
        for record in records:
            values = [_wrap(str(record.get(key, '') or '—'), cell_width - 10, 9) for key, _ in fields]
            # Split exceptionally long profile fields across pages without clipping.
            while any(values):
                available = int((PAGE_HEIGHT - 44 - y - 10) // 12)
                if available < 1:
                    start_page()
                    continue
                count = min(max(map(len, values)), available)
                draw_row([v[:count] for v in values], count * 12 + 10)
                values = [v[count:] for v in values]
                if any(values):
                    start_page()
                    text(f"Tiếp theo: {record.get('username', '')}", 32, 58, 8)
    for number, page in enumerate(pages, 1):
        page.append(('text', f'Trang {number}/{len(pages)}', PAGE_WIDTH - 32,
                     PAGE_HEIGHT - 28, 8, False, '#62766c', 'right'))
    if format == 'pdf':
        return _render_pdf(pages, {'document_title': 'VERA SPA - Danh sách tạm trú'})
    return _render_png(pages, fonts)
