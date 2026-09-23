from __future__ import annotations

import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    # The scratch image omits app requirements; tests inject their own HTTP fake.
    sys.modules["requests"] = SimpleNamespace(get=None, RequestException=OSError)

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
    }]
    assert "usimilarity" not in repr(result)
    assert "MjCardNo" not in repr(result)
    assert "dwfilepos" not in repr(result)


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

    def fake_get(url, *, params, **kwargs):
        calls.append((url, dict(params), kwargs))
        return _response(next(responses))

    with patch.dict("os.environ", {"VERA_FACEGATE_BASE_URL": "http://127.0.0.1:18080", "VERA_FACEGATE_USERNAME": "test-user", "VERA_FACEGATE_PASSWORD": "test-password"}):
      result = facegate.fetch_control_log("2026-09-23", "2026-09-23", get=fake_get)

    assert result["count"] == 2
    assert result["attendance_calculation_enabled"] is False
    assert len(calls) == 2
    assert all(call[1]["group"] == "CONTROL" for call in calls)
    assert calls[0][1]["sessionid"] == "0"
    assert calls[1][1]["sessionid"] == "19"
    assert calls[1][1]["beginno"] == "20"
    assert all(call[2]["allow_redirects"] is False for call in calls)
    assert all(call[2]["auth"] == ("test-user", "test-password") for call in calls)


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
      response = facegate.fetch_control_log("2026-09-23", "2026-09-23", get=fake_get)

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


if __name__ == "__main__":
  unittest.main()
