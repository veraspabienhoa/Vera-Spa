from io import BytesIO
from PIL import Image
from pypdf import PdfReader
from vera_payroll_print import render_payroll


def test_landscape_fits_all_columns_and_preserves_values():
    cols=[('tt','STT'),('name','Nhân viên')]+[(str(i),f'Khoản {i}') for i in range(7)]
    rows=[{'tt':1,'name':'Ngọc Châu',**{str(i):123456+i for i in range(7)}}]
    pdf=PdfReader(BytesIO(render_payroll(rows,cols,'BẢNG LƯƠNG KTV','pdf')))
    assert len(pdf.pages)==1
    for page in pdf.pages:
        assert abs(float(page.mediabox.width)-841.89)<1
        assert abs(float(page.mediabox.height)-595.276)<1
        assert 'Ngọc Châu' in page.extract_text()
    text=''.join(p.extract_text() for p in pdf.pages)
    for i in range(7): assert f'{123456+i:,}'.replace(',','.') in text
    png=Image.open(BytesIO(render_payroll(rows,cols,'BẢNG LƯƠNG KTV','png')))
    assert png.width==1684 and png.height==1191


def test_wide_payroll_wraps_headers_and_only_paginates_rows():
    cols = [('tt', 'STT'), ('name', 'Nhân viên')] + [(str(i), f'Khoản phụ cấp {i}') for i in range(17)]
    rows = [{'tt': i+1, 'name': f'Nhân viên {i+1}', **{str(j):12345678 for j in range(17)}} for i in range(60)]
    pdf = PdfReader(BytesIO(render_payroll(rows, cols, 'BẢNG LƯƠNG ' * 12, 'pdf')))
    assert len(pdf.pages) > 1
    text = ''.join(page.extract_text() for page in pdf.pages)
    assert text.count('12.345.678') == 60 * 17
    assert 'Phần 1/' not in text
    for page in pdf.pages:
        assert abs(float(page.mediabox.width)-841.89)<1
        assert 'STT' in page.extract_text()
