from types import SimpleNamespace

from vera_web_v2_violation_unlimited import install_violation_unlimited


class FakeApp:
    def __init__(self):
        self.state = SimpleNamespace()
        self.routes = {}

    def get(self, path):
        def decorator(fn):
            self.routes[path] = fn
            return fn
        return decorator


class FakeShared:
    def __init__(self):
        self.rules = {
            "Về sớm KHÔNG phép": {"leave_type": "Không phép"},
            "Qua tour KHÔNG phép": {"leave_type": "Vi phạm"},
            "Lỗi vi phạm khác": {"leave_type": "Vi phạm"},
            "Nghỉ CÓ phép": {"leave_type": "Có phép"},
            "Nghỉ phát sinh": {"leave_type": "Phát sinh"},
            "Legacy KHÔNG phép": {"leave_type": ""},
        }

    @staticmethod
    def norm(value):
        return str(value or "").strip().lower()

    def _reason_item(self, _conn, reason):
        return self.rules[reason]

    @staticmethod
    def group(reason):
        key = str(reason or "").lower()
        if "không phép" in key:
            return "khong_phep"
        if "phát sinh" in key:
            return "phat_sinh"
        if "có phép" in key:
            return "co_phep"
        return ""


def test_violation_type_is_not_grouped_as_khong_phep():
    app = FakeApp()
    shared = FakeShared()
    install_violation_unlimited(app, shared_module=shared)

    assert shared._policy_group(None, "Về sớm KHÔNG phép") == "khong_phep"
    assert shared._policy_group(None, "Qua tour KHÔNG phép") == ""
    assert shared._policy_group(None, "Lỗi vi phạm khác") == ""
    assert shared._policy_group(None, "Nghỉ CÓ phép") == "co_phep"
    assert shared._policy_group(None, "Nghỉ phát sinh") == "phat_sinh"
    assert shared._policy_group(None, "Legacy KHÔNG phép") == "khong_phep"
