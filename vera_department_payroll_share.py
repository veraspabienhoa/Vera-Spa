"""Printable administrative payroll exports; columns match the Excel workbook."""
from io import BytesIO
from pathlib import Path
from html import escape
import textwrap

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from vera_customer_count_pdf import fonts


def export_values(rows, columns):
    data = [[title for _, title in columns]]
    for row in rows:
        data.append([row.get(key, '') for key, _ in columns])
    totals = [''] * len(columns)
    totals[1] = 'TỔNG'
    for index in range(4, len(columns)):
        totals[index] = sum(float(row.get(columns[index][0]) or 0) for row in rows)
    data.append(totals)
    return data


def display(value):
    if isinstance(value, (int, float)):
        return f'{value:,.2f}'.rstrip('0').rstrip('.').replace(',', '|').replace('.', ',').replace('|', '.')
    return str(value or '')


def payroll_pdf(rows, label, columns):
    regular, bold = fonts()
    output = BytesIO()
    width, _ = landscape(A4)
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=16, rightMargin=16, topMargin=20, bottomMargin=22,
                            title=f'Lương hành chánh {label}', author='VERA SPA')
    normal = ParagraphStyle('PayrollCell', fontName=regular, fontSize=5.7, leading=8, alignment=1)
    total_style = ParagraphStyle('PayrollTotal', parent=normal, fontName=bold)
    heading = ParagraphStyle('PayrollHeading', parent=normal, fontName=bold, textColor=colors.white)
    title = ParagraphStyle('PayrollTitle', fontName=bold, fontSize=12, leading=16, alignment=1)
    data = export_values(rows, columns)
    cells = [[Paragraph(escape(display(value)), heading if ri == 0 else total_style if ri == len(data)-1 else normal) for value in row] for ri, row in enumerate(data)]
    weights = [0.45, 2.0, 1.0] + [1.0] * (len(columns) - 3)
    widths = [(width - 32) * weight / sum(weights) for weight in weights]
    table = Table(cells, colWidths=widths, repeatRows=1, hAlign='CENTER')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#194b3b')),
                              ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#e5f0e9')),
                              ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#5a7668')),
                              ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),3),
                              ('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    def page_number(canvas, document):
        canvas.setFont(regular, 7)
        canvas.drawRightString(width - 16, 10, f'Trang {document.page}')
    doc.build([Paragraph(escape(f'BẢNG LƯƠNG HÀNH CHÁNH THÁNG {label}'),title),Spacer(1,12),table],onFirstPage=page_number,onLaterPages=page_number)
    return output.getvalue()


def payroll_png(rows, label, columns):
    roots = [Path('/usr/share/fonts/truetype/dejavu'),Path('/opt/codex/runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts')]
    root = next((p for p in roots if (p/'DejaVuSans.ttf').exists()),None)
    if root is None:
        raise RuntimeError('Máy chủ cần font DejaVu Sans để xuất ảnh tiếng Việt.')
    font = ImageFont.truetype(str(root/'DejaVuSans.ttf'),18)
    bold = ImageFont.truetype(str(root/'DejaVuSans-Bold.ttf'),20)
    widths = [60,240,150] + [150] * (len(columns) - 3)
    lines = [[textwrap.wrap(display(value),max(4,(widths[i]-12)//11)) or [''] for i,value in enumerate(row)] for row in export_values(rows,columns)]
    heights = [max(len(cell) for cell in row)*26+20 for row in lines]
    image = Image.new('RGB',(sum(widths)+32,sum(heights)+100),'white')
    draw = ImageDraw.Draw(image)
    draw.text((16,20),f'BẢNG LƯƠNG HÀNH CHÁNH THÁNG {label}',font=bold,fill='#194b3b')
    y=80
    for ri,row in enumerate(lines):
        x=16
        for ci,cell in enumerate(row):
            fill='#194b3b' if ri==0 else '#e5f0e9' if ri==len(lines)-1 else 'white'
            draw.rectangle((x,y,x+widths[ci],y+heights[ri]),fill=fill,outline='#5a7668',width=2)
            for li,line in enumerate(cell):
                draw.text((x+6,y+8+li*26),line,font=font,fill='white' if ri==0 else '#17352a')
            x+=widths[ci]
        y+=heights[ri]
    output=BytesIO();image.save(output,format='PNG');return output.getvalue()
