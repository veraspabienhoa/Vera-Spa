"""Read-only customer counts: one matching invoice is one customer visit."""
from calendar import monthrange
from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart

VN = ZoneInfo('Asia/Ho_Chi_Minh')
FONT_LOCK = Lock()


def invoice_day(row):
    # Share the report screen's Vietnam calendar and legacy date semantics.
    from vera_live_tour_query import _report_day
    return _report_day(row.get('effective_at') or row.get('business_date'))


def customer_counts(rows, *, date_from='', date_to=''):
    visits, missing_id = {}, 0
    for row in rows:
        identity = str(row.get('invoice_id') or row.get('bill_no') or '').strip()
        if not identity:
            missing_id += 1
            continue
        day = invoice_day(row)
        # Deterministic deduplication even if legacy lines disagree on dates.
        if identity not in visits or day and (not visits[identity] or day < visits[identity]):
            visits[identity] = day
    counts = Counter(visits.values())
    days = sorted(day for day in counts if day)
    start, end = date_from or (days[0] if days else ''), date_to or (days[-1] if days else '')
    if start and end:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if (last - first).days <= 3660:
            day = first
            while day <= last:
                counts.setdefault(day.isoformat(), 0)
                day += timedelta(days=1)
    daily = [(day, counts[day]) for day in sorted(counts) if day]
    if counts.get(''):
        daily.append(('', counts['']))
    return {'daily': daily, 'total': len(visits), 'missing_id_rows': missing_id,
            'undated': counts.get('', 0)}


def fonts():
    with FONT_LOCK:
        if 'VeraCount' in pdfmetrics.getRegisteredFontNames():
            return 'VeraCount', 'VeraCountBold'
        roots = [Path('/usr/share/fonts/truetype/dejavu'),
                 Path('/opt/codex/runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts')]
        for root in roots:
            regular, bold = root / 'DejaVuSans.ttf', root / 'DejaVuSans-Bold.ttf'
            if regular.exists() and bold.exists():
                pdfmetrics.registerFont(TTFont('VeraCount', str(regular)))
                pdfmetrics.registerFont(TTFont('VeraCountBold', str(bold)))
                return 'VeraCount', 'VeraCountBold'
    raise RuntimeError('Máy chủ cần font DejaVu Sans để xuất PDF tiếng Việt.')


def customer_count_pdf(summary, filters, *, generated_at=None):
    regular, bold = fonts()
    output = BytesIO()
    width, height = landscape(A4)
    doc = SimpleDocTemplate(output, pagesize=(width, height), leftMargin=32, rightMargin=32,
                            topMargin=28, bottomMargin=34, title='VERA SPA - Báo cáo số lượng khách', author='VERA SPA')
    usable = width - 64
    green, pale, blue = colors.HexColor('#194b3b'), colors.HexColor('#edf5f0'), colors.HexColor('#4f81bd')
    style = ParagraphStyle('CountBody', fontName=regular, fontSize=9, leading=13, textColor=green)
    title = ParagraphStyle('CountTitle', parent=style, fontName=bold, fontSize=19, leading=25)
    small = ParagraphStyle('CountSmall', parent=style, fontSize=8, leading=11)
    display_day = lambda value: date.fromisoformat(value).strftime('%d-%m-%Y') if value else 'Không rõ ngày'
    start, end = filters.get('date_from') or '', filters.get('date_to') or ''
    scope = f"{display_day(start) if start else 'Tất cả'} đến {display_day(end) if end else 'Tất cả'}"
    descriptions = [f'{label}: {filters[key]}' for key, label in
                    [('date', 'Ngày'), ('employee', 'Nhân viên'), ('customer', 'Khách hàng'),
                     ('service', 'Dịch vụ'), ('bill_no', 'Số hóa đơn'), ('total_amount', 'Tổng tiền')]
                    if filters.get(key) not in (None, '')]
    if filters.get('date'):
        descriptions[0] = f"Ngày: {display_day(filters['date'])}"
    daily = summary['daily']
    monthly = bool(start and end and start.endswith('-01')
                   and date.fromisoformat(end).day == monthrange(date.fromisoformat(end).year, date.fromisoformat(end).month)[1])
    if monthly:
        groups = {}
        for day, count in daily:
            groups.setdefault(day[:7], []).append((day, count))
        chunks = list(groups.values()) or [[]]
    else:
        chunks = [daily[i:i + 14] for i in range(0, len(daily), 14)] or [[]]
    generated_at = generated_at or datetime.now(VN)
    filter_paragraph = Paragraph(escape(' | '.join(descriptions) or 'Các bộ lọc khác: Tất cả'), small)
    _, filter_height = filter_paragraph.wrap(usable, height)
    chart_height = max(90, 185 - max(0, filter_height - 22))
    story = []
    for index, chunk in enumerate(chunks):
        if index:
            story.append(PageBreak())
        story.extend([Paragraph('VERA SPA | SỐ LƯỢNG KHÁCH', title),
                      Paragraph(escape(f'Theo bộ lọc: {scope}'), style),
                      Paragraph(escape(' | '.join(descriptions) or 'Các bộ lọc khác: Tất cả'), small), Spacer(1, 10)])
        page_daily = chunk if monthly else daily
        page_total = sum(count for _, count in chunk) if monthly else summary['total']
        if monthly and chunk:
            month_label = date.fromisoformat(chunk[0][0]).strftime('%m-%Y') if chunk[0][0] else 'Không rõ ngày'
            story.extend([Paragraph(f'Tháng {month_label}', style), Spacer(1, 4)])
        summary_table = Table([[Paragraph('TỔNG KHÁCH (SỐ HÓA ĐƠN)', small), Paragraph('NGÀY CÓ KHÁCH', small), Paragraph('CAO NHẤT / NGÀY', small)],
                               [str(page_total), str(sum(count > 0 for day, count in page_daily if day)), str(max((count for day, count in page_daily if day), default=0))]],
                              colWidths=[usable / 3] * 3)
        summary_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), pale), ('FONTNAME', (0, 1), (-1, 1), bold),
                                          ('FONTSIZE', (0, 1), (-1, 1), 19), ('TEXTCOLOR', (0, 0), (-1, -1), green),
                                          ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story.extend([summary_table, Spacer(1, 12), Paragraph('Một hóa đơn = một lượt khách; mỗi hóa đơn chỉ được tính một lần.', small), Spacer(1, 8)])
        if chunk:
            chart = VerticalBarChart()
            chart.x, chart.y, chart.width, chart.height = 35, 32, usable - 55, chart_height
            chart.data = [[count for _, count in chunk]]
            chart.categoryAxis.categoryNames = [day[-2:] if monthly and day else display_day(day) if day else 'Không rõ' for day, _ in chunk]
            chart.categoryAxis.labels.fontName = regular
            chart.categoryAxis.labels.fontSize = 6.5
            chart.valueAxis.labels.fontName = regular
            chart.valueAxis.labels.fontSize = 8
            chart.valueAxis.valueMin = 0
            maximum = max(count for _, count in chunk)
            step = max(1, (maximum + 4) // 5)
            chart.valueAxis.valueMax = max(5, step * 6)
            chart.valueAxis.valueStep = step
            chart.valueAxis.visibleGrid = True
            chart.valueAxis.gridStrokeColor = colors.HexColor('#dbe4df')
            chart.bars[0].fillColor, chart.bars[0].strokeColor = blue, blue
            chart.barLabelFormat = '%d'
            chart.barLabels.fontName, chart.barLabels.fontSize = bold, 8
            chart.barLabels.nudge = 5
            drawing = Drawing(usable, chart_height + 45)
            drawing.add(chart)
            story.append(drawing)
            # Two compact rows of dates keep all 28–31 days legible on one page.
            parts = [chunk[i:i + 16] for i in range(0, len(chunk), 16)] if monthly else [chunk]
            columns = max(len(part) for part in parts)
            cells = []
            for part in parts:
                padding = [''] * (columns - len(part))
                cells.extend([['Ngày'] + [day[-2:] if monthly and day else display_day(day) for day, _ in part] + padding + ['Cộng'],
                              ['Số khách'] + [str(count) for _, count in part] + padding + [str(sum(count for _, count in part))]])
            table = Table(cells, colWidths=[55] + [(usable - 120) / columns] * columns + [65])
            table.setStyle(TableStyle([('FONTNAME', (0, 0), (-1, -1), regular),
                                      ('FONTSIZE', (0, 0), (-1, -1), 7), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                      ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#c8d9cf')),
                                      ('ROWBACKGROUNDS', (0, 0), (-1, -1), [pale, colors.white]),
                                      ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
            story.append(table)
        else:
            story.append(Paragraph('Không có hóa đơn khớp bộ lọc.', style))
        if summary['missing_id_rows']:
            story.extend([Spacer(1, 8), Paragraph(f"Có {summary['missing_id_rows']} dòng thiếu mã hóa đơn, không đưa vào số khách.", small)])
    def footer(canvas, _doc):
        canvas.setFont(regular, 8)
        canvas.setFillColor(green)
        canvas.drawString(32, 18, f"Lập lúc {generated_at.astimezone(VN).strftime('%d-%m-%Y %H:%M')} | Theo dữ liệu đã thanh toán")
        canvas.drawRightString(width - 32, 18, f'Trang {canvas.getPageNumber()} / {len(chunks)}')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
