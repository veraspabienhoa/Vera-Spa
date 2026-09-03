from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_locker_and_letan_rules_share_the_payroll_system_settings():
    rules = source("vera_web_v2_rules.py")
    payroll = source("vera_web_v2_department_payroll.py")

    assert 'DEPARTMENT_RULES = {"locker": "Locker", "letan": "Lễ tân"}' in rules
    assert 'DEPARTMENT_RULES_CATEGORY = "payroll"' in rules
    assert 'return f"department_{department}_penalty_rules"' in rules
    assert '_setting_key(department, "penalty_rules")' in payroll
    assert '@app.put("/v2/rules/department/{department}")' in rules
    assert "Chỉ Admin được thay đổi nội quy Locker/Lễ tân" in rules


def test_rules_page_starts_empty_and_allows_admin_to_apply_later():
    page = source("web-v2/src/pages/RulesPage.jsx")
    client = source("web-v2/src/lib/api.js")

    assert "NỘI QUY LOCKER / LỄ TÂN" in page
    assert "Chưa có nội dung phạt. Admin sẽ nhập sau." in page
    assert "Thêm nội quy" in page
    assert "Áp dụng {label}" in page
    assert "saveDepartmentRules" in client
