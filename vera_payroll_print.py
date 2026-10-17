"""Shared A4 portrait payroll tables; repeat identity across column groups."""
from reportlab.lib.pagesizes import A4
from fastapi import HTTPException
from vera_web_v2_training_report_export import _fonts, _wrap, _render_pdf, _render_png


def _render_payroll(rows, columns, title, format):
    fonts = _fonts()
    width, height = A4
    margin = 30
    pages = []
    def display(v):
        if isinstance(v, (int, float)):
            return f'{v:,.2f}'.rstrip('0').rstrip('.').replace(',', '|').replace('.', ',').replace('|', '.')
        return str(v if v is not None else '')
    groups = [columns[:2] + columns[i:i+4] for i in range(2, len(columns), 4)] or [columns]
    for part, fields in enumerate(groups, 1):
        weights = [0.45, 1.7] + [1.3] * (len(fields)-2)
        widths = [(width-2*margin)*n/sum(weights) for n in weights]
        page = []; y = 0
        def text(value, x, yy, bold=False, size=8):
            page.append(('text', value, x, yy, size, bold, '#173f2e', 'left'))
        def draw(values, bold=False):
            nonlocal y
            wrapped = [_wrap(display(v), w-8, 8, bold) for v,w in zip(values,widths)]
            h = max(map(len,wrapped))*11+12
            x = margin
            for lines,w in zip(wrapped,widths):
                if bold: page.append(('rect',x,y,w,h,'#e5f0e9'))
                for k,line in enumerate(lines): text(line,x+4,y+6+k*11,bold)
                page.append(('line',x,y,x,y+h,'#5a7668',.5)); x+=w
            page.extend([('line',x,y,x,y+h,'#5a7668',.5),('line',margin,y,x,y,'#5a7668',.5),('line',margin,y+h,x,y+h,'#5a7668',.5)])
            y += h
        def start():
            nonlocal page,y
            page=[];pages.append(page);y=85
            text('VERA SPA',margin,30,True,13)
            text(title,margin,50,True,10)
            text(f'Phần {part}/{len(groups)}',margin,67)
            draw([label for _,label in fields],True)
        start()
        for row in rows:
            values=[row.get(key,'') for key,_ in fields]
            needed=max(len(_wrap(display(v),w-8,8)) for v,w in zip(values,widths))*11+12
            if needed > height-200:
                raise HTTPException(400, "Nội dung một ô quá dài để in A4. Vui lòng rút gọn dữ liệu.")
            if y+needed>height-margin-20: start()
            draw(values)
    for n,page in enumerate(pages,1):
        page.append(('text',f'Trang {n}/{len(pages)}',width-margin,height-22,8,False,'#173f2e','right'))
    return _render_pdf(pages,{'document_title':title},A4) if format=='pdf' else _render_png(pages,fonts,A4)


def render_payroll(rows, columns, title, format):
    from vera_web_v2_training_report_export import ReportExportTooLarge, ReportExportUnavailable
    try:
        return _render_payroll(rows, columns, title, format)
    except ReportExportTooLarge as exc:
        raise HTTPException(400, str(exc)) from exc
    except ReportExportUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
