import unicodedata

from vera_web_v2_payroll import _history_details


def norm(value):
    value = unicodedata.normalize('NFD', str(value or '').casefold())
    return ''.join(c for c in value if not unicodedata.combining(c)).replace('đ', 'd')


def test_history_filters_and_status_do_not_recalculate_saved_money():
    records = [
        {'Tên Hệ thống': 'An Nhiên', 'Họ và tên': 'Nguyễn A', 'Tiền Lương': 123, 'Số tiền thực nhận': -500},
        {'Tên Hệ thống': 'B', 'Số tiền thực nhận': 0},
        {'Tên Hệ thống': 'C', 'Số tiền thực nhận': 100},
    ]
    catalog = {norm('An Nhiên'): {'employment_status': 'Đã nghỉ việc'}, 'b': {'employment_status': 'Đang làm việc'}}
    rows = _history_details(records, catalog, norm, 'an nhien', True, True)
    assert len(rows) == 1
    assert rows[0]['Tiền Lương'] == 123
    assert rows[0]['Số tiền thực nhận'] == -500
    assert rows[0]['__employment_status'] == 'Đã nghỉ việc'
    assert '__employment_status' not in records[0]
    assert len(_history_details(records, catalog, norm, non_positive_only=True)) == 2
    assert _history_details(records, catalog, norm, 'Nguyen A')[0]['Tên Hệ thống'] == 'An Nhiên'


def test_history_does_not_include_catalog_employees_without_visible_salary_rows():
    rows = _history_details([{'Tên Hệ thống': 'A'}], {'a': {'employment_status': 'Đang làm việc'}, 'private': {'employment_status': 'Đã nghỉ việc'}}, norm)
    assert [row['Tên Hệ thống'] for row in rows] == ['A']
    assert _history_details([{'Tên Hệ thống': 'unknown'}], {}, norm, former_only=True) == []


def test_export_search_matches_frontend_word_boundaries_and_partial_final_word():
    rows = [{'Tên Hệ thống': 'An Nhiên', 'Họ và tên': 'Nguyễn A'}]
    assert len(_history_details(rows, {}, norm, 'an nhi')) == 1
    assert len(_history_details(rows, {}, norm, 'An-Nhiên')) == 1
    assert _history_details(rows, {}, norm, 'n nhi') == []
    assert _history_details(rows, {}, norm, 'a nhi') == []
