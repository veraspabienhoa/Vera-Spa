"""Observed FaceGate LISTADD/LISTMODIFT protocol. No automatic retries of device writes.

Source: operator-provided bwlist.asp/js/bwlist.js, 28 September 2026.
New enrollments use LISTADD/add. Replacements keep the existing UID and use
LISTMODIFT/update, with a strict device read-back before the mapping changes.
"""
from datetime import datetime
from io import BytesIO
import html
import re
import secrets
import time

from PIL import Image, ImageOps
import requests

import vera_facegate_control_log as device


class EnrollmentError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class UploadRejected(EnrollmentError):
    pass


def fields(body, *, only=None, ignore=()):
    if len(body.encode('utf-8')) > device.MAX_RESPONSE_BYTES:
        raise EnrollmentError('invalid_response', 'Phản hồi máy vượt giới hạn.')
    result = {}
    for key, value in re.findall(r'root\.([A-Za-z0-9_.]+)=(.*?)(?=\s+root\.|</html>|$)', body, re.S):
        # Login firmware repeats unrelated capability flags with different
        # values. Ignore only fields the login caller explicitly does not use.
        if only is not None and key not in only:
            continue
        if key in ignore:
            continue
        if key in result:
            raise EnrollmentError('invalid_response', 'Máy trả trường dữ liệu bị trùng.')
        result[key] = html.unescape(value).strip()
    if result.get('ERR.no') != '0':
        raise EnrollmentError('device_error', 'Máy chưa chấp nhận yêu cầu. Hãy kiểm tra lại kết nối hoặc phiên đăng nhập.')
    return result


def jpeg_photo(content):
    # Normalize transport only; never change the saved original or its aspect ratio.
    with Image.open(BytesIO(content)) as source:
        photo = ImageOps.exif_transpose(source).convert('RGB')
        out = BytesIO()
        photo.save(out, format='JPEG', quality=92)
    value = out.getvalue()
    if not value or len(value) > device.MAX_IMAGE_BYTES:
        raise EnrollmentError('photo_size', 'Ảnh JPEG gửi máy vượt 4 MB; hãy chọn ảnh nhỏ hơn.')
    return value


class FaceGateEnrollmentClient:
    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.base, _, self.auth = device._facegate_config()
        self.sleep = sleep

    def close(self):
        self.session.close()

    def request(self, path, params, *, photo=None):
        # Never use _device_get: its login retry must not replay a mutation.
        mutation = photo is None and params.get('action') != 'list'
        method = self.session.post if photo is not None or mutation else self.session.get
        params = dict(params)
        options = {'params': params, 'auth': self.auth, 'timeout': (3, 8),
                   'allow_redirects': False, 'stream': True}
        if photo is not None:
            # The device's upgrade_frm submits txt before vfileselector.
            # getPath() supplies the basename on Chrome/Safari; this text part
            # is part of the upload protocol, not just a display-only input.
            options['data'] = {'txt': 'FaceID.jpg'}
            options['files'] = {'vfileselector': ('FaceID.jpg', photo, 'image/jpeg')}
        else:
            # js/send.js: non-list actions POST the same 8-character nonce
            # appended to the URL, with form values remaining in the query.
            nonce = str(secrets.randbelow(90000000) + 10000000)
            params['nRanId'] = nonce
            options['headers'] = {'Content-Type': 'text/html; charset=UTF-8',
                                  'Pragma': 'no-cach', 'cache-control': 'no-cache',
                                  'Expires': 'Wed, 26 Oct 2016 23:48:01 GMT'}
            if mutation:
                options['data'] = nonce
        response = method(self.base + path, **options)
        try:
            if response.status_code != 200:
                raise EnrollmentError('device_http', 'Máy chưa trả kết quả hợp lệ.')
            chunks, size = [], 0
            for chunk in response.iter_content(8192):
                size += len(chunk)
                if size > device.MAX_RESPONSE_BYTES:
                    raise EnrollmentError('invalid_response', 'Phản hồi máy vượt giới hạn.')
                chunks.append(chunk)
            return b''.join(chunks).decode('utf-8', errors='strict')
        finally:
            response.close()

    def login(self):
        value = fields(self.request('/webs/login', {'action': 'list', 'group': 'LOGIN',
                       'UserID': str(secrets.randbelow(90000000) + 10000000)}),
                       only={'ERR.no', 'ERR.des', 'LOGIN.ulevel'})
        if not value.get('LOGIN.ulevel', '').isdigit():
            raise EnrollmentError('login_failed', 'Không đăng nhập được máy chấm công.')

    def profiles(self):
        value = fields(self.request('/webs/getWhitelist', {
            'action': 'list', 'group': 'LIST', 'uflag': '0', 'usex': '2',
            'uage': '0-100', 'MjCardNo': '0', 'begintime': '1970-01-01/00:00:00',
            'endtime': '2099-12-31/23:59:59', 'utype': '3', 'sequence': '1',
            'beginno': '0', 'reqcount': '1000',
            'sessionid': str(secrets.randbelow(90000000) + 10000000),
        }), ignore={'LIST.uRFIdCardNum'})
        # Firmware emits this unused, unindexed RFID field once per profile.
        # Keep indexed identity/reference fields and list counts strict.
        items = {}
        for key, val in value.items():
            match = re.fullmatch(r'LIST.ITEM(\d+)\.(\w+)', key)
            if match:
                items.setdefault(int(match[1]), {})[match[2]] = val
        try:
            total, count = int(value['LIST.totalcount']), int(value['LIST.rspcount'])
            ids = [int(row['uid']) for row in items.values()]
        except (KeyError, ValueError) as exc:
            raise EnrollmentError('incomplete_list', 'Không đọc đủ danh sách hồ sơ trên máy.') from exc
        if not (0 <= total == count == len(items) <= 1000) or len(set(ids)) != total or any(uid <= 0 for uid in ids):
            raise EnrollmentError('incomplete_list', 'Danh sách máy chưa đầy đủ; chưa thể đăng ký an toàn.')
        return list(items.values())

    def upload(self, photo, session_id, *, profile_id=None):
        # POST body may be an HTML completion page; the authoritative result is
        # getUploadPercent. Do not assume HTTP 200 means a face was accepted.
        params = {'action': 'LISTADD' if profile_id is None else 'LISTMODIFT',
                  'group': 'UPLOAD', 'sessionid': session_id, 'IsCheckSim': '1'}
        if profile_id is not None:
            if not isinstance(profile_id, int) or profile_id <= 0:
                raise EnrollmentError('invalid_profile', 'ID hồ sơ FaceGate không hợp lệ.')
            params['LISTuid'] = str(profile_id)
        response = self.request('/webs/uploadfile', params, photo=photo)
        # Some firmware replies with an API error and HTTP 200 instead of the
        # completion page. Do not discard that rejection and poll an idle upload.
        if re.search(r'root\.ERR\.no=', response):
            try:
                fields(response, only={'ERR.no', 'ERR.des'})
            except EnrollmentError as exc:
                if exc.code == 'device_error':
                    raise UploadRejected('upload_request_rejected',
                        'Máy từ chối nhận file ảnh; hồ sơ trên máy chưa được cập nhật.') from None
                raise
        started = False
        for _ in range(12):
            value = fields(self.request('/webs/getUploadPercent', {
                'action': 'list', 'group': 'UPLOAD', 'sessionid': session_id}))
            if value.get('UPLOAD.sessionid') not in (session_id, '0'):
                raise EnrollmentError('wrong_session', 'Máy trả kết quả của phiên gửi ảnh khác.')
            state = value.get('UPLOAD.state')
            if state == '100':
                ref = device.registration_ref({key.removeprefix('UPLOAD.'): val for key, val in value.items()})
                if not ref:
                    raise EnrollmentError('invalid_reference', 'Máy chưa trả tham chiếu đăng ký mới hợp lệ.')
                return ref
            if state in {'101', '102', '103', '104', '105', '106'}:
                message = {'104': 'Máy đã đầy hồ sơ.', '105': 'Máy không tìm thấy khuôn mặt rõ trong ảnh.',
                           '106': 'Máy phát hiện khuôn mặt đã đăng ký. Cần đối chiếu hồ sơ đang có.'}.get(state, 'Máy từ chối ảnh; hãy chọn ảnh khác.')
                raise UploadRejected('upload_' + state, message)
            if state is None or not state.isdigit() or not 0 <= int(state) < 100:
                raise EnrollmentError('invalid_state', 'Trạng thái xử lý ảnh của máy không hợp lệ.')
            started = started or int(state) > 0
            self.sleep(.5)
        if not started:
            raise EnrollmentError('upload_not_started',
                'Máy chưa bắt đầu xử lý file ảnh. Ảnh chỉ đang lưu trên VERA, chưa cập nhật lên máy. Hãy kiểm tra lại kết quả.')
        raise EnrollmentError('upload_pending', 'Máy chưa hoàn tất xử lý ảnh; cần kiểm tra lại kết quả.')

    def profile_details(self, profile_id):
        if not isinstance(profile_id, int) or not 0 < profile_id <= 2**31 - 1:
            raise EnrollmentError('invalid_profile', 'ID hồ sơ FaceGate không hợp lệ.')
        value = fields(self.request('/webs/getWhitelist', {
            'action': 'list', 'group': 'LIST', 'LIST.uid': str(profile_id)}))
        detail = {key.removeprefix('LIST.'): val for key, val in value.items()
                  if key.startswith('LIST.')}
        if detail.get('uid') != str(profile_id):
            raise EnrollmentError('wrong_profile', 'Máy không trả đúng hồ sơ cần cập nhật.')
        return detail

    def update_photo(self, profile, ref):
        """Update only a previously read profile, preserving its other fields."""
        try:
            profile_id = int(profile['uid'])
            if profile_id <= 0 or profile.get('uname') is None or profile.get('utext') is None:
                raise ValueError()
            params = {'action': 'update', 'group': 'LIST'}
            for key, value in profile.items():
                if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', key):
                    params['LIST.' + key] = str(value)
            params.update({'LIST.uid': str(profile_id),
                           'LIST.dwfiletype': str(ref['file_type']),
                           'LIST.dwfileindex': str(ref['file_index']),
                           'LIST.dwfilepos': str(ref['file_position']),
                           'LIST.uIsCheckSim': '1'})
        except (KeyError, TypeError, ValueError):
            raise EnrollmentError('invalid_profile', 'Hồ sơ máy thiếu dữ liệu cần giữ nguyên khi cập nhật.') from None
        fields(self.request('/webs/setWhitelist', params))
        return profile_id

    def verify_replacement(self, profile_id, name, token, ref):
        matches = [p for p in self.profiles() if p.get('uid') == str(profile_id)]
        if len(matches) != 1 or matches[0].get('uname') != name or matches[0].get('utext') != token or device.registration_ref(matches[0]) != ref:
            raise EnrollmentError('unverified', 'Ảnh mới chưa được xác minh trên đúng hồ sơ. Không gửi lại để tránh cập nhật trùng.')
        detail = self.profile_details(profile_id)
        if detail.get('uname') != name or detail.get('utext') != token or device.registration_ref(detail) != ref:
            raise EnrollmentError('unverified', 'Hồ sơ đọc lại không khớp ảnh mới. Cần kiểm tra trên máy.')
        return {'profile_id': profile_id, 'device_name': name, 'registration_ref': ref}

    def door_defaults(self):
        value = fields(self.request('/webs/getCfgSysDoor', {'action': 'list', 'group': 'CFGDOOR'}))
        try:
            protocol, card = int(value['CFGDOOR.protocol']), int(value['CFGDOOR.publicMjCardNo'])
        except (KeyError, ValueError) as exc:
            raise EnrollmentError('door_config', 'Không đọc được cấu hình tạo hồ sơ của máy.') from exc
        if not 0 <= protocol <= 65535 or not 0 <= card <= 2**32-1:
            raise EnrollmentError('door_config', 'Cấu hình hồ sơ máy không hợp lệ.')
        return protocol, card

    def add(self, name, token, ref, defaults):
        protocol, card = defaults
        day = datetime.now(device.VN_TZ).date().isoformat()
        params = {'action': 'add', 'group': 'LIST', 'LIST.uid': '-1',
                  'LIST.uname': name, 'LIST.utext': token, 'LIST.utype': '0',
                  'LIST.dwfiletype': str(ref['file_type']), 'LIST.dwfileindex': str(ref['file_index']),
                  'LIST.dwfilepos': str(ref['file_position']), 'LIST.protocol': str(protocol),
                  'LIST.publicMjCardNo': str(card), 'LIST.MjCardNo': str(card),
                  'LIST.ucardtype': '0', 'LIST.uregno': '0', 'LIST.usex': '0',
                  'LIST.unation': '1', 'LIST.ucertype': '0', 'LIST.ucernumber': '',
                  'LIST.ubirth': '2000-1-1', 'LIST.uphone': '', 'LIST.uplace': '',
                  'LIST.uaddr': '', 'LIST.ulisttype': '0', 'LIST.ulistChScope': '0',
                  'LIST.uIdCardID': '', 'LIST.uWardenId': '', 'LIST.uAccessID': '',
                  'LIST.uRoomNum': '', 'LIST.uvalidbegintime': day+' 00:00:00',
                  'LIST.uvalidendtime': day+' 23:59:59', 'LIST.uvalidDateBeg': day,
                  'LIST.uvalidDateEnd': day, 'LIST.uvalidTimeBeg': '00:00:00',
                  'LIST.uvalidTimeEnd': '23:59:59', 'LIST.uIsCheckSim': '1'}
        fields(self.request('/webs/setWhitelist', params))

    def verify(self, name, token, ref):
        matches = [p for p in self.profiles() if p.get('utext') == token]
        if len(matches) != 1 or matches[0].get('uname') != name or device.registration_ref(matches[0]) != ref:
            raise EnrollmentError('unverified', 'Chưa xác minh được hồ sơ vừa đăng ký. Không gửi lại để tránh tạo trùng.')
        uid = int(matches[0]['uid'])
        value = fields(self.request('/webs/getWhitelist', {'action': 'list', 'group': 'LIST', 'LIST.uid': str(uid)}))
        detail = {key.removeprefix('LIST.'): val for key, val in value.items() if key.startswith('LIST.')}
        if detail.get('uid') != str(uid) or detail.get('uname') != name or detail.get('utext') != token or device.registration_ref(detail) != ref:
            raise EnrollmentError('unverified', 'Hồ sơ đọc lại không khớp lần gửi ảnh. Cần kiểm tra trên máy.')
        return {'profile_id': uid, 'device_name': name, 'registration_ref': ref}
