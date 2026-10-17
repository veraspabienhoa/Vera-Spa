from datetime import datetime
from zoneinfo import ZoneInfo
from vera_leave_scheduled_completion import completion_payload
from vera_leave_list_filters import filter_rows

VN = ZoneInfo('Asia/Ho_Chi_Minh')

def request(kind='Nghỉ Phép năm', status='Đã duyệt', **payload):
    return {'record_type': kind, 'record_status': status, 'date_from': '10/10/2026',
            'date_to': '16/10/2026', 'payload': payload}


def test_annual_completes_only_after_inclusive_end_date():
    row = request()
    assert completion_payload(row, datetime(2026, 10, 16, 23, 59, 59, tzinfo=VN)) is None
    result = completion_payload(row, datetime(2026, 10, 16, 17, tzinfo=ZoneInfo('UTC')))
    assert result['Trạng thái kỳ nghỉ'] == 'Đã kết thúc'
    assert result['Kết thúc lúc'] == '2026-10-17T00:00:00+07:00'
    assert 'Ngày quay lại làm việc' not in result
    assert completion_payload({**row, 'payload': result}, datetime(2026, 10, 18, tzinfo=VN)) is None


def test_resignation_completes_on_effective_date_without_return():
    row = request('Nghỉ việc'); row['date_to'] = row['date_from']
    assert completion_payload(row, datetime(2026, 10, 9, 23, 59, tzinfo=VN)) is None
    result = completion_payload(row, datetime(2026, 10, 10, tzinfo=VN))
    assert result['Nguồn kết thúc kỳ nghỉ'] == 'scheduled'
    assert 'Ngày quay lại làm việc' not in result


def test_manual_pending_cancelled_and_invalid_dates_are_preserved():
    now = datetime(2026, 10, 18, tzinfo=VN)
    for status in ('Chờ duyệt', 'Đã hủy', 'Từ chối'):
        assert completion_payload(request(status=status), now) is None
    assert completion_payload(request(**{'Trạng thái kỳ nghỉ': 'Đã kết thúc', 'Nguồn kết thúc kỳ nghỉ': 'manual'}), now) is None
    assert completion_payload({**request(), 'date_to': 'bad'}, now) is None
    assert completion_payload(request('Nghỉ làm đẹp'), now) is None


def test_list_filters_are_combined_and_accent_insensitive():
    rows = [{'leave_reason': 'Nghỉ Phép năm', 'leave_type': 'Phép năm', 'detail': 'Về quê Đồng Nai'},
            {'leave_reason': 'Nghỉ KHÔNG phép', 'leave_type': 'Không phép', 'detail': 'Đi việc riêng'}]
    assert filter_rows(rows, 'phep', 'phep nam', 'dong nai') == rows[:1]
    assert filter_rows(rows, 'khong', '', 'que') == []
    assert filter_rows(rows) == rows
