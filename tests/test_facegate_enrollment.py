from io import BytesIO

import pytest
from PIL import Image
import requests

import vera_facegate_enrollment as fg

REF = {'file_type': 0, 'file_index': 0, 'file_position': 14680064}
OLD_REF = {'file_type': 0, 'file_index': 0, 'file_position': 14680065}


def body(**values):
    return '<html>' + '\n'.join('root.'+k+'='+str(v) for k, v in {'ERR.no': 0, **values}.items()) + '</html>'


class Response:
    status_code = 200
    def __init__(self, value): self.value, self.closed = value.encode(), False
    def iter_content(self, size): yield self.value
    def close(self): self.closed = True


class Session:
    def __init__(self, replies): self.replies, self.calls = list(replies), []
    def get(self, url, **kwargs): return self.request('GET', url, kwargs)
    def post(self, url, **kwargs): return self.request('POST', url, kwargs)
    def request(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        response = self.replies.pop(0)
        if isinstance(response, Exception): raise response
        return Response(response)
    def close(self): pass


def client(monkeypatch, replies):
    monkeypatch.setenv('VERA_FACEGATE_BASE_URL', 'http://192.168.1.34')
    monkeypatch.setenv('VERA_FACEGATE_USERNAME', 'test')
    monkeypatch.setenv('VERA_FACEGATE_PASSWORD', 'test')
    session = Session(replies)
    return fg.FaceGateEnrollmentClient(session, sleep=lambda _: None), session


def roster(rows, total=None):
    fields = {'LIST.totalcount': len(rows) if total is None else total, 'LIST.rspcount': len(rows)}
    for i, row in enumerate(rows): fields.update({f'LIST.ITEM{i}.{k}': v for k,v in row.items()})
    return body(**fields)


def profile():
    return {'uid': '123', 'uname': 'Test Staff', 'utext': 'vera:token',
            'dwfiletype': 0, 'dwfileindex': 0, 'dwfilepos': 14680064}


def test_upload_uses_observed_form_and_similarity_check(monkeypatch):
    c, s = client(monkeypatch, ['<html>uploaded</html>', body(**{'UPLOAD.state': 100,
        'UPLOAD.sessionid': '0', 'UPLOAD.dwfiletype': 0, 'UPLOAD.dwfileindex': 0, 'UPLOAD.dwfilepos': 14680064})])
    assert c.upload(b'jpeg', '12345678') == REF
    method, url, kwargs = s.calls[0]
    assert method == 'POST' and url.endswith('/webs/uploadfile')
    assert kwargs['params'] == {'action':'LISTADD','group':'UPLOAD','sessionid':'12345678','IsCheckSim':'1'}
    assert kwargs['files']['vfileselector'] == ('FaceID.jpg', b'jpeg', 'image/jpeg')
    assert all(not call[2]['allow_redirects'] for call in s.calls)


def test_photo_replacement_uses_observed_modify_upload_and_update_protocol(monkeypatch):
    p = {**profile(), 'uphone': '0123456789', 'uaddr': 'Keep this field'}
    updated = {**p, 'dwfilepos': REF['file_position']}
    c, s = client(monkeypatch, [
        '<html>uploaded</html>',
        body(**{'UPLOAD.state': 100, 'UPLOAD.sessionid': '12345678',
                'UPLOAD.dwfiletype': REF['file_type'], 'UPLOAD.dwfileindex': REF['file_index'],
                'UPLOAD.dwfilepos': REF['file_position']}),
        body(), roster([updated]), body(**{'LIST.' + k: v for k, v in updated.items()}),
    ])
    assert c.upload(b'jpeg', '12345678', profile_id=123) == REF
    c.update_photo(p, REF)
    assert c.verify_replacement(123, 'Test Staff', 'vera:token', REF)['profile_id'] == 123
    upload = s.calls[0][2]
    assert upload['params'] == {'action': 'LISTMODIFT', 'group': 'UPLOAD',
                                'sessionid': '12345678', 'IsCheckSim': '1', 'LISTuid': '123'}
    update = s.calls[2][2]['params']
    assert update['action'] == 'update' and update['LIST.uid'] == '123'
    assert update['LIST.uname'] == p['uname'] and update['LIST.utext'] == p['utext']
    assert update['LIST.uphone'] == p['uphone'] and update['LIST.uaddr'] == p['uaddr']
    assert update['LIST.dwfilepos'] == str(REF['file_position'])
    assert s.calls[2][0] == 'POST' and all(call[0] == 'GET' for call in s.calls[1:2] + s.calls[3:])


@pytest.mark.parametrize('state', [101,102,103,104,105,106])
def test_rejected_faces_never_become_success(monkeypatch, state):
    c, s = client(monkeypatch, ['', body(**{'UPLOAD.state':state, 'UPLOAD.sessionid':'12345678'})])
    with pytest.raises(fg.UploadRejected): c.upload(b'jpeg', '12345678')
    assert len(s.calls) == 2


def test_timeout_does_not_replay_post(monkeypatch):
    c, s = client(monkeypatch, [requests.Timeout('secret URL must not reach UI')])
    with pytest.raises(requests.Timeout): c.upload(b'jpeg', '12345678')
    assert len(s.calls) == 1


@pytest.mark.parametrize('changes', [{'UPLOAD.sessionid':'99999999'}, {'UPLOAD.dwfiletype':3}, {'UPLOAD.dwfilepos':0}])
def test_wrong_session_or_reference_fails_closed(monkeypatch, changes):
    c, _ = client(monkeypatch, ['', body(**{'UPLOAD.state':100, 'UPLOAD.sessionid':'12345678',
        'UPLOAD.dwfiletype':0, 'UPLOAD.dwfileindex':0, 'UPLOAD.dwfilepos':14680064, **changes})])
    with pytest.raises(fg.EnrollmentError): c.upload(b'jpeg','12345678')


def test_add_and_exact_readback(monkeypatch):
    p = profile()
    c, s = client(monkeypatch, [body(), roster([p]), body(**{'LIST.'+k:v for k,v in p.items()})])
    c.add('Test Staff', 'vera:token', REF, (1, 0))
    assert c.verify('Test Staff', 'vera:token', REF) == {'profile_id':123,'device_name':'Test Staff','registration_ref':REF}
    assert s.calls[0][0] == 'POST'
    assert all(call[0] == 'GET' for call in s.calls[1:])
    assert s.calls[0][2]['data'] == s.calls[0][2]['params']['nRanId']
    assert len(s.calls[0][2]['data']) == 8
    assert s.calls[0][2]['headers']['Content-Type'] == 'text/html; charset=UTF-8'
    assert 'files' not in s.calls[0][2]
    params = s.calls[0][2]['params']
    assert params['LIST.uid'] == '-1' and params['action'] == 'add'
    assert params['LIST.utext'] == 'vera:token' and params['LIST.ulisttype'] == '0'


@pytest.mark.parametrize('case', ['truncated','duplicate_uid','missing_token','wrong_reference','wrong_name','wrong_detail'])
def test_never_confirm_partial_or_different_registration(monkeypatch, case):
    p = profile(); rows = [p]; total = None; detail = dict(p)
    if case == 'truncated': total = 2
    if case == 'duplicate_uid': rows.append(dict(p))
    if case == 'missing_token': p['utext'] = ''
    if case == 'wrong_reference': p['dwfilepos'] = 12
    if case == 'wrong_name': p['uname'] = 'Someone Else'
    if case == 'wrong_detail': detail['uid'] = '124'
    c, _ = client(monkeypatch, [roster(rows,total),body(**{'LIST.'+k:v for k,v in detail.items()})])
    with pytest.raises(fg.EnrollmentError): c.verify('Test Staff', 'vera:token', REF)


def test_parser_rejects_login_page_errors_duplicates_and_oversize():
    for value in ['<html>login</html>',body(**{'ERR.no':1}),body()+'\nroot.ERR.no=0', 'x'*(fg.device.MAX_RESPONSE_BYTES+1)]:
        with pytest.raises(fg.EnrollmentError): fg.fields(value)


def test_transport_conversion_preserves_original_and_ratio():
    out = BytesIO(); Image.new('RGB',(120,80),'blue').save(out,'PNG'); original=out.getvalue()
    jpeg=fg.jpeg_photo(original)
    assert original == out.getvalue()
    with Image.open(BytesIO(jpeg)) as image: assert image.size == (120,80) and image.format == 'JPEG'


def test_profile_save_timeout_never_retries_mutation(monkeypatch):
    c, s = client(monkeypatch, [requests.Timeout('private device detail')])
    with pytest.raises(requests.Timeout): c.add('Test Staff', 'vera:token', REF, (1, 0))
    assert len(s.calls) == 1 and s.calls[0][0] == 'POST'


def test_login_ignores_conflicting_unused_firmware_capabilities(monkeypatch):
    response = body(**{'LOGIN.ulevel': 0})
    extra = ''.join(f'\nroot.LOGIN.{key}=0\nroot.LOGIN.{key}=1'
                    for key in ('enterservice', 'ActiveMQSvr', 'VideoParamsSet'))
    c, session = client(monkeypatch, [response.replace('</html>', extra+'</html>')])
    c.login()
    assert len(session.calls) == 1 and session.calls[0][0] == 'GET'


@pytest.mark.parametrize('key', ['ERR.no', 'ERR.des', 'LOGIN.ulevel'])
@pytest.mark.parametrize('second', ['0', '1'])
def test_login_still_rejects_duplicate_decision_fields(monkeypatch, key, second):
    response = body(**{'LOGIN.ulevel': 0, 'ERR.des': 0})
    response = response.replace('</html>', f'\nroot.{key}={second}</html>')
    c, _ = client(monkeypatch, [response])
    with pytest.raises(fg.EnrollmentError, match='trùng'): c.login()


@pytest.mark.parametrize('key', ['LIST.uid', 'UPLOAD.dwfilepos', 'UPLOAD.sessionid'])
def test_other_protocol_responses_remain_strict(key):
    response = body(**{key: 1}).replace('</html>', f'\nroot.{key}=2</html>')
    with pytest.raises(fg.EnrollmentError, match='trùng'): fg.fields(response)


def rfid_roster(rows):
    response = roster(rows)
    for i in range(len(rows)):
        response = response.replace(f'root.LIST.ITEM{i}.uid=',
                                    f'root.LIST.uRFIdCardNum=0\nroot.LIST.ITEM{i}.uid=')
    return response


def test_roster_reads_all_56_profiles_with_repeated_unused_rfid(monkeypatch):
    rows = [dict(profile(), uid=str(i+1), utext=f'vera:{i}') for i in range(56)]
    c, session = client(monkeypatch, [rfid_roster(rows)])
    assert c.profiles() == [{k: str(v) for k, v in row.items()} for row in rows]
    assert len(session.calls) == 1 and session.calls[0][0] == 'GET'


@pytest.mark.parametrize('key,value', [
    ('ERR.no', '0'), ('LIST.totalcount', '2'), ('LIST.rspcount', '2'),
    ('LIST.ITEM0.uid', '123'), ('LIST.ITEM0.uname', 'Test Staff'),
    ('LIST.ITEM0.utext', 'vera:token'), ('LIST.ITEM0.dwfiletype', '0'),
    ('LIST.ITEM0.dwfileindex', '0'), ('LIST.ITEM0.dwfilepos', '14680064'),
])
def test_rfid_roster_still_rejects_duplicate_critical_fields(monkeypatch, key, value):
    response = rfid_roster([profile(), dict(profile(), uid='124')])
    response = response.replace('</html>', f'\nroot.{key}={value}</html>')
    c, _ = client(monkeypatch, [response])
    with pytest.raises(fg.EnrollmentError, match='trùng'): c.profiles()


def test_rfid_exception_is_scoped_to_roster():
    with pytest.raises(fg.EnrollmentError, match='trùng'):
        fg.fields(rfid_roster([profile(), dict(profile(), uid='124')]))


def test_exact_readback_after_roster_with_repeated_rfid(monkeypatch):
    p = profile()
    c, _ = client(monkeypatch, [rfid_roster([p, dict(p, uid='124', utext='other')]),
                               body(**{'LIST.'+k: v for k, v in p.items()})])
    assert c.verify('Test Staff', 'vera:token', REF)['profile_id'] == 123
