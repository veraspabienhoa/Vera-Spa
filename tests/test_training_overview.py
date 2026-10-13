from io import BytesIO
from datetime import time
from PIL import Image
from pypdf import PdfReader
from vera_web_v2_training_overview import session_seconds, summarize, render_overview


def test_duration_and_summary_do_not_invent_missing_hours_or_scores():
    assert session_seconds(time(9, 15), '10:45:00') == 5400
    assert session_seconds('09:00:30', '10:00:00') == 3570
    for start, end in [('bad', '10:00'), ('10:00', '09:00'), (None, '10:00'), ('09:00', '09:00')]:
        assert session_seconds(start, end) is None
    catalog = [{'username': 'Lan', 'department_code': 'nhanvien'}, {'username': 'Empty', 'department_code': 'nhanvien'}, {'username': 'Support', 'department_code': 'support'}]
    row = {'employee_username': 'LAN', 'start_time': '09:15', 'end_time': '10:45', 'topic': 'Kỹ thuật vai gáy', 'skill_grade': 'A', 'notes': 'Cần luyện thêm'}
    report = summarize(catalog, [row, {**row, 'start_time': None}], [])
    item = report['employees'][0]
    assert item['seconds'] == 5400
    assert item['missing_duration'] == 1
    assert item['summary'].count('Kỹ thuật vai gáy') == 1
    assert 'Chưa có phiếu đã nộp' in item['summary']
    assert [e['username'] for e in report['untrained']] == ['Empty']


def sample_report(long=False):
    return {'employees': [{'employee': {'username': name}, 'seconds': hours * 3600, 'summary': 'Nội dung: Kỹ thuật vai gáy; chăm sóc da\nĐánh giá: Tiến bộ rõ rệt, cần luyện thêm lực tay\n' + ('Nhận xét đầy đủ không cắt nội dung. ' * (180 if long else 1)) + 'KẾT THÚC NHẬN XÉT'} for name, hours in [('Thảo Linh', 6.5), ('Quỳnh Nhi', 3.25), ('Ngọc Như', 0), ('Hải My', 2)]], 'untrained': [{'username': name} for name in ['Gia Hân', 'Bảo Ngọc', 'Lê Thơ', 'Mẫn Nhi']]}


def test_pdf_png_keep_all_employees_and_long_notes():
    report = sample_report(long=True)
    pdf = render_overview(report, 'pdf')
    reader = PdfReader(BytesIO(pdf))
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert len(reader.pages) > 1
    for item in report['employees']:
        assert item['employee']['username'] in text
    for item in report['untrained']:
        assert item['username'] in text
    assert text.count('KẾT THÚC NHẬN XÉT') == 4
    png = Image.open(BytesIO(render_overview(sample_report(), 'png')))
    assert png.width > 1000 and png.height > 1000
