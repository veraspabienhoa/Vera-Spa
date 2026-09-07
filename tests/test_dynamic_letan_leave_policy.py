from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_letan_policy_defaults_show_five_named_groups():
    from vera_letan_leave_policy import normalize_policy

    policy = normalize_policy(None)
    assert policy["enabled"] is True
    assert [group["name"] for group in policy["groups"]] == [f"Nhóm {index}" for index in range(1, 6)]
    assert all(len(group["reasons"]) == 3 for group in policy["groups"])


def test_letan_policy_can_be_paused_and_groups_changed():
    from vera_letan_leave_policy import normalize_policy, reason_group

    policy = normalize_policy({
        "enabled": False,
        "groups": [
            {"id": f"group_{index}", "name": f"Nhóm sửa {index}", "reasons": [
                f"Lý do {index}.1", f"Lý do {index}.2", f"Lý do {index}.3",
            ]}
            for index in range(1, 6)
        ],
    })
    assert policy["enabled"] is False
    assert reason_group(policy, "Lý do 3.2")["name"] == "Nhóm sửa 3"


def test_backend_guard_reads_live_policy_and_falls_back_when_paused():
    guard = (ROOT / "vera_web_v2_letan_leave_guard.py").read_text(encoding="utf-8")
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")
    rules = (ROOT / "vera_web_v2_rules.py").read_text(encoding="utf-8")

    assert "policy = load_letan_leave_policy(conn)" in guard
    assert 'if not policy["enabled"]:' in guard
    assert "_reason_group(old_reason, norm, policy)" in guard
    assert '"letan_leave_policy": letan_leave_policy' in api
    assert '@app.put("/v2/rules/letan-leave-policy")' in rules
    assert "Phải có đúng 5 nhóm, mỗi nhóm gồm 3 Lý do nghỉ riêng biệt." in rules


def test_rules_page_has_activation_pause_and_edit_controls_for_each_group():
    component = (ROOT / "web-v2/src/pages/LetanLeavePolicyRules.jsx").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/RulesPage.jsx").read_text(encoding="utf-8")
    permissions = (ROOT / "web-v2/src/lib/leaveRecordPermissions.js").read_text(encoding="utf-8")

    assert "Tạm ngưng kích hoạt" in component
    assert "Kích hoạt nội quy" in component
    assert "Lưu sửa đổi nội quy" in component
    assert "group.reasons.map" in component
    assert "saveLetanLeavePolicy" in page
    assert "letanLeavePolicy?.enabled === false" in permissions
    assert "letanLeavePolicy?.groups?.map" in permissions
