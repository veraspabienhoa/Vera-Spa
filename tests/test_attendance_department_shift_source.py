from datetime import date

from vera_web_v2_attendance_query_perf import _placeholder_record, _definition_for_shift

DEFINITIONS = [{'Tên ca': 'Ca 2', 'Bộ phận': 'Nhân viên + Leader', 'Giờ bắt đầu': '13:00', 'Giờ kết thúc': '23:59'},
               {'Tên ca': 'Ca 2', 'Bộ phận': 'Lễ tân', 'Giờ bắt đầu': '16:30', 'Giờ kết thúc': '00:30'}]


def test_reception_cannot_inherit_staff_shift_or_arbitrary_department_shift():
    assert _definition_for_shift('Ca 2', DEFINITIONS, 'letan') == DEFINITIONS[1]
    assert _definition_for_shift('Ca 2', DEFINITIONS[:1], 'letan') == {}
    assert _definition_for_shift('', DEFINITIONS, 'letan') == {}
    assert _definition_for_shift('Chưa chia ca', DEFINITIONS, 'letan') == {}


def test_anh_nguyen_without_daily_schedule_has_no_invented_shift():
    row = _placeholder_record({'username': 'Anh Nguyễn', 'role': 'letan', 'work_shift': 'Chưa chia ca'},
                              date(2026, 9, 12), DEFINITIONS, {}, {}, None)
    assert row['shift'] == row['shift_start'] == row['shift_end'] == ''
    assert row['attendance_expected'] is False


def test_daily_reception_hours_override_same_named_catalog_shift():
    row = _placeholder_record({'username': 'Anh Nguyễn', 'role': 'letan', 'work_shift': 'Ca 2'},
                              date(2026, 9, 12), DEFINITIONS, {}, {},
                              {'shift_code': 'Ca 2', 'start_time': '17:00', 'end_time': '01:00'})
    assert row['shift_start'] == '17:00' and row['shift_end'] == '01:00'
