"""Date authorization through real indexed PostgreSQL HTTP read paths."""
from copy import deepcopy
from datetime import datetime
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event

import vera_live_tour_query as query
import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, RouteIdentity
from test_live_tour_date_permissions import (
    BASE_GRANTS, SECTIONS, TODAY, YESTERDAY, date_feature, dated_state,
    grants_for, prefix, row_ids, section_rows,
)
from test_live_tour_resource_postgres import database


@pytest.fixture
def dated_database(database):
    with database.begin() as conn:
        query.ensure_schema(conn)
        store.lock(conn)
        before, _, _ = store.read(conn)
        state = deepcopy(before)
        state.update(dated_state())
        old_invoice = deepcopy(next(row for row in state["invoices"] if row["id"] == f"i-{YESTERDAY}"))
        new_invoice = deepcopy(next(row for row in state["invoices"] if row["id"] == f"i-{TODAY}"))
        old_pending = deepcopy(next(row for row in state["pending"] if row["id"] == f"p-{YESTERDAY}"))
        new_pending = deepcopy(next(row for row in state["pending"] if row["id"] == f"p-{TODAY}"))
        state["invoice_changes"] = [{"id": "date-invoice-change", "at": NOW.isoformat(),
                                      "before": old_invoice, "after": new_invoice}]
        state["pending_changes"] = [{"id": "date-pending-change", "at": NOW.isoformat(),
                                      "before": old_pending, "after": new_pending}]
        state["backups"] = [{"id": "date-backup", "created_at": NOW.isoformat(),
                              "snapshot": {"invoices": [old_invoice, new_invoice], "pending": [old_pending, new_pending]}}]
        store.write(conn, before, state, "date-permission-fixture")
    return database


def client_for(database, monkeypatch, features):
    class Identity(RouteIdentity):
        role: str = "letan"

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(live, "datetime", FixedDateTime)

    def require(_conn, _ident, feature):
        if feature not in features:
            raise HTTPException(403, feature)

    app = FastAPI()
    live.install_live_tour_routes(
        app, engine_instance=lambda: database, current_identity=lambda: Identity(),
        require_feature=require, feature_allowed=lambda _c, _i, feature: feature in features,
        feature_map=lambda _c, _i, keys: {key: key in features for key in keys}, identity_type=Identity,
    )
    return TestClient(app)


@pytest.mark.parametrize("section", ["pending", "invoices", "reports"])
def test_indexed_collection_uses_canonical_today_before_counts_and_paging(dated_database, monkeypatch, section):
    features = grants_for(**{key: "all" for key in SECTIONS})
    features.remove(date_feature(section, "all"))
    features.add(date_feature(section, "today"))
    client = client_for(dated_database, monkeypatch, features)
    statements = []

    def collect(_conn, _cursor, sql, _params, _context, _many):
        statements.append(sql)

    event.listen(dated_database, "before_cursor_execute", collect)
    try:
        response = client.get(f"/v2/live-tour/collections/{section}", params={"preset": "today", "page_size": 1})
    finally:
        event.remove(dated_database, "before_cursor_execute", collect)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == data["pages"] == 1
    assert row_ids(section_rows(data["data"], section)) == {f"{prefix(section)}-{TODAY}"}
    assert any(sql.startswith("WITH ready AS") for sql in statements), "Expected the real indexed collection path"
    if section == "reports":
        assert data["data"]["report_totals"]["totalRevenue"] == 110
        assert data["data"]["report_totals"]["invoiceCount"] == 1


@pytest.mark.parametrize("section", SECTIONS)
@pytest.mark.parametrize("params", [{}, {"preset": "today"}, {"date_from": TODAY, "date_to": TODAY}])
def test_indexed_collection_denies_requests_without_date_grants(dated_database, monkeypatch, section, params):
    client = client_for(dated_database, monkeypatch, set(BASE_GRANTS))
    response = client.get(f"/v2/live-tour/collections/{section}", params=params)
    assert response.status_code == 403, response.text


def test_restricted_report_secondary_ledgers_have_filtered_totals_and_fallback_parity(dated_database, monkeypatch):
    client = client_for(dated_database, monkeypatch, grants_for(reports="month", invoices="yesterday", pending="today"))
    requests = [
        ("/v2/live-tour/reports", {"tab": "revenue", "preset": "month", "page_size": 1}),
        ("/v2/live-tour/reports", {"tab": "invoices", "preset": "month", "page_size": 1}),
        ("/v2/live-tour/collections/reports", {"preset": "month", "page_size": 1}),
        ("/v2/live-tour/customers/c1/history", {}),
    ]
    first = [client.get(path, params=params) for path, params in requests]
    assert all(response.status_code == 200 for response in first), [response.text for response in first]
    revenue, invoices, collection, history = [response.json() for response in first]
    assert revenue["total"] == 5 and revenue["summary"]["totalRevenue"] == 550
    assert revenue["summary"]["pendingInvoiceCount"] == 1
    assert all(row["id"] == f"i-{YESTERDAY}" for row in revenue["invoices"])
    assert invoices["total"] == invoices["pages"] == 1
    assert row_ids(invoices["rows"]) == {f"i-{YESTERDAY}"}
    assert collection["total"] == 5 and collection["data"]["report_totals"]["totalRevenue"] == 550
    assert row_ids(history["invoices"]) == {f"i-{YESTERDAY}"}
    assert row_ids(history["pending"]) == {f"p-{TODAY}"}
    monkeypatch.setattr(query, "schema_ready", lambda _conn: False)
    fallback = [client.get(path, params=params) for path, params in requests]
    assert all(response.status_code == 200 for response in fallback)
    assert [response.json() for response in first] == [response.json() for response in fallback]


def test_indexed_report_collection_does_not_return_receipts_outside_invoice_scope(dated_database, monkeypatch):
    client = client_for(dated_database, monkeypatch, grants_for(reports="today", invoices="yesterday"))
    response = client.get("/v2/live-tour/collections/reports", params={"preset": "today"})
    assert response.status_code == 200, response.text
    assert row_ids(response.json()["data"]["report_rows"]) == {f"r-{TODAY}"}
    assert response.json()["data"]["state"]["invoices"] == []
    assert response.json()["data"]["report_totals"]["invoiceCount"] == 1


def test_history_nested_snapshots_and_backup_numbers_are_scoped_on_indexed_storage(dated_database, monkeypatch):
    client = client_for(dated_database, monkeypatch, grants_for(**{section: "today" for section in SECTIONS}))
    response = client.get("/v2/live-tour/collections/history", params={"preset": "today"})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    serialized = json.dumps({key: data[key] for key in ("invoice_changes", "pending_changes", "backups")})
    assert f"I-{YESTERDAY}" not in serialized and f"P-{YESTERDAY}" not in serialized
    assert data["backups"][0]["bill_numbers"] == sorted([f"I-{TODAY}", f"P-{TODAY}"])
    assert "snapshot" not in data["backups"][0]
    monkeypatch.setattr(query, "schema_ready", lambda _conn: False)
    fallback = client.get("/v2/live-tour/collections/history", params={"preset": "today"})
    assert fallback.status_code == 200 and fallback.json() == response.json()


def test_history_hidden_number_does_not_probe_indexed_count_or_matching_event(dated_database, monkeypatch):
    client = client_for(dated_database, monkeypatch, grants_for(history="today", invoices="today", pending="today"))
    params = {"preset": "today", "bill_no": f"I-{YESTERDAY}"}
    response = client.get("/v2/live-tour/collections/history", params=params)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0
    assert response.json()["data"]["invoice_changes"] == []
    monkeypatch.setattr(query, "schema_ready", lambda _conn: False)
    fallback = client.get("/v2/live-tour/collections/history", params=params)
    assert fallback.status_code == 200 and fallback.json() == response.json()


def test_backup_only_reader_cannot_obtain_audit_rows_through_indexed_history(dated_database, monkeypatch):
    features = {"live_tour_view", "live_tour_backup", date_feature("history", "today")}
    client = client_for(dated_database, monkeypatch, features)
    response = client.get("/v2/live-tour/collections/history", params={"preset": "today"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1 and data["data"]["backups"][0]["bill_numbers"] == []
    assert data["data"]["audit"] == data["data"]["invoice_changes"] == data["data"]["pending_changes"] == []
