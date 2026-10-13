from io import BytesIO
from PIL import Image
from pypdf import PdfReader
from vera_performance_report_export import render_performance_report


def test_pdf_a4_and_png_include_filters_actors_dates_and_every_row():
    row=['Thảo Linh','90 Tiêu chuẩn','10.1','2026-10-13T09:55:00+07:00','2026-10-13T10:00:00+07:00','','2026-10-13T11:25:00+07:00',90,85,'Sớm 5 phút',5,'reception.start','reception.finish']
    rows=[row for _ in range(12)]
    bounds={'date_from':'2026-10-13','date_to':'2026-10-13','performance_timing':'early'}
    reader=PdfReader(BytesIO(render_performance_report([],rows,bounds,'pdf')))
    text='\n'.join(page.extract_text() for page in reader.pages)
    assert text.count('reception.start')==12 and text.count('reception.finish')==12
    assert '13-10-2026' in text and 'Kết quả: Sớm' in text
    assert 'BÁO CÁO ĐÀO TẠO' not in text
    assert abs(float(reader.pages[0].mediabox.width)-595.28)<1
    image=Image.open(BytesIO(render_performance_report([],rows[:1],bounds,'png')))
    assert image.width>1000 and image.height>1000
