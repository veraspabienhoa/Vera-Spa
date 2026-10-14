"""Residence print template: A4 landscape, one page across, repeated headers."""
from reportlab.lib.pagesizes import A4, landscape
from vera_web_v2_training_report_export import _fonts, _wrap, _render_pdf, _render_png

EXPORT_COLUMNS = [('username','Tên nhân viên'),('full_name','Họ và tên'),
    ('birth_date','Ngày sinh'),('gender','Giới tính'),('cccd_number','Số CCCD'),
    ('cccd_issue_date','Ngày cấp CCCD'),('cccd_issue_place','Nơi cấp CCCD'),('address','Địa chỉ')]
TITLE = 'DANH SÁCH CẬP NHẬT NƠI CƯ TRÚ MỚI CỦA NHÂN VIÊN'
BUSINESS = 'HỘ KINH DOANH VERA'
ADDRESS = 'Địa chỉ: 193 Trương Định, Tam Hiệp, Đồng Nai'
WIDTHS = [28, 70, 114, 66, 42, 90, 66, 95, 235]


def export_rows(records):
    output = []
    for row in records:
        projected = {k: row.get(k, '') for k, _ in EXPORT_COLUMNS}
        if not projected['address']:
            projected['address'] = ', '.join(str(row[k]) for k in
                ('address_detail','ward','district','province') if row.get(k))
        output.append(projected)
    return output


def render_residence(records, columns, format):
    fonts = _fonts()
    size = landscape(A4)
    width, height = size
    left, top, bottom = 18, 54, height - 54
    widths = [n / sum(WIDTHS) * (width - left * 2) for n in WIDTHS]
    fields = [('stt','STT'), *EXPORT_COLUMNS]
    pages = []
    page, y = [], top

    def text(value, x, at, fs=8, bold=False, anchor='left'):
        page.append(('text',str(value),x,at,fs,bold,'#000000',anchor))

    def line(x1,y1,x2,y2):
        page.append(('line',x1,y1,x2,y2,'#000000',.5))

    def row(lines, count, bold=False):
        nonlocal y
        h = count * 11 + 10
        x = left
        for w, values in zip(widths, lines):
            line(x,y,x,y+h)
            for n, value in enumerate(values): text(value,x+4,y+5+n*11,bold=bold)
            x += w
        line(x,y,x,y+h); line(left,y,x,y); line(left,y+h,x,y+h)
        y += h

    def start_page():
        nonlocal page,y
        page=[]; pages.append(page)
        text(BUSINESS,left,top,11,True)
        text(ADDRESS,left,top+17,9)
        text(TITLE,width/2,top+42,12,True,'center')
        y=top+68
        headers=[_wrap(label,w-8,8,True) for (_,label),w in zip(fields,widths)]
        row(headers,max(map(len,headers)),True)

    start_page()
    for i,record in enumerate(export_rows(records),1):
        values=[str(i)]+[str(record[k] or '—') for k,_ in EXPORT_COLUMNS]
        lines=[_wrap(v,w-8,8) for v,w in zip(values,widths)]
        needed=max(map(len,lines))*11+10
        if y+needed>bottom and needed<bottom-(top+110): start_page()
        while any(lines):
            available=int((bottom-y-10)//11)
            if available<1: start_page(); continue
            count=min(available,max(map(len,lines)))
            row([v[:count] for v in lines],count)
            lines=[v[count:] for v in lines]
            if any(lines):
                start_page()
                text(f'Tiếp theo: {record["username"]}',left,top+58,7)
    if y+80>bottom: start_page()
    text('Ngày..........tháng..........năm..........',width-140,y+18,9,False,'center')
    text('Xác nhận của đơn vị',width-140,y+42,10,True,'center')
    for n,p in enumerate(pages,1):
        p.append(('text',f'Trang {n}/{len(pages)}',width-left,height-30,8,False,'#000000','right'))
    return _render_pdf(pages,{'document_title':TITLE},size) if format=='pdf' else _render_png(pages,fonts,size)
