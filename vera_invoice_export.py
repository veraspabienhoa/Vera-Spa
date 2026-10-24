"""Customer-facing invoice rows, without bank or payment QR data."""
from io import BytesIO
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
    if service:
        rows += [['', 'Tiền dịch vụ', money(totals[0])], ['', 'Giảm giá', money(totals[1])]]
    if tip: rows.append(['', 'Tiền tip', money(totals[2])])
    rows.append(['', 'Tổng tiền', money(totals[3])])
    return headers, rows

def render_invoice_export(headers, rows, format):
    if format == 'pdf':
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from vera_customer_count_pdf import fonts
        normal, bold = fonts()
        style = ParagraphStyle('InvoiceRow', fontName=normal, fontSize=8, leading=11)
        out = BytesIO()
        doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
        cells = [[Paragraph(escape(str(v)), style) for v in row] for row in [headers, *rows]]
        table = Table(cells, colWidths=[doc.width*.1, doc.width*.6, doc.width*.3], repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#37634f')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf3ef')),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#edf3ef')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        doc.build([Paragraph('VERA SPA · HÓA ĐƠN DỊCH VỤ', ParagraphStyle('Title',parent=style,fontName=bold,fontSize=18,leading=24)), Paragraph('193 Trương Định, Tam Hiệp, Đồng Nai',style), Spacer(1,16),table])
        return out.getvalue()
    from PIL import Image, ImageDraw
    from vera_customer_count_png import _font, _wrap
    width, margin = 1600, 32
    widths = [(width-2*margin)*part for part in (.1,.6,.3)]
    font = _font(18)
    wrapped = [[_wrap(str(v),font,widths[c]-16) for c,v in enumerate(row)] for row in [headers,*rows]]
    heights = [max(len(v) for v in row)*25+20 for row in wrapped]
    height = 140+sum(heights)
    if height>20000 or width*height>32000000: raise ValueError('Ảnh quá dài. Hãy chọn ít hóa đơn hơn hoặc tải PDF.')
    img=Image.new('RGB',(width,height),'white'); draw=ImageDraw.Draw(img)
    draw.text((margin,24),'VERA SPA · HÓA ĐƠN DỊCH VỤ',font=_font(30,True),fill='#173e32')
    draw.text((margin,70),'193 Trương Định, Tam Hiệp, Đồng Nai',font=font,fill='#173e32')
    y=110
    for index,(row,h) in enumerate(zip(wrapped,heights)):
        for c,lines in enumerate(row):
            x=margin+sum(widths[:c])
            draw.rectangle((x,y,x+widths[c],y+h),fill='#edf3ef' if index in (0,len(wrapped)-1) else 'white',outline='#37634f')
            for line_index,line in enumerate(lines): draw.text((x+8,y+10+line_index*25),line,font=font,fill='#173e32')
        y+=h
    out=BytesIO();img.save(out,format='PNG');return out.getvalue()
