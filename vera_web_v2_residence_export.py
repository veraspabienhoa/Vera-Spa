"""Residence print template: A4 landscape, one page across, repeated headers."""
from reportlab.lib.pagesizes import A4, landscape
from vera_web_v2_training_report_export import _fonts, _wrap, _render_pdf, _render_png, FONT_ROOTS, _FONT_LOCK
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

EXPORT_COLUMNS = [('username','Tên nhân viên'),('full_name','Họ và tên'),
    ('birth_date','Ngày sinh'),('gender','Giới tính'),('cccd_number','Số CCCD'),
    ('cccd_issue_date','Ngày cấp CCCD'),('cccd_issue_place','Nơi cấp CCCD'),('address','Địa chỉ')]
TITLE = 'DANH SÁCH NHÂN VIÊN ĐĂNG KÝ TẠM TRÚ'
LABOR_TITLE = 'DANH SÁCH CƠ SỞ KHAI TRÌNH SỬ DỤNG LAO ĐỘNG'
NATIONAL = 'CÔNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM'
MOTTO = 'ĐỘC LẬP - TỰ DO - HẠNH PHÚC'
INDUSTRY = 'Nghành nghề kinh doanh: Gội đầu, xoa bóp'
LABOR_COLUMNS = [*EXPORT_COLUMNS, ('hourly_salary', 'Mức lương\n(giờ)'),
    ('job_title', 'Công việc đang làm'), ('contract_signed', 'Ngày ký hợp đồng'),
    ('contract_end', 'Ngày hết hợp đồng')]
BUSINESS = 'HỘ KINH DOANH VERA'
ADDRESS = 'Địa chỉ: 193 Trương Định, Tam Hiệp, Đồng Nai'
WIDTHS = [5.57, 14, 22.855, 13.14, 8.425, 18, 13.14, 19, 47]
LABOR_WIDTHS = [30, 52, 75, 58, 32, 70, 58, 79, 128, 48, 57, 58, 58]


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
    return render_roster(records, format)


def render_roster(records, format, *, labor=False):
    fonts = _fonts()
    serif = [next((root / name for root in FONT_ROOTS if (root / name).is_file()), None)
             for name in ('DejaVuSerif.ttf', 'DejaVuSerif-Bold.ttf')]
    font_names = None
    if all(serif):
        fonts = tuple(serif); font_names = ('VeraRosterSerif', 'VeraRosterSerifBold')
        with _FONT_LOCK:
            for name,path in zip(font_names,fonts):
                if name not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(name,str(path)))
    size = landscape(A4)
    width, height = size
    left, top, bottom = 18, 54, height - 54
    weights = LABOR_WIDTHS if labor else WIDTHS
    columns = LABOR_COLUMNS if labor else EXPORT_COLUMNS
    title = LABOR_TITLE if labor else TITLE
    widths = [n / sum(weights) * (width - left * 2) for n in weights]
    fields = [('stt','STT'), *columns]
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
        for column_index, (w, values) in enumerate(zip(widths, lines)):
            line(x,y,x,y+h)
            centered = bold or column_index in {0,3,4,5,6,9,11,12}
            start_y = y + (h-len(values)*11)/2
            for n, value in enumerate(values): text(value,x+w/2 if centered else x+4,start_y+n*11,bold=bold,anchor='center' if centered else 'left')
            x += w
        line(x,y,x,y+h); line(left,y,x,y); line(left,y+h,x,y+h)
        y += h

    def start_page():
        nonlocal page,y
        page=[]; pages.append(page)
        text(BUSINESS,left,top,11,True)
        text(ADDRESS,left,top+17,9)
        text(INDUSTRY,left,top+34,9)
        text(NATIONAL,width/2,top+51,9,True,'center')
        text(MOTTO,width/2,top+68,9,True,'center')
        text(title,width/2,top+91,12,True,'center')
        y=top+117
        headers=[_wrap(label,w-8,8,True,font_names=font_names) for (_,label),w in zip(fields,widths)]
        row(headers,max(map(len,headers)),True)

    start_page()
    projected = export_rows(records)
    if labor:
        projected = [{**base, **{key: source.get(key, '') for key, _ in LABOR_COLUMNS[len(EXPORT_COLUMNS):]}} for base,source in zip(projected,records)]
    for i,record in enumerate(projected,1):
        values=[str(i)]+[str(record.get(k) if record.get(k) is not None else '') for k,_ in columns]
        lines=[_wrap(v or ' ',w-8,8,font_names=font_names) for v,w in zip(values,widths)]
        needed=max(map(len,lines))*11+10
        if y+needed>bottom and needed<bottom-(top+164): start_page()
        while any(lines):
            available=int((bottom-y-10)//11)
            if available<1: start_page(); continue
            count=min(available,max(map(len,lines)))
            row([v[:count] for v in lines],count)
            lines=[v[count:] for v in lines]
            if any(lines):
                start_page()
                text(f'Tiếp theo: {record["username"]}',left,top+107,7)
    if y+(100 if labor else 80)>bottom: start_page()
    text('Ngày..........tháng..........năm..........',width-140,y+18,9,False,'center')
    text('Xác nhận của đơn vị',width-140,y+42,10,True,'center')
    if labor:
        for offset,value in enumerate(('Số…../XN-TB.TBXH', 'Phòng lao động - TBXH TP Biên Hòa', 'Cơ sở đăng ký:…..HĐLĐ (…….Nam/…….Nữ)', 'Biên Hòa, ngày…..tháng…..năm…..', 'Trưởng phòng')):
            text(value,left+140,y+18+offset*15,9,bold=offset in {1,4})
    for n,p in enumerate(pages,1):
        p.append(('text',f'Trang {n}/{len(pages)}',width-left,height-30,8,False,'#000000','right'))
    return _render_pdf(pages,{'document_title':title},size,font_names=font_names) if format=='pdf' else _render_png(pages,fonts,size)
