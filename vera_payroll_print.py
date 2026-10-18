"""Shared A4 landscape payroll tables; fit all columns within printable width."""
from reportlab.lib.pagesizes import A4, landscape
from fastapi import HTTPException
from vera_web_v2_training_report_export import _fonts, _width, _wrap, _render_pdf, _render_png


def _render_payroll(rows, columns, title, format):
    fonts = _fonts()
    page_size = landscape(A4)
    width, height = page_size
    margin = 30
    pages = []
    def display(v):
        if isinstance(v, (int, float)):
            return f'{v:,.2f}'.rstrip('0').rstrip('.').replace(',', '|').replace('.', ',').replace('|', '.')
        return str(v if v is not None else '')
    groups = [columns]
    for fields in groups:
        weights = [max(0.65, min(2.0, max((len(display(row.get(key, ""))) for row in rows), default=8) / 10)) for key, _ in fields]
        widths = [(width-2*margin)*n/sum(weights) for n in weights]
        size = min(8, 155 / max(len(fields), 1))
        leading = size * 1.35
        padding = 2
        for row in rows:
            for (key, _), cell_width in zip(fields, widths):
                value = row.get(key)
                if isinstance(value, (int, float)):
                    measured = _width(display(value), size, False)
                    if measured > cell_width-2*padding:
                        size *= (cell_width-2*padding-0.1) / measured
        leading = size * 1.35
        page = []; y = 0
        def text(value, x, yy, bold=False, size=size):
            page.append(('text', value, x, yy, size, bold, '#173f2e', 'left'))
        def draw(values, bold=False):
            nonlocal y
            wrapped = [_wrap(display(v), w-2*padding, size, bold) for v,w in zip(values,widths)]
            h = max(map(len,wrapped))*leading+8
            x = margin
            for lines,w in zip(wrapped,widths):
                if bold: page.append(('rect',x,y,w,h,'#e5f0e9'))
                for k,line in enumerate(lines): text(line,x+padding,y+4+k*leading,bold)
                page.append(('line',x,y,x,y+h,'#5a7668',.5)); x+=w
            page.extend([('line',x,y,x,y+h,'#5a7668',.5),('line',margin,y,x,y,'#5a7668',.5),('line',margin,y+h,x,y+h,'#5a7668',.5)])
            y += h
        def start():
            nonlocal page,y
            page=[];pages.append(page);y=50
            text('VERA SPA',margin,30,True,13)
            for line in _wrap(title, width-2*margin, 10, True):
                text(line, margin, y, True, 10)
                y += 14
            y += 10
            draw([label for _,label in fields],True)
        start()
        for row in rows:
            values=[row.get(key,'') for key,_ in fields]
            needed=max(len(_wrap(display(v),w-2*padding,size)) for v,w in zip(values,widths))*leading+8
            if needed > height-200:
                raise HTTPException(400, "Nội dung một ô quá dài để in A4. Vui lòng rút gọn dữ liệu.")
            if y+needed>height-margin-20: start()
            draw(values)
    for n,page in enumerate(pages,1):
        page.append(('text',f'Trang {n}/{len(pages)}',width-margin,height-22,8,False,'#173f2e','right'))
    return _render_pdf(pages,{'document_title':title},page_size) if format=='pdf' else _render_png(pages,fonts,page_size)


def render_payroll(rows, columns, title, format):
    from vera_web_v2_training_report_export import ReportExportTooLarge, ReportExportUnavailable
    try:
        return _render_payroll(rows, columns, title, format)
    except ReportExportTooLarge as exc:
        raise HTTPException(400, str(exc)) from exc
    except ReportExportUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
