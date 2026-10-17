from io import BytesIO
from PIL import Image
from pypdf import PdfReader
from vera_payroll_print import render_payroll


def test_portrait_grouped_pages_repeat_identity_and_preserve_values():
    cols=[('tt','STT'),('name','Nhân viên')]+[(str(i),f'Khoản {i}') for i in range(7)]
    rows=[{'tt':1,'name':'Ngọc Châu',**{str(i):123456+i for i in range(7)}}]
    pdf=PdfReader(BytesIO(render_payroll(rows,cols,'BẢNG LƯƠNG KTV','pdf')))
    assert len(pdf.pages)==2
    for page in pdf.pages:
        assert abs(float(page.mediabox.width)-595.276)<1
        assert abs(float(page.mediabox.height)-841.89)<1
        assert 'Ngọc Châu' in page.extract_text()
    text=''.join(p.extract_text() for p in pdf.pages)
    for i in range(7): assert f'{123456+i:,}'.replace(',','.') in text
    png=Image.open(BytesIO(render_payroll(rows,cols,'BẢNG LƯƠNG KTV','png')))
    assert png.width==1191 and png.height==3368
