"""Detached, bounded PDF/PNG charts for the full filtered performance ledger."""
from vera_web_v2_training_report_export import (
    _Layout, _fonts, _render_pdf, _render_png, _date, _datetime,
    BODY_WIDTH, MARGIN, GREEN, GOLD, MUTED,
)


def render_performance_report(headers, rows, bounds, file_format):
    fonts = _fonts()
    layout = _Layout('Thời gian thực hiện', png=file_format == 'png')
    layout.paragraph('BÁO CÁO THỜI GIAN THỰC HIỆN', bold=True, size=16)
    dates = [str(row[6])[:10] for row in rows if row[6]]
    start = bounds.get('date') or bounds.get('date_from') or min(dates, default='')
    end = bounds.get('date') or bounds.get('date_to') or max(dates, default='')
    layout.paragraph(f'Từ ngày: {_date(start)} · Đến ngày: {_date(end)}', size=9)
    names = {'employee': 'Nhân viên', 'customer': 'Khách hàng', 'service': 'Dịch vụ', 'bill_no': 'Hóa đơn', 'performance_timing': 'Kết quả'}
    timing = {'all': 'Tất cả', 'early': 'Sớm', 'late': 'Trễ', 'ontime': 'Đúng giờ'}
    for key, label in names.items():
        if bounds.get(key):
            layout.field(label, timing.get(bounds[key], bounds[key]) if key == 'performance_timing' else bounds[key])
    layout.paragraph(f'{len(rows)} dịch vụ · Xanh: quy định · Vàng: thực tế (phút)', size=9, color=MUTED)
    maximum = max([float(value) for row in rows for value in row[7:9] if value is not None] or [1]) or 1
    if not rows:
        layout.paragraph('Không có dữ liệu phù hợp bộ lọc.')
    for index, row in enumerate(rows, 1):
        layout.ensure(190)
        layout.record(f'{index}. {row[0]} · {row[1]} · Phòng {row[2] or "—"}')
        for value, label, color in [(row[7], 'Quy định', GREEN), (row[8], 'Thực tế', GOLD)]:
            layout.ensure(28)
            layout.text(label, MARGIN, layout.y, size=9)
            if value is not None:
                width = max(0, float(value)) / maximum * (BODY_WIDTH - 160)
                layout.rect(MARGIN + 75, layout.y, width, 12, color)
            layout.text('—' if value is None else f'{value} phút', MARGIN + BODY_WIDTH, layout.y, size=9, anchor='right')
            layout.y += 23
        layout.paragraph(f'Kết quả: {row[9] or "—"}', bold=True, size=10)
        layout.paragraph(f'Booking: {_datetime(row[3])} · Xông hơi: {row[10] if row[10] is not None else "—"} phút', size=8)
        layout.paragraph(f'Bắt đầu: {_datetime(row[4] or row[5])} · Hoàn thành: {_datetime(row[6])}', size=8)
        layout.paragraph(f'Tài khoản thực hiện: {row[11] or "—"} · Tài khoản hoàn thành: {row[12] or "—"}', size=8)
    pages = layout.finish()
    replacements = {'BÁO CÁO ĐÀO TẠO & PHÁT TRIỂN': 'BÁO CÁO THỜI GIAN THỰC HIỆN', 'VERA SPA | Báo cáo đào tạo đầy đủ': 'VERA SPA | Thời gian thực hiện'}
    pages = [[(cmd[0], replacements.get(cmd[1], cmd[1]), *cmd[2:]) if cmd[0] == 'text' else cmd for cmd in page] for page in pages]
    return _render_pdf(pages, {'employee': {'full_name': 'Thời gian thực hiện'}}) if file_format == 'pdf' else _render_png(pages, fonts)
