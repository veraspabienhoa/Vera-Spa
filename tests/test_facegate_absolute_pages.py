from unittest.mock import patch
import pytest
import vera_facegate_control_log as device
from vera_facegate_sync import prepare_batch

class Response:
    status_code = 200
    def __init__(self, body):
        self.text = body
    def close(self):
        pass

def page(group, start, count, local=False):
    parts = [f'root.{group}.totalcount=129', f'root.{group}.beginno={start}',
             f'root.{group}.rspcount={count}', f'root.{group}.sessionid=8', 'root.ERR.no=0']
    for n in range(count):
        prefix = f'root.{group}.ITEM{n if local else start+n}.'
        parts.extend(prefix+k+'='+v for k,v in {
            'uid': str(1000+start+n), 'utime': '2026-09-24/20:20:36',
            'uname': 'Test', 'ustatus': '1', 'utype': '0',
            'dwfiletype': '0', 'dwfileindex': '0', 'dwfilepos': '1420'}.items())
    return ' '.join(parts)

@pytest.mark.parametrize('group', ['CONTROL', 'CAPTURE'])
@pytest.mark.parametrize('local', [False, True])
def test_all_129_records_across_seven_pages(group, local):
    starts, closed = [], []
    def get(url, **kwargs):
        start = int(kwargs['params']['beginno'])
        starts.append(start)
        return Response(page(group, start, min(20, 129-start), local))
    def post(url, **kwargs):
        closed.append(kwargs['params']['sessionid'])
        return Response('root.ERR.no=0')
    with patch.object(device, '_facegate_config', return_value=('http://device', '/webs/getLog', ('x','y'))):
        fetch = device.fetch_control_log if group == 'CONTROL' else device.fetch_capture_log
        result = fetch('2026-09-24', '2026-09-24', get=get, post=post)
    assert starts == [0,20,40,60,80,100,120]
    assert len(result['records']) == 129
    assert len({r['event_id'] for r in result['records']}) == 129
    assert result['truncated'] is False
    assert closed == ['8']
    if group == 'CONTROL':
        assert len(prepare_batch(result, '2026-09-24')) == 129

@pytest.mark.parametrize('group', ['CONTROL', 'CAPTURE'])
def test_page_bound_is_count_not_absolute_index(group):
    parse = device.parse_control_log_response if group == 'CONTROL' else device._parse_capture_log_response
    assert len(parse(page(group, 120, 9))['records']) == 9
    with pytest.raises(ValueError, match='giới hạn'):
        parse(page(group, 120, 21))

@pytest.mark.parametrize('group', ['CONTROL', 'CAPTURE'])
def test_short_response_reports_truncation(group):
    def get(url, **kwargs):
        start = int(kwargs['params']['beginno'])
        return Response(page(group, start, 20 if start == 0 else 0))
    with patch.object(device, '_facegate_config', return_value=('http://device', '/webs/getLog', ('x','y'))):
        fetch = device.fetch_control_log if group == 'CONTROL' else device.fetch_capture_log
        result = fetch('2026-09-24', '2026-09-24', get=get, post=lambda *a, **kw: Response(''))
    assert result['truncated'] is True
    assert len(result['records']) == 20
