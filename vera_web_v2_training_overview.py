"""All-time training overview, built only from the authorized active roster."""
from collections import Counter
from datetime import time, datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from sqlalchemy import bindparam, text

from vera_web_v2_training_report_export import (
    _Layout, _fonts, _wrap, _render_pdf, _render_png,
    MARGIN, BODY_WIDTH, BODY_BOTTOM, GREEN, GRID, MUTED, PALE,
)


def session_seconds(start, end):
    try:
        start = start if isinstance(start, time) else time.fromisoformat(str(start))
        end = end if isinstance(end, time) else time.fromisoformat(str(end))
        seconds = lambda value: value.hour * 3600 + value.minute * 60 + value.second
        duration = seconds(end) - seconds(start)
        return duration if duration > 0 else None
    except (ValueError, TypeError):
        return None


def read_overview(conn, catalog, date_from=None, date_to=None):
    """Two bound bulk reads; no per-employee connections or bootstrap row limit."""
    if not catalog:
        today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()
        return {"employees": [], "untrained": [], 'date_from': str(date_from or today), 'date_to': str(date_to or today)}
    names = [item['username'].lower() for item in catalog]
    daily = conn.execute(text('''SELECT employee_username, training_date, start_time, end_time,
        topic, skill_grade, learning_attitude, strengths, improvements, notes
        FROM vera_training_session WHERE lower(employee_username) IN :names
        ORDER BY training_date, start_time, id''').bindparams(bindparam('names', expanding=True)), {'names': names}).mappings().all()
    evaluations = conn.execute(text('''SELECT a.employee_username, c.name AS cycle_name, c.end_date,
        ev.craft_score, ev.communication_score, ev.attitude_score, ev.discipline_score,
        ev.appearance_score, ev.hygiene_score, ev.attendance_score,
        ev.strengths, ev.improvements, ev.comments
        FROM vera_evaluation_assignment a JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
        JOIN vera_evaluation_cycle c ON c.id=a.cycle_id
        WHERE a.status='submitted' AND lower(a.employee_username) IN :names
        ORDER BY c.end_date, ev.submitted_at, a.id''').bindparams(bindparam('names', expanding=True)), {'names': names}).mappings().all()
    report = summarize(catalog, daily, evaluations)
    all_days = [str(row['training_date'])[:10] for row in daily] + [str(row['end_date'])[:10] for row in evaluations]
    today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()
    report['date_from'] = str(date_from) if date_from else min(all_days, default=today)
    report['date_to'] = str(date_to) if date_to else max(all_days, default=today)
    def in_range(value):
        day = str(value)[:10]
        return (not date_from or day >= str(date_from)) and (not date_to or day <= str(date_to))
    if date_from or date_to:
        filtered = summarize(catalog, [row for row in daily if in_range(row['training_date'])], [row for row in evaluations if in_range(row['end_date'])])
        report['employees'] = filtered['employees']
    return report


def summarize(catalog, daily, evaluations):
    groups = {item['username'].casefold(): {'employee': item, 'daily': [], 'evaluations': []} for item in catalog}
    for key, rows in [('daily', daily), ('evaluations', evaluations)]:
        for row in rows:
            group = groups.get(row['employee_username'].casefold())
            if group is not None:
                group[key].append(row)
    trained, untrained = [], []
    scores = [('craft_score', 'Tay nghề'), ('communication_score', 'Giao tiếp'), ('attitude_score', 'Thái độ'),
              ('discipline_score', 'Kỷ luật'), ('appearance_score', 'Ngoại hình'), ('hygiene_score', 'Vệ sinh'), ('attendance_score', 'Chuyên cần')]
    for group in groups.values():
        employee, sessions, assessments = group['employee'], group['daily'], group['evaluations']
        if not sessions and not assessments:
            if employee.get('department_code') == 'nhanvien':
                untrained.append(employee)
            continue
        durations = [session_seconds(row['start_time'], row['end_time']) for row in sessions]
        topics = list(dict.fromkeys(str(row['topic']).strip() for row in sessions if row.get('topic')))
        parts = ['Nội dung: ' + ('; '.join(topics) if topics else 'Chưa có buổi đào tạo')]
        grades = Counter(str(row['skill_grade']) for row in sessions if row.get('skill_grade'))
        if grades:
            parts.append('Kỹ năng: ' + ', '.join(f'{grade}: {count} buổi' for grade, count in grades.items()))
        for rows, label, fields in [(sessions, 'Đào tạo', [('learning_attitude', 'Tinh thần'), ('strengths', 'Điểm mạnh'), ('improvements', 'Cần cải thiện'), ('notes', 'Nhận xét')]),
                                    (assessments, 'Đánh giá', [('strengths', 'Điểm mạnh'), ('improvements', 'Cần cải thiện'), ('comments', 'Nhận xét')])]:
            for field, title in fields:
                values = list(dict.fromkeys(str(row[field]).strip() for row in rows if row.get(field)))
                if values:
                    parts.append(f'{label} - {title}: ' + '; '.join(values))
        if assessments:
            averages = []
            for field, label in scores:
                values = [Decimal(str(row[field])) for row in assessments if row.get(field) is not None]
                if values:
                    averages.append(f'{label} {sum(values) / len(values):.2f}/5')
            parts.append(f'Đánh giá tổng hợp ({len(assessments)} phiếu): ' + ('; '.join(averages) if averages else 'Chưa có điểm'))
        else:
            parts.append('Đánh giá tổng hợp: Chưa có phiếu đã nộp')
        missing = sum(value is None for value in durations)
        if missing:
            parts.append(f'{missing} buổi thiếu giờ hợp lệ, chưa cộng vào tổng')
        trained.append({'employee': employee, 'seconds': sum(value for value in durations if value is not None),
                        'session_count': len(sessions), 'missing_duration': missing, 'summary': '\n'.join(parts)})
    return {'employees': trained, 'untrained': untrained}


def build_layout(report, *, png=False):
    layout = _Layout('Toàn bộ nhân viên', png=png)
    layout.paragraph('BÁO CÁO TIẾN ĐỘ ĐÀO TẠO', size=17, bold=True)
    from vera_web_v2_training_report_export import _date
    layout.paragraph(f"Từ ngày: {_date(report.get('date_from'))} · Đến ngày: {_date(report.get('date_to'))}", size=9, color=MUTED)
    trained = report['employees']
    layout.section('01', 'NHÂN VIÊN ĐÃ ĐÀO TẠO / ĐÁNH GIÁ', f'{len(trained)} nhân viên · Tổng giờ các buổi trong khoảng ngày có thời gian hợp lệ')
    if not trained:
        layout.paragraph('Chưa có hồ sơ đào tạo hoặc đánh giá đã nộp.')
    maximum = max([item['seconds'] for item in trained] or [0]) or 1
    gap = 12
    width = (BODY_WIDTH - gap * 2) / 3
    for offset in range(0, len(trained), 3):
        chunk = trained[offset:offset + 3]
        names = [_wrap(item['employee'].get('full_name') or item['employee']['username'], width - 12, 10, True) for item in chunk]
        summaries = [_wrap('Nội dung và đánh giá tổng hợp\n' + item['summary'], width - 12, 8, False) for item in chunk]
        layout.ensure(220)
        y = layout.y
        for index, item in enumerate(chunk):
            x = MARGIN + index * (width + gap)
            height = 100 * item['seconds'] / maximum
            layout.rect(x + 6, y, width - 12, 125, PALE)
            if height:
                layout.rect(x + width * .3, y + 112 - height, width * .4, height, GREEN)
            layout.text(f"{item['seconds'] / 3600:.2f} giờ", x + width / 2, y + 116 - height - 17, size=10, bold=True, anchor='center')
            for line_index, line in enumerate(names[index]):
                layout.text(line, x + 6, y + 134 + line_index * 15, size=10, bold=True)
        layout.y = y + 139 + max(len(lines) for lines in names) * 15
        remaining = [list(lines) for lines in summaries]
        while any(remaining):
            available = int((BODY_BOTTOM - layout.y - 12) // 12)
            if available < 1:
                layout.new_page()
                for index, item in enumerate(chunk):
                    x = MARGIN + index * (width + gap)
                    for line_index, line in enumerate(names[index]):
                        layout.text(line, x + 6, layout.y + line_index * 15, size=10, bold=True)
                layout.y += max(len(lines) for lines in names) * 15 + 8
                continue
            count = min(available, max(len(lines) for lines in remaining))
            for index, lines in enumerate(remaining):
                x = MARGIN + index * (width + gap)
                for line_index, line in enumerate(lines[:count]):
                    layout.text(line, x + 6, layout.y + line_index * 12, size=8, bold=line == 'Nội dung và đánh giá tổng hợp')
                del lines[:count]
                layout.line(x, layout.y + count * 12, x + width, layout.y + count * 12, GRID)
            layout.y += count * 12 + 14
    layout.section('02', 'NHÂN VIÊN CHƯA ĐÀO TẠO / ĐÁNH GIÁ', 'Chỉ bộ phận nhanvien · Chưa có buổi đào tạo hoặc phiếu đánh giá đã nộp trong toàn bộ thời gian', background='#fff2b3')
    if not report['untrained']:
        layout.paragraph('Không có nhân viên chưa được đào tạo / đánh giá.')
    for offset in range(0, len(report['untrained']), 3):
        rows = report['untrained'][offset:offset + 3]
        lines = [_wrap(f"{offset + i + 1}. {item.get('full_name') or item['username']}", width - 12, 9, False) for i, item in enumerate(rows)]
        height = max(len(item) for item in lines) * 14 + 14
        layout.ensure(height)
        for i, values in enumerate(lines):
            x = MARGIN + i * (width + gap)
            layout.rect(x, layout.y, width, height, PALE)
            for n, line in enumerate(values):
                layout.text(line, x + 6, layout.y + 6 + n * 14, size=9)
            for x1, y1, x2, y2 in [(x, layout.y, x + width, layout.y), (x, layout.y + height, x + width, layout.y + height), (x, layout.y, x, layout.y + height), (x + width, layout.y, x + width, layout.y + height)]:
                layout.line(x1, y1, x2, y2, GREEN)
        layout.y += height
    return layout.finish()


def render_overview(report, file_format):
    fonts = _fonts()
    pages = build_layout(report, png=file_format == 'png')
    if file_format == 'pdf':
        return _render_pdf(pages, {'employee': {'full_name': 'Toàn bộ nhân viên'}})
    if file_format == 'png':
        return _render_png(pages, fonts)
    raise ValueError('Định dạng không hợp lệ')
