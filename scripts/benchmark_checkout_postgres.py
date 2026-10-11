"""Synthetic checkout load through real API, auth, locks and PostgreSQL commits.

Requires a *local disposable* PostgreSQL instance; creates/drops only randomly
named vera_phase3_bench_* databases. Never pass a production database. Outbound
HTTP/DNS/socket traffic is blocked before application imports. See the companion
document for definitions, caveats and the exact baseline/candidate protocol.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import platform
import socket
import statistics
import subprocess
import sys
import threading
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def block_external_network():
    """Block proxy-host connections too; this is solely a benchmark boundary."""
    import requests
    allowed = {"127.0.0.1", "::1", "localhost", b"127.0.0.1", b"::1", b"localhost", None}
    connect, connect_ex, resolve = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
    send = requests.sessions.Session.send
    def guarded_connect(sock, address):
        if not isinstance(address, tuple) or address[0] not in allowed:
            raise OSError("External network disabled by checkout benchmark")
        return connect(sock, address)
    def guarded_connect_ex(sock, address):
        if not isinstance(address, tuple) or address[0] not in allowed:
            raise OSError("External network disabled by checkout benchmark")
        return connect_ex(sock, address)
    def guarded_resolve(host, *args, **kwargs):
        if host not in allowed:
            raise OSError("External DNS disabled by checkout benchmark")
        return resolve(host, *args, **kwargs)
    def guarded_send(session, request, **kwargs):
        if urlsplit(request.url).hostname not in allowed:
            raise requests.ConnectionError("External HTTP disabled by checkout benchmark")
        return send(session, request, **kwargs)
    socket.socket.connect, socket.socket.connect_ex = guarded_connect, guarded_connect_ex
    socket.getaddrinfo, requests.sessions.Session.send = guarded_resolve, guarded_send


block_external_network()
import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
import vera_web_v2_api as api
import vera_web_v2_local_auth as local_auth
import vera_web_v2_live_tour as live
import vera_live_tour_relational as relational
import vera_live_tour_resource_store as store
import vera_live_tour_receipts as receipts
from vera_live_tour_cutover import run as cutover
from vera_live_tour_timing import ActionTiming

NOW = datetime(2026, 9, 5, 15, 0, tzinfo=live.VN_TZ)
CURRENT = ContextVar("checkout_benchmark_metrics", default=None)


def package_versions():
    result = {}
    for package in ("fastapi", "starlette", "httpx", "httpx2", "SQLAlchemy", "psycopg"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            pass
    return result


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def percentiles(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "p50": None, "p95": None}
    return {"n": len(values), "p50": round(statistics.median(values), 3),
            "p95": round(values[max(0, math.ceil(len(values) * .95) - 1)], 3)}


class MetricsCursor(psycopg.Cursor):
    def execute(self, query, params=None, **kwargs):
        self._bench_ledger = "pg_try_advisory_xact_lock" in str(query) and any(
            str(value) == "vera:resource:live_tour_ledger:invoices"
            for value in (params.values() if isinstance(params, dict) else params or []))
        started = perf_counter()
        result = super().execute(query, params, **kwargs)
        metric = CURRENT.get()
        if metric is not None:
            metric["sql_count"] += 1
            metric["sql_execute_ms"] += (perf_counter() - started) * 1000
            if self.description is not None:
                metric["returned_rows"] += max(0, self.rowcount)
        return result

    def _record(self, rows):
        metric = CURRENT.get()
        if metric is not None:
            if self._bench_ledger and rows and rows[0][0] is True:
                metric["ledger_acquired"] = perf_counter()
            if metric["byte_probe"]:
                metric["decoded_result_bytes"] += sum(len(compact_json(row).encode("utf-8")) for row in rows)
        return rows

    def fetchone(self):
        row = super().fetchone()
        self._record([] if row is None else [row])
        return row

    def fetchall(self):
        return self._record(super().fetchall())

    def fetchmany(self, size=None):
        rows = super().fetchmany() if size is None else super().fetchmany(size)
        return self._record(rows)


class MetricsConnection(psycopg.Connection):
    def commit(self):
        result = super().commit()
        metric = CURRENT.get()
        if metric is not None and metric.get("ledger_acquired") is not None:
            metric["ledger_hold_ms"] = (perf_counter() - metric.pop("ledger_acquired")) * 1000
        return result


class MeasuredTiming(ActionTiming):
    def emit(self, outcome="ok"):
        metric = CURRENT.get()
        if metric is not None:
            metric["phases_ms"] = dict(self.phases)
            metric["route_business_ms"] = (perf_counter() - self.started) * 1000


class FixedDateTime(live.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


@asynccontextmanager
async def isolated_lifespan(application):
    """Exclude projection/scheduler jobs identically at both source revisions."""
    yield


class MetricsMiddleware:
    def __init__(self, app, records):
        self.app, self.records = app, records

    async def __call__(self, scope, receive, send):
        identifier = dict(scope.get("headers", [])).get(b"x-benchmark-id", b"").decode()
        metric = self.records.get(identifier)
        token = CURRENT.set(metric)
        try:
            await self.app(scope, receive, send)
        finally:
            CURRENT.reset(token)


def make_dataset(history, operations):
    state = live._empty_state(NOW)
    state["employees"], state["customers"] = [], []
    bodies = []
    for index in range(operations):
        n = index + 1
        employee = {
            "id": f"e{n}", "stt": str(n), "name": f"Synthetic employee {n}",
            "appointment": "", "service": "Body 90", "service_price": 100,
            "request": "", "room": f"{n}.1", "status": "CHO THANH TOÁN",
            "duration": 90, "started_at": "", "completed_at": "",
            "payment_status": "CHO THANH TOÁN", "tour_count": 0, "request_count": 0,
            "work_status": "Đi làm", "shift": "Ca 1", "break_started_at": "",
            "clock_out": "", "clock_in": "", "note": "", "hidden": False,
            "vip": False, "sort_index": index, "customer_id": f"c{n}",
            "customer_name": f"Synthetic customer {n}", "customer_phone": f"090{n:07}",
        }
        state["employees"].append(employee)
        state["customers"].append({"id":f"c{n}", "name":employee["customer_name"],
            "phone":employee["customer_phone"], "combo_purchases":[{
                "id": f"purchase-{n}", "combo_name":"Synthetic combo", "total":10,
                "used":0, "remaining":10, "unlimited":True}]})
        scenario = ("auto", "manual", "pending", "combo")[index % 4]
        payload = {"employee_id":f"e{n}", "payment_method":"TIỀN MẶT", "tip":11}
        if scenario == "manual":
            payload["bill_no"] = f"BENCH-MANUAL-{n:06}"
        elif scenario == "pending":
            pending = live._apply_action(state, "move_pending", {"employee_id":f"e{n}"}, "admin", NOW)["pending"]
            pending["id"] = f"pending-{n}"
            payload = {"pending_id":pending["id"], "payment_method":"TIỀN MẶT", "tip":11}
        elif scenario == "combo":
            payload.update(payment_method="COMBO", combo_purchase_id=f"purchase-{n}", customer_id=f"c{n}")
        bodies.append({"action":"checkout", "response_view":"receipt", "payload":payload,
                       "idempotency_key":f"benchmark-payment-{n:06}", "scenario":scenario})
    for service in state["services"]:
        if service["name"] == "Body 90":
            service["price"] = 100
    state["invoices"] = [{"id":f"history-invoice-{n}", "bill_no":f"VERA-20260905-{n+1:04}",
        "business_date":"2026-09-05", "total":111, "tip":11, "payment_method":"TIỀN MẶT",
        "entries":[{"employee_id":"historical", "service":"Body 90", "total":100,
                    "note":"Synthetic historical detail. " * 20}]} for n in range(history)]
    state["reports"] = [{"id":f"history-report-{n}", "invoice_id":row["id"], "total":111,
                         "tip":11, "business_date":"2026-09-05"} for n, row in enumerate(state["invoices"])]
    state["invoice_changes"] = [{"id":f"history-void-{n}", "before":{
        "id":f"voided-{n}", "bill_no":f"VOID-USED-{n}", "entries":[{"note":"Synthetic void history"}]}}
        for n in range(history // 10)]
    state["audit"] = [{"id":f"history-audit-{n}", "detail":{"note":"Synthetic historical audit"}}
                      for n in range(min(history, 2000))]
    state["pending_changes"] = []
    state["idempotency"] = {f"historic-receipt-{n}":{"action":"checkout", "status":"completed",
        "result":{"invoice":deepcopy(row)}} for n, row in enumerate(state["invoices"])}
    # Do not let fixture-only UUID audit entries make cross-version datasets differ.
    for employee in state["employees"]:
        if isinstance(employee.get("last_assignment_display"), dict):
            employee["last_assignment_display"]["pending_id"] = f"pending-{employee['id'][1:]}"
    return state, bodies


def engine_for(url, size):
    return create_engine(url, pool_size=size, max_overflow=0, pool_timeout=5,
        creator=lambda: MetricsConnection.connect(
            cursor_factory=MetricsCursor,
            **make_url(url).translate_connect_args(username="user", database="dbname")))


def setup_database(url, history, operations, activate):
    # Database names and host are controlled by this harness, never caller SQL.
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    database = "vera_phase3_bench_" + uuid4().hex
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{database}"'))
    target = make_url(url).set(database=database)
    engine = engine_for(target, 4)
    auth_engine = engine_for(target, 2)
    state, bodies = make_dataset(history, operations)
    os.environ["VERA_LIVE_TOUR_RELATIONAL_MODE"] = "shadow"
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE vera_app_setting(category text,setting_key text,value_json jsonb,
            source text,updated_by text,revision bigint,created_at timestamptz DEFAULT NOW(),
            updated_at timestamptz DEFAULT NOW(),PRIMARY KEY(category,setting_key))"""))
        conn.execute(text("""CREATE TABLE employees(username text PRIMARY KEY,full_name text,bank_name text,
            bank_account text,role text,email text,password_value text,login_locked boolean,payload jsonb,
            work_shift text,shift_start_date date,rotation_cycle integer)"""))
        conn.execute(text("""INSERT INTO employees(username,full_name,bank_name,bank_account,role,email,password_value,login_locked,payload)
            VALUES('admin','Synthetic administrator','','','admin','',
            'synthetic-only',false,'{}'::jsonb)"""))
        blank = live._empty_state(NOW)
        conn.execute(text("""INSERT INTO vera_app_setting(category,setting_key,value_json,revision)
            VALUES('live_tour','state',CAST(:state AS jsonb),7)"""), {"state":relational._json(blank)})
        assert cutover(conn)["ok"]
    os.environ["VERA_LIVE_TOUR_RELATIONAL_MODE"] = "active"
    with engine.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        seeded = deepcopy(before)
        seeded.update(state)
        store.write(conn, before, seeded, "fixture")
        receipts.migrate(conn)
        if activate:
            module_name, function_name = activate.split(":", 1)
            getattr(importlib.import_module(module_name), function_name)(conn)
        revision = store.read(conn)[1]
    token = local_auth.new_access_token()
    session = {"kind":local_auth.SESSION_RECORD_KIND, "version":local_auth.STORE_VERSION,
        "auth_user_id":"00000000-0000-0000-0000-000000000001", "employee_username":"admin",
        "access_token_hash":local_auth.token_digest(token),
        "credential_fingerprint":local_auth.credential_fingerprint("admin", "synthetic-only"),
        "access_expires_at":int(datetime.now(timezone.utc).timestamp()) + 3600}
    with auth_engine.begin() as conn:
        conn.execute(text("""INSERT INTO vera_app_setting(category,setting_key,value_json,revision)
            VALUES(:category,'benchmark-session',CAST(:session AS jsonb),1)"""),
            {"category":local_auth.SESSION_CATEGORY,"session":compact_json(session)})
    api._engine, api._auth_engine_instance = engine, lambda: auth_engine
    local_auth._SCHEMA_READY = False
    local_auth.ensure_local_auth_schema(auth_engine)
    api._permission_cache.update(loaded_at=0, payload={}, revision=None)
    for body in bodies:
        body["expected_revision"] = revision
    with engine.begin() as conn:
        conn.execute(text("ANALYZE"))
    return admin, database, engine, auth_engine, token, bodies, hashlib.sha256(compact_json(state).encode()).hexdigest()


def new_metric(byte_probe=False):
    return {"sql_count":0, "sql_execute_ms":0.0, "returned_rows":0,
            "decoded_result_bytes":0, "byte_probe":byte_probe}


def summarize(metrics):
    successes = [m for m in metrics if m["status"] == 200]
    return {"attempts":len(metrics), "status_counts":dict(Counter(str(m["status"]) for m in metrics)),
        "successes":len(successes), "successful_latency_ms":percentiles([m["elapsed_ms"] for m in successes]),
        "all_attempt_latency_ms":percentiles([m["elapsed_ms"] for m in metrics]),
        "successful_sql_count":percentiles([m["sql_count"] for m in successes]),
        "successful_returned_rows":percentiles([m["returned_rows"] for m in successes]),
        "successful_sql_execute_ms":percentiles([m["sql_execute_ms"] for m in successes]),
        "ledger_hold_ms":percentiles([m["ledger_hold_ms"] for m in successes if "ledger_hold_ms" in m]),
        "phases_ms":{phase:percentiles([m.get("phases_ms", {}).get(phase, 0) for m in successes])
            for phase in ("authorize","lock_read","apply","write","commit","response_read","render")},
        "scenarios":{scenario:dict(Counter(str(m["status"]) for m in metrics if m["scenario"] == scenario))
            for scenario in ("auto","manual","pending","combo")}}


def run_case(url, history, callers, samples, warmups, activate):
    # Four additional sequential probes collect byte counts OUTSIDE timed load.
    setup = setup_database(url, history, samples + warmups + 4, activate)
    admin, database, engine, auth_engine, token, bodies, digest = setup
    records = {}
    app = FastAPI()
    app.add_middleware(MetricsMiddleware, records=records)
    app.get("/v2/me")(api.me)
    live.install_live_tour_routes(app, engine_instance=lambda:engine,
        current_identity=api.current_identity, require_feature=api._require_feature,
        feature_allowed=api._feature_allowed, identity_type=api.Identity)
    # install_live_tour_routes wraps lifespan to start background workers. This
    # benchmark deliberately isolates checkout + auth, not a changing job queue.
    app.router.lifespan_context = isolated_lifespan
    try:
        with TestClient(app) as client:
            headers = {"Authorization":"Bearer " + token}
            assert client.get("/v2/me", headers=headers).status_code == 200
            def request(index, byte_probe=False):
                body = deepcopy(bodies[index])
                scenario = body.pop("scenario")
                identifier = str(index)
                metric = new_metric(byte_probe)
                metric["scenario"] = scenario
                records[identifier] = metric
                start = perf_counter()
                response = client.post("/v2/live-tour/action", json=body,
                    headers={**headers,"X-Benchmark-Id":identifier})
                metric.update(status=response.status_code, elapsed_ms=(perf_counter()-start)*1000)
                if response.status_code == 200:
                    invoice = response.json()["result"]["invoice"]
                    assert invoice["tip"] == 11
                    assert invoice["total"] == (11 if scenario == "combo" else 111)
                elif response.status_code not in (409, 503):
                    raise AssertionError(f"Unexpected synthetic checkout status {response.status_code}: {response.text}")
                return metric
            for index in range(warmups):
                assert request(index)["status"] == 200
            probes = [request(warmups + samples + n, True) for n in range(4)]
            assert all(m["status"] == 200 for m in probes)
            auth_results = []
            done = threading.Event()
            auth_ready = threading.Event()
            def auth_load():
                # Co-running real /v2/me, with its actual revocation/account checks.
                auth_ready.set()
                while not done.is_set():
                    start = perf_counter()
                    response = client.get("/v2/me", headers=headers)
                    auth_results.append({"status":response.status_code,"elapsed_ms":(perf_counter()-start)*1000})
                    done.wait(.01)
            auth_thread = threading.Thread(target=auth_load)
            auth_thread.start()
            auth_ready.wait()
            start = perf_counter()
            try:
                with ThreadPoolExecutor(max_workers=callers) as pool:
                    metrics = list(pool.map(request, range(warmups, warmups + samples)))
            finally:
                duration = perf_counter() - start
                done.set()
                auth_thread.join()
            result = summarize(metrics)
            result.update(history_invoices=history, history_voids=history//10, callers=callers,
                warmups=warmups, dataset_sha256=digest, elapsed_seconds=round(duration, 6),
                successful_checkouts_per_second=round(result["successes"]/duration, 3),
                attempts_per_second=round(samples/duration, 3),
                auth={"samples":len(auth_results),"status_counts":dict(Counter(str(m["status"]) for m in auth_results)),
                      "latency_ms":percentiles([m["elapsed_ms"] for m in auth_results])},
                byte_probes=[{key:m[key] for key in ("scenario","status","sql_count","returned_rows","decoded_result_bytes")}
                             for m in probes])
            with engine.connect() as conn:
                count, distinct = conn.execute(text("""SELECT COUNT(*),COUNT(DISTINCT payload->>'bill_no')
                    FROM vera_live_tour_invoice WHERE deleted_at IS NULL""")).one()
                expected = history + warmups + 4 + result["successes"]
                assert count == distinct == expected, (count, distinct, expected)
            # A committed response must replay without increasing the ledger.
            successful_index = next((index for index in range(warmups, warmups+samples)
                                     if records[str(index)]["status"] == 200), None)
            if successful_index is not None:
                body = deepcopy(bodies[successful_index]); body.pop("scenario")
                replay = client.post("/v2/live-tour/action", json=body, headers=headers)
                assert replay.status_code == 200 and replay.json()["duplicate"] is True
            # The measured auth route must also reject a session revoked in PostgreSQL.
            with auth_engine.begin() as conn:
                conn.execute(text("""UPDATE vera_app_setting SET value_json=value_json ||
                    jsonb_build_object('revoked_at',1) WHERE setting_key='benchmark-session'"""))
            assert client.get("/v2/me", headers=headers).status_code == 401
            result["checks"] = {"ledger_count":count,"unique_bill_numbers":True,"replay":True,"revoked_session_rejected":True}
            return result
    finally:
        engine.dispose(); auth_engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{database}"'))
        admin.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-disposable-local-postgres", action="store_true", required=True,
                        help="Acknowledge the DSN is a disposable local server, never production or a production tunnel")
    parser.add_argument("--history", type=int, nargs="+", default=[0,1000,10000])
    parser.add_argument("--callers", type=int, nargs="+", default=[1,4])
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--warmups", type=int, default=4)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--activate", help="Explicit candidate migration module:function")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("VERA_BENCH_POSTGRES_URL", "")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Only an explicitly configured localhost disposable PostgreSQL instance is allowed")
    if args.samples < 4 or args.warmups < 0 or any(h < 0 for h in args.history) or any(c < 1 or c > 16 for c in args.callers):
        raise SystemExit("Invalid benchmark workload bounds")
    os.environ["VERA_AUTH_PROVIDER"] = "postgres"
    live.datetime, live.ActionTiming = FixedDateTime, MeasuredTiming
    with create_engine(url).connect() as conn:
        postgres = conn.execute(text("SHOW server_version")).scalar_one()
    result = {"scope":"Synthetic in-process TestClient API + local PostgreSQL; no WAN/browser/production capacity claim",
        "measurement":"Latency excludes byte probes; returned rows include scalar reads and RETURNING; decoded bytes are compact JSON UTF-8, not wire bytes",
        "load":"Closed-loop callers; one attempt per unique payment; fail-fast 409/503 counted, no automatic retries",
        "git_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "python":sys.version,"executable":str(Path(sys.executable).resolve()),"postgres":postgres,"platform":platform.platform(),
        "harness_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "core_sources_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
            for name in ("vera_web_v2_live_tour.py","vera_live_tour_resource_store.py",
                         "vera_live_tour_bill_numbers.py","vera_live_tour_relational.py",
                         "vera_live_tour_receipts.py","vera_web_v2_api.py","vera_web_v2_local_auth.py")
            if (ROOT/name).is_file()},
        "cpu_count":os.cpu_count(),"cpu_quota":Path("/sys/fs/cgroup/cpu.max").read_text().strip() if Path("/sys/fs/cgroup/cpu.max").exists() else None,
        "dependencies":package_versions(),
        "activation":args.activate,"background_workers":"disabled by identical isolated ASGI lifespan","cases":[]}
    for repeat in range(args.repeat):
        for history in args.history:
            for callers in args.callers:
                case = run_case(url, history, callers, args.samples, args.warmups, args.activate)
                case["repeat"] = repeat + 1
                result["cases"].append(case)
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(result,indent=2)+"\n")
                print(json.dumps({"history":history,"callers":callers,"repeat":repeat+1,
                    "successes":case["successes"],"status_counts":case["status_counts"],
                    "successful_checkouts_per_second":case["successful_checkouts_per_second"],
                    "latency_ms":case["successful_latency_ms"],"ledger_hold_ms":case["ledger_hold_ms"]}),flush=True)


if __name__ == "__main__":
    main()
