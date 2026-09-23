from __future__ import annotations

import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    # The scratch image omits app requirements; tests inject their own HTTP fake.
    sys.modules["requests"] = SimpleNamespace(get=None, post=None, RequestException=OSError)

import vera_facegate_control_log as facegate


def _response(body: str):
    class Response:
        status_code = 200
        text = body

    return Response()


class FaceGateControlLogTests(unittest.TestCase):
  def test_capture_parser_keeps_event_pointer_and_no_profile_fields(self):
    body = """<html>
root.CAPTURE.sessionid=15
root.CAPTURE.totalcount=1
root.CAPTURE.beginno=0
root.CAPTURE.rspcount=1
root.CAPTURE.ITEM0.uid=16338
root.CAPTURE.ITEM0.utime=2026-09-23/18:16:43
root.CAPTURE.ITEM0.dwfiletype=2
root.CAPTURE.ITEM0.dwfileindex=9
root.CAPTURE.ITEM0.dwfilepos=32571392
root.CAPTURE.ITEM0.utext=Snap
root.CAPTURE.ITEM0.udescription=Not Processed
root.CAPTURE.ITEM0.phone=0900000000
root.ERR.no=0
root.ERR.des=ok
</html>"""

    result = facegate._parse_capture_log_response(body)

    self.assertEqual(result["records"], [{
      "event_id": 16338,
      "occurred_at": "2026-09-23T18:16:43+07:00",
      "image_ref": {
        "file_type": 2, "file_index": 9, "file_position": 32571392,
        "time": "2026-09-23/18:16:43",
      },
      "image_available": True,
      "event_text": "Snap",
      "event_status": "Not Processed",
    }])
    self.assertNotIn("phone", repr(result))

  def test_capture_parser_rejects_success_without_capture_metadata(self):
    with self.assertRaisesRegex(ValueError, "không đúng định dạng Capture Log"):
      facegate._parse_capture_log_response("<html>root.ERR.no=0 root.ERR.des=ok</html>")

  def test_capture_closes_session_when_later_page_is_invalid(self):
    pages = iter([
      "root.CAPTURE.sessionid=33 root.CAPTURE.totalcount=21 root.CAPTURE.rspcount=20 root.ERR.no=0",
      "root.ERR.no=0 root.ERR.des=loginTimeout",
    ])
    closed = []
    with patch.dict("os.environ", {
      "VERA_FACEGATE_BASE_URL": "http://127.0.0.1:18080",
      "VERA_FACEGATE_USERNAME": "test-user", "VERA_FACEGATE_PASSWORD": "test-password",
    }):
      with self.assertRaisesRegex(ValueError, "không đúng định dạng Capture Log"):
        facegate.fetch_capture_log(
          "2026-09-23", "2026-09-23",
          get=lambda *args, **kwargs: _response(next(pages)),
          post=lambda url, *, params, **kwargs: closed.append(dict(params)) or _response("root.ERR.no=0"),
        )
    self.assertEqual(len(closed), 1)
    self.assertEqual(closed[0]["action"], "msg")
    self.assertEqual(closed[0]["group"], "CAPTURE")
    self.assertEqual(closed[0]["sessionid"], "33")

  def test_capture_image_uses_observed_get_image_query_and_bounds_payload(self):
    calls = []

    class ImageResponse:
      status_code = 200
      headers = {"Content-Type": "image/bmp; charset=binary"}

      def iter_content(self, *, chunk_size):
        self.chunk_size = chunk_size
        yield b"BMtest-data"

      def close(self):
        self.closed = True

    response = ImageResponse()

    def fake_get(url, *, params, **kwargs):
      calls.append((url, dict(params), kwargs))
      return response

    ref = {
      "file_type": 2, "file_index": 9, "file_position": 32571392,
      "time": "2026-09-23/18:16:43",
    }
    with patch.dict("os.environ", {
      "VERA_FACEGATE_BASE_URL": "http://127.0.0.1:18080",
      "VERA_FACEGATE_USERNAME": "test-user",
      "VERA_FACEGATE_PASSWORD": "test-password",
    }):
      content, media_type = facegate.fetch_capture_image(ref, get=fake_get)

    self.assertEqual((content, media_type), (b"BMtest-data", "image/bmp"))
    self.assertEqual(calls[0][0], "http://127.0.0.1:18080/webs/getImage")
    self.assertEqual(calls[0][1], {
      "action": "list", "group": "IMAGE", "dwfiletype": "2",
      "dwfileindex": "9", "dwfilepos": "32571392",
      "time": "2026-09-23/18:16:43",
      "RanId": calls[0][1]["RanId"],
    })
    self.assertRegex(calls[0][1]["RanId"], r"^[1-9][0-9]{7}$")
    self.assertEqual(calls[0][2]["auth"], ("test-user", "test-password"))
    self.assertTrue(calls[0][2]["stream"])
    self.assertFalse(calls[0][2]["allow_redirects"])
    self.assertEqual(response.chunk_size, 64 * 1024)
    self.assertTrue(response.closed)

  def test_capture_image_rejects_non_image_response_and_invalid_pointer(self):
    ref = {
      "file_type": 2, "file_index": 9, "file_position": 32571392,
      "time": "2026-09-23/18:16:43",
    }

    class HtmlResponse:
      status_code = 200
      headers = {"Content-Type": "text/html; charset=UTF-8"}
      content = b"<html>login</html>"

      def close(self):
        pass

    with patch.dict("os.environ", {
      "VERA_FACEGATE_BASE_URL": "http://127.0.0.1:18080",
      "VERA_FACEGATE_USERNAME": "test-user",
      "VERA_FACEGATE_PASSWORD": "test-password",
    }):
      with self.assertRaisesRegex(ValueError, "không trả về định dạng ảnh"):
        facegate.fetch_capture_image(ref, get=lambda *args, **kwargs: HtmlResponse())
      with self.assertRaisesRegex(ValueError, "không hợp lệ"):
        facegate.fetch_capture_image({**ref, "time": "bad"}, get=lambda *args, **kwargs: self.fail("network must not be called"))

  def test_control_log_parser_keeps_only_minimal_event_fields(self):
    body = """<html>
root.CONTROL.sessionid=19
root.CONTROL.totalcount=1
root.CONTROL.beginno=0
root.CONTROL.rspcount=1
root.CONTROL.ITEM0.uid=16331
root.CONTROL.ITEM0.utime=2026-09-23/17:17:07
root.CONTROL.ITEM0.ustatus=1
root.CONTROL.ITEM0.utype=0
root.CONTROL.ITEM0.uname=Nhân viên A
root.CONTROL.ITEM0.usimilarity=91.2
root.CONTROL.ITEM0.MjCardNo=12345678
root.CONTROL.ITEM0.dwfileindex=9
root.CONTROL.ITEM0.dwfilepos=30801920
root.ERR.no=0
root.ERR.des=ok
</html>"""

    result = facegate.parse_control_log_response(body)

    assert result["records"] == [{
        "event_id": 16331,
        "occurred_at": "2026-09-23T17:17:07+07:00",
        "device_name": "Nhân viên A",
        "status_code": "1",
        "type_code": "0",
        "registration_ref": None,
    }]
    assert "usimilarity" not in repr(result)
    assert "MjCardNo" not in repr(result)
    assert "dwfilepos" not in repr(result)

  def test_control_registration_reference_never_uses_capture_pointer(self):
    body = """root.CONTROL.sessionid=4 root.CONTROL.totalcount=1 root.CONTROL.rspcount=1
root.CONTROL.ITEM0.uid=10 root.CONTROL.ITEM0.uname=Test A root.CONTROL.ITEM0.utime=2026-09-23/19:50:05
root.CONTROL.ITEM0.dwfiletype=0 root.CONTROL.ITEM0.dwfileindex=0 root.CONTROL.ITEM0.dwfilepos=12000
root.CONTROL.ITEM0.cfiletype=2 root.CONTROL.ITEM0.cfileindex=9 root.CONTROL.ITEM0.cfilepos=34000
root.ERR.no=0"""
    result = facegate.parse_control_log_response(body)['records'][0]
    self.assertEqual(result['registration_ref'], {'file_type': 0, 'file_index': 0, 'file_position': 12000})
    self.assertNotIn('34000', repr(result))
    self.assertIsNone(facegate.registration_ref({'dwfiletype': 2, 'dwfileindex': 9, 'dwfilepos': 34000}))

  def test_profile_requires_exact_id_success_and_valid_registration_reference(self):
    body = 'root.LIST.uid=7 root.LIST.uname=Test A root.LIST.dwfiletype=0 root.LIST.dwfileindex=0 root.LIST.dwfilepos=12000 root.ERR.no=0'
    with patch.dict('os.environ', {'VERA_FACEGATE_BASE_URL': 'http://127.0.0.1:18080', 'VERA_FACEGATE_USERNAME': 'test', 'VERA_FACEGATE_PASSWORD': 'test'}):
      result = facegate.fetch_registered_profile(7, get=lambda *a, **kw: _response(body))
      self.assertEqual(result['profile_id'], 7)
      self.assertEqual(result['registration_ref']['file_position'], 12000)
      for invalid in [body.replace('uid=7', 'uid=8'), body.replace('no=0', 'no=1'), body.replace('dwfiletype=0', 'dwfiletype=2'), 'root.ERR.no=0']:
        with self.assertRaises(ValueError):
          facegate.fetch_registered_profile(7, get=lambda *a, **kw: _response(invalid))


  def test_fetch_uses_control_group_and_device_session_pagination(self):
    responses = iter([
        """root.CONTROL.sessionid=19 root.CONTROL.totalcount=21 root.CONTROL.beginno=0 root.CONTROL.rspcount=20
root.CONTROL.ITEM0.uid=100 root.CONTROL.ITEM0.utime=2026-09-23/08:00:00 root.CONTROL.ITEM0.uname=NV A root.CONTROL.ITEM0.ustatus=1
root.ERR.no=0 root.ERR.des=ok""",
        """root.CONTROL.sessionid=19 root.CONTROL.totalcount=21 root.CONTROL.beginno=20 root.CONTROL.rspcount=1
root.CONTROL.ITEM0.uid=99 root.CONTROL.ITEM0.utime=2026-09-23/09:00:00 root.CONTROL.ITEM0.uname=NV B root.CONTROL.ITEM0.ustatus=2
root.ERR.no=0 root.ERR.des=ok""",
    ])
    calls = []
    closes = []

    def fake_get(url, *, params, **kwargs):
        calls.append((url, dict(params), kwargs))
        return _response(next(responses))

    def fake_post(url, *, params, **kwargs):
        closes.append((url, params, kwargs))
        return _response("root.ERR.no=0")

    with patch.dict("os.environ", {"VERA_FACEGATE_BASE_URL": "http://127.0.0.1:18080", "VERA_FACEGATE_USERNAME": "test-user", "VERA_FACEGATE_PASSWORD": "test-password"}):
      result = facegate.fetch_control_log("2026-09-23", "2026-09-23", get=fake_get, post=fake_post)

    assert result["count"] == 2
    assert result["attendance_calculation_enabled"] is False
    assert len(calls) == 2
    assert all(call[1]["group"] == "CONTROL" for call in calls)
    assert calls[0][1]["sessionid"] == "0"
    assert calls[1][1]["sessionid"] == "19"
    assert calls[1][1]["beginno"] == "20"
    assert all(call[2]["allow_redirects"] is False for call in calls)
    assert all(call[2]["auth"] == ("test-user", "test-password") for call in calls)
    assert len(closes) == 1
    assert closes[0][1]["action"] == "msg"
    assert closes[0][1]["group"] == "CONTROL"
    assert closes[0][1]["sessionid"] == "19"
    assert closes[0][1]["RanId"] != calls[-1][1]["RanId"]
    assert closes[0][2]["auth"] == ("test-user", "test-password")


  def test_fetch_rejects_invalid_or_unbounded_date_ranges(self):
    for start, end in (("2026-09-24", "2026-09-23"), ("2026-01-01", "2026-03-05")):
      with self.subTest(start=start, end=end), patch.dict("os.environ", {"VERA_FACEGATE_BASE_URL": "http://127.0.0.1:18080", "VERA_FACEGATE_USERNAME": "test-user", "VERA_FACEGATE_PASSWORD": "test-password"}):
        with self.assertRaises(ValueError):
          facegate.fetch_control_log(start, end, get=lambda *args, **kwargs: self.fail("network must not be called"))

  def test_fetch_requires_server_side_basic_auth_configuration(self):
    with patch.dict("os.environ", {"VERA_FACEGATE_BASE_URL": "http://127.0.0.1:18080"}, clear=True):
      with self.assertRaisesRegex(RuntimeError, "xác thực phía máy chủ"):
        facegate.fetch_control_log("2026-09-23", "2026-09-23", get=lambda *args, **kwargs: self.fail("network must not be called"))


  def test_fetch_builds_bounded_control_log_query(self):
    captured = {}

    def fake_get(url, *, params, **kwargs):
        captured["url"] = url
        captured["params"] = params
        captured["kwargs"] = kwargs
        return _response("""root.CONTROL.sessionid=7 root.CONTROL.totalcount=1 root.CONTROL.beginno=0 root.CONTROL.rspcount=1
root.CONTROL.ITEM0.uid=7 root.CONTROL.ITEM0.utime=2026-09-23/11:00:00 root.CONTROL.ITEM0.uname=NV root.CONTROL.ITEM0.ustatus=1
root.ERR.no=0 root.ERR.des=ok""")

    with patch.dict("os.environ", {"VERA_FACEGATE_BASE_URL": "http://127.0.0.1:18080", "VERA_FACEGATE_USERNAME": "test-user", "VERA_FACEGATE_PASSWORD": "test-password"}):
      response = facegate.fetch_control_log("2026-09-23", "2026-09-23", get=fake_get, post=lambda *args, **kwargs: _response("root.ERR.no=0"))

    assert captured["url"] == "http://127.0.0.1:18080/webs/getControl"
    assert captured["params"]["action"] == "list"
    assert captured["params"]["group"] == "CONTROL"
    assert captured["params"]["ustatus"] == "0"
    assert captured["params"]["usex"] == "2"
    assert captured["params"]["uage"] == "0-100"
    assert captured["params"]["MjCardNo"] == "0"
    assert captured["params"]["begintime"] == "2026-09-23/00:00:00"
    assert captured["params"]["endtime"] == "2026-09-23/23:59:59"
    assert captured["params"]["reqcount"] == "20"
    assert captured["kwargs"]["timeout"] == (3, 8)
    assert captured["kwargs"]["auth"] == ("test-user", "test-password")
    assert response["status_semantics_verified"] is False


  def test_parser_rejects_device_errors_and_login_html(self):
    with self.assertRaisesRegex(ValueError, "trả lỗi"):
      facegate.parse_control_log_response("root.CONTROL.totalcount=0 root.ERR.no=7")
    with self.assertRaisesRegex(ValueError, "không đúng định dạng"):
      facegate.parse_control_log_response("<html><title>login</title></html>")
    with self.assertRaisesRegex(ValueError, "không đúng định dạng"):
      facegate.parse_control_log_response("root.CAPTURE.totalcount=1 root.CAPTURE.sessionid=2 root.CAPTURE.rspcount=1 root.ERR.no=0")


class FaceGateMappingRouteTests(unittest.TestCase):
  def setUp(self):
    import copy
    import json
    from contextlib import contextmanager
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    from vera_web_v2_snapshot import install_snapshot_routes

    class Identity(BaseModel):
      username: str = 'admin-test'
      role: str = 'admin'

    self.ident = Identity()
    self.rows = []
    self.connection_open = False
    self.sql = []
    owner = self

    class Connection:
      def execute(self, statement, params):
        sql = str(statement)
        owner.sql.append(sql)
        if sql.startswith('SELECT username'):
          value = params['username'] if params['username'] == 'vera-test' else None
        elif sql.startswith('SELECT value_json'):
          value = copy.deepcopy(owner.rows)
        else:
          value = None
          if sql.startswith('UPDATE vera_app_setting'):
            owner.rows = json.loads(params['value'])
        return SimpleNamespace(scalar_one_or_none=lambda: value)

    class Engine:
      @contextmanager
      def connect(self):
        owner.connection_open = True
        try:
          yield Connection()
        finally:
          owner.connection_open = False
      begin = connect

    app = FastAPI()
    install_snapshot_routes(app, engine_instance=lambda: Engine(), current_identity=lambda: self.ident,
                            require_feature=lambda *a: None, identity_type=Identity)
    self.client = TestClient(app)
    self.ref = {'file_type': 0, 'file_index': 0, 'file_position': 12000}
    self.profile = {'profile_id': 7, 'device_name': 'Test A', 'registration_ref': self.ref}
    self.body = {**self.profile, 'username': 'vera-test', 'employee_code': 'EMPTEST', 'confirmed': True}
    self.env = patch.dict('os.environ', {'VERA_FACEGATE_DEVICE_ID': 'device-test'})
    self.env.start()
    self.addCleanup(self.env.stop)

  def device_read(self, uid):
    self.assertFalse(self.connection_open, 'Device HTTP must run outside database connections')
    return self.profile

  def test_admin_confirmation_required_before_device_or_database_access(self):
    with patch.object(facegate, 'fetch_registered_profile') as read:
      self.ident.role = 'nhanvien'
      self.assertEqual(self.client.post('/v2/devices/facegate-mappings', json=self.body).status_code, 403)
      self.assertEqual(self.client.post('/v2/devices/facegate-mappings/check', json={'registration_ref': self.ref}).status_code, 403)
      self.ident.role = 'admin'
      self.assertEqual(self.client.post('/v2/devices/facegate-mappings', json={**self.body, 'confirmed': False}).status_code, 400)
      read.assert_not_called()
      self.assertEqual(self.sql, [])

  def test_save_conflicts_and_check_live_profile(self):
    with patch.object(facegate, 'fetch_registered_profile', side_effect=self.device_read):
      response = self.client.post('/v2/devices/facegate-mappings', json=self.body)
      self.assertEqual(response.status_code, 200, response.text)
      self.assertTrue(any('FOR UPDATE' in sql for sql in self.sql))
      result = self.client.post('/v2/devices/facegate-mappings/check', json={'registration_ref': self.ref})
      self.assertEqual(result.json()['status'], 'reference_match')
      self.assertEqual(result.json()['employee_code'], 'EMPTEST')
      # Same profile cannot silently move to a different employee code.
      self.assertEqual(self.client.post('/v2/devices/facegate-mappings', json={**self.body, 'employee_code': 'OTHER'}).status_code, 409)
      # A changed reference invalidates both the old preview and a log check.
      self.profile = {**self.profile, 'registration_ref': {**self.ref, 'file_position': 13000}}
      self.assertEqual(self.client.post('/v2/devices/facegate-mappings', json=self.body).status_code, 409)
      self.assertEqual(self.client.post('/v2/devices/facegate-mappings/check', json={'registration_ref': self.ref}).json()['status'], 'changed')
    with patch.object(facegate, 'fetch_registered_profile', side_effect=ConnectionError('Không kết nối được thiết bị.')):
      self.assertEqual(self.client.post('/v2/devices/facegate-mappings/check', json={'registration_ref': self.ref}).status_code, 502)

  def test_unmapped_reference_does_not_read_device(self):
    with patch.object(facegate, 'fetch_registered_profile') as read:
      result = self.client.post('/v2/devices/facegate-mappings/check', json={'registration_ref': self.ref})
      self.assertEqual(result.json()['status'], 'unmapped')
      read.assert_not_called()


if __name__ == "__main__":
  unittest.main()
