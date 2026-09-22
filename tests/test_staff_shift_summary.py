from datetime import date
from vera_web_v2_staff import staff_shift_summary


def employee(**changes):
    return dict(role='nhanvien', employment_status='Đang làm việc', work_shift='Ca 1',
                shift_start_date='15/09/2026', rotation_cycle='Theo chu kỳ Tuần', **changes)


def test_only_active_ktv_count_and_fixed_not_double_counted():
    base = employee()
    rows = [base, {**base, 'role': 'leader', 'work_shift': 'Ca 1 (Không đổi)'},
            {**base, 'rotation_cycle': 'Cố định (Không đổi)', 'work_shift': 'Ca 2'},
            {**base, 'role': 'locker'}, {**base, 'employment_status': 'Tạm thời nghỉ việc'},
            {**base, 'employment_status': 'Đã nghỉ việc'}, {**base, 'shift_start_date': '23/09/2026'},
            {**base, 'work_shift': ''}]
    assert staff_shift_summary(rows, date(2026, 9, 22)) == {
        'ca_1_regular': 0, 'ca_1_fixed': 1, 'ca_1_total': 1,
        'ca_2_regular': 1, 'ca_2_fixed': 1, 'ca_2_total': 2,
    }


def test_custom_shift_and_weekly_boundary():
    definitions = [{'Tên ca': 'Sáng', 'Ca chính': 'Ca 1', 'Bộ phận': 'Nhân viên + Leader'}]
    row = {**employee(), 'work_shift': 'Sáng'}
    assert staff_shift_summary([row], date(2026, 9, 21), definitions)['ca_1_regular'] == 1
    assert staff_shift_summary([row], date(2026, 9, 22), definitions)['ca_2_regular'] == 1
