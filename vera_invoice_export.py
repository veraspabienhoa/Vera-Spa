"""Customer-facing invoice rows, without bank or payment QR data."""
from io import BytesIO
from pathlib import Path
from threading import Lock

BRAND_FONT = Path(__file__).parent / "web-v2/public/fonts/CinzelDecorative-Black.ttf"
BRAND_LOCK = Lock()
from xml.sax.saxutils import escape
from pydantic import BaseModel, Field, model_validator
from vera_web_v2_live_tour_payment import service_subtotal

class InvoiceExportRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=50)
    service: bool = True
    tip: bool = True
    preset: str = 'today'
    date_from: str = ''
    date_to: str = ''

    @model_validator(mode='after')
    def validate_selection(self):
        if not self.service and not self.tip:
            raise ValueError('Chọn Dịch vụ hoặc Tiền tip.')
        if len(set(self.ids)) != len(self.ids) or any(not key or len(key)>160 for key in self.ids):
            raise ValueError('Danh sách hóa đơn không hợp lệ.')
        return self

def invoice_rows(invoices, service, tip, display_date):
    headers = ['STT', 'Dịch vụ' if service else 'Nội dung', 'Thành tiền']
    rows = []
    totals = [0, 0, 0, 0]
    money = lambda value: f'{value:,.0f}'.replace(',', '.') + ' đ'
    for index, inv in enumerate(invoices, 1):
        subtotal, discount, tips = float(service_subtotal(inv)), float(inv.get('discount') or 0), float(inv.get('tip') or 0)
        total = float(inv.get('total') or 0) if service and tip else (float(inv.get('total') or 0)-tips if service else tips)
        totals = [a+b for a,b in zip(totals, (subtotal, discount, tips, total))]
        # Explicit service fields only: never include employee or room metadata.
        labels = [str(e.get('service') or '') for e in inv.get('entries', [])]
        label = ' · '.join(filter(None, labels)) or str(inv.get('service') or inv.get('services') or 'Dịch vụ')
        rows.append([str(index), label if service else 'Tiền tip', money(total)])
    if tip: rows.append(['', 'Tiền tip', money(totals[2])])
    rows.append(['', 'Tổng tiền', money(totals[3])])
    return headers, rows

def invoice_date_label(invoices):
    from datetime import date
    from vera_live_tour_query import _report_day
    days = sorted({day for row in invoices if (day := _report_day(row.get('effective_at') or row.get('business_date')))})
    if not days:
        return 'Ngày —'
    labels = [date.fromisoformat(day).strftime('%d-%m-%Y') for day in (days[0], days[-1])]
    return 'Ngày ' + (labels[0] if days[0] == days[-1] else ' – '.join(labels))


def _signature_italic_path():
    roots = [Path('/usr/share/fonts/truetype/dejavu'),
             Path('/opt/codex/runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts')]
    for name in ('DejaVuSans-Oblique.ttf', 'DejaVuSansMono-Oblique.ttf'):
        for root in roots:
            candidate = root / name
            if candidate.is_file():
                return candidate
    raise RuntimeError('Máy chủ cần font DejaVu nghiêng để xuất chữ ký tiếng Việt.')


def render_invoice_export(headers, rows, format, date_label="Ngày —"):
    if format == 'pdf':
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import inch
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from vera_customer_count_pdf import fonts
        normal, bold = fonts()
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        with BRAND_LOCK:
            if 'VeraInvoiceBrand' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('VeraInvoiceBrand', str(BRAND_FONT)))
            if 'VeraInvoiceItalic' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('VeraInvoiceItalic', str(_signature_italic_path())))
        style = ParagraphStyle('InvoiceRow', fontName=normal, fontSize=8, leading=11)
        out = BytesIO()
        doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=.7*inch, rightMargin=.7*inch, topMargin=.75*inch, bottomMargin=.75*inch)
        header_style = ParagraphStyle('InvoiceHeader', parent=style, fontName=bold, alignment=1)
        center_style = ParagraphStyle('InvoiceCenter', parent=style, alignment=1)
        cells = [[Paragraph(escape(str(v)), header_style if index == 0 else center_style if c in (0, 2) else style)
                  for c, v in enumerate(row)] for index, row in enumerate([headers, *rows])]
        cells[-1] = [Paragraph(escape(str(rows[-1][1])), header_style), '', Paragraph(escape(str(rows[-1][2])), header_style)]
        table = Table(cells, colWidths=[doc.width*.1, doc.width*.6, doc.width*.3], repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([('SPAN',(0,-1),(1,-1)),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#37634f')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#c8dcd1')),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#edf3ef')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        from reportlab.platypus import KeepTogether
        brand_style = ParagraphStyle('Brand', parent=style, alignment=1, fontSize=28, leading=38, textColor=colors.HexColor('#173e32'))
        address_style = ParagraphStyle('Address', parent=style, alignment=1, fontName=bold, fontSize=10, leading=18)
        title_style = ParagraphStyle('InvoiceTitle', parent=style, alignment=1, fontName=bold, fontSize=16, leading=26)
        signature_style = ParagraphStyle('Signature', parent=style, alignment=1, fontName=bold, fontSize=12, leading=18)
        signature_hint = ParagraphStyle('SignatureHint', parent=style, alignment=1, fontName='VeraInvoiceItalic', fontSize=8, leading=14)
        signature = Table([['', Paragraph('Vera Spa', signature_style)],
                           ['', Paragraph('Ký ghi rõ họ tên', signature_hint)]],
                          colWidths=[doc.width*.7, doc.width*.3])
        signature.setStyle(TableStyle([('LEFTPADDING',(0,0),(-1,-1),0), ('RIGHTPADDING',(0,0),(-1,-1),0)]))
        doc.build([Paragraph('<font name="VeraInvoiceBrand">VERA SPA</font>', brand_style),
                   Paragraph('193 Trương Định, Tam Hiệp, Đồng Nai', address_style),
                   Spacer(1,12), Paragraph('HÓA ĐƠN DỊCH VỤ', title_style),
                   Paragraph(escape(date_label), center_style), Spacer(1,16), table,
                   KeepTogether([Spacer(1,20), signature, Spacer(1,64)])])
        return out.getvalue()
    from PIL import Image, ImageDraw, ImageFont
    from vera_customer_count_png import _font, _wrap
    width = 1600
    pixels_per_inch = width / (210 / 25.4)
    margin = round(.7 * pixels_per_inch)
    vertical_margin = round(.75 * pixels_per_inch)
    widths = [(width-2*margin)*part for part in (.1,.6,.3)]
    font = _font(18)
    header_font = _font(18, True)
    wrapped = [[_wrap(str(v),header_font if index in (0,len(rows)) else font,widths[c]-16) for c,v in enumerate(row)] for index,row in enumerate([headers,*rows])]
    heights = [max(len(v) for v in row)*25+20 for row in wrapped]
    height = 2*vertical_margin+370+sum(heights)
    if height>20000 or width*height>32000000: raise ValueError('Ảnh quá dài. Hãy chọn ít hóa đơn hơn hoặc tải PDF.')
    img=Image.new('RGB',(width,height),'white'); draw=ImageDraw.Draw(img)
    brand_font = ImageFont.truetype(str(BRAND_FONT), 48)
    draw.text((width/2,vertical_margin+43),'VERA SPA',font=brand_font,fill='#173e32',anchor='ms')
    draw.text((width/2,vertical_margin+78),'193 Trương Định, Tam Hiệp, Đồng Nai',font=header_font,fill='#173e32',anchor='mm')
    draw.text((width/2,vertical_margin+145),'HÓA ĐƠN DỊCH VỤ',font=_font(30,True),fill='#173e32',anchor='mm')
    draw.text((width/2,vertical_margin+184),date_label,font=font,fill='#173e32',anchor='mm')
    y=vertical_margin+215
    for index,(row,h) in enumerate(zip(wrapped,heights)):
        if index == len(wrapped)-1:
            split = margin+sum(widths[:2])
            draw.rectangle((margin,y,split,y+h),fill='#edf3ef',outline='#37634f')
            draw.rectangle((split,y,width-margin,y+h),fill='#edf3ef',outline='#37634f')
            draw.text(((margin+split)/2,y+10),str(rows[-1][1]),font=header_font,fill='#173e32',anchor='mt')
            for line_index,line in enumerate(row[2]):
                draw.text(((split+width-margin)/2,y+10+line_index*25),line,font=header_font,fill='#173e32',anchor='mt')
            y+=h
            continue
        for c,lines in enumerate(row):
            x=margin+sum(widths[:c])
            draw.rectangle((x,y,x+widths[c],y+h),fill='#c8dcd1' if index == 0 else 'white',outline='#37634f')
            cell_font = header_font if index == 0 else font
            centered = index == 0 or c in (0, 2)
            for line_index,line in enumerate(lines):
                draw.text((x+widths[c]/2 if centered else x+8,y+10+line_index*25),line,
                          font=cell_font,fill='#173e32',anchor='mt' if centered else 'lt')
        y+=h
    signature_x=margin+sum(widths[:2])+widths[2]/2
    draw.text((signature_x,y+35),'Vera Spa',font=_font(26,True),fill='#173e32',anchor='mt')
    draw.text((signature_x,y+76),'Ký ghi rõ họ tên',font=ImageFont.truetype(str(_signature_italic_path()),18),fill='#173e32',anchor='mt')
    out=BytesIO();img.save(out,format='PNG');return out.getvalue()
