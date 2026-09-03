from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_domain_is_allowed_by_python_api_and_cloud_build():
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")
    build = (ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")
    assert '"https://app.veraspa.vn"' in api
    assert '"https://veraspabienhoa.github.io"' in api
    assert "_REQUIRED_WEB_ORIGINS" in api
    assert "VERA_V2_CORS_ORIGINS=https://app.veraspa.vn,https://veraspabienhoa.github.io" in build
    assert ').split(",")' in api


def test_idempotent_payroll_save_retries_once_on_transport_failure():
    client = (ROOT / "web-v2/src/lib/api.js").read_text(encoding="utf-8")
    payroll = (ROOT / "vera_web_v2_payroll.py").read_text(encoding="utf-8")
    assert "path === '/v2/payroll/save' ? 2 : 1" in client
    assert "DELETE FROM payroll_history_rows WHERE batch_id=:label" in payroll
    assert "pg_advisory_xact_lock" in payroll
