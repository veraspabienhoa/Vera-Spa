# Checkout throughput measurements, 11-10-2026

Offline synthetic PostgreSQL/API measurements. No production load, deployment,
financial data or live external services were involved. See the
[methodology and runner](checkout-postgres-benchmark.md) for exact definitions.

## Result

At 10,000 historical invoices, single-caller checkout p50 decreased from
422.3–425.9 ms to 25.9–26.6 ms across two runs.
The returned read set stayed bounded after explicit numbering-registry activation.
At zero history, latency was essentially unchanged. This does not establish a
50× system-wide improvement or production concurrency capacity.

Each range below is the minimum–maximum of two independent run statistics, not
a pooled percentile. Each single-caller run completed all 40 requests.

| Historical invoices | Version | Latency p50 / p95 (ms) | Ledger hold p50 / p95 (ms) | Successful checkouts/s |
|---:|---|---:|---:|---:|
| 0 | Baseline | 23.9–24.4 / 25.7–28.5 | 15.3–15.8 / 17.0–17.9 | 40.019–41.561 |
| 0 | Activated candidate | 24.2–24.7 / 31.5–31.8 | 15.6–16.5 / 19.1–20.1 | 39.045–39.308 |
| 1,000 | Baseline | 45.5–47.6 / 55.5–60.0 | 35.4–36.4 / 40.7–45.2 | 18.344–19.245 |
| 1,000 | Activated candidate | 25.0–26.6 / 28.0–36.6 | 16.3–16.9 / 18.2–22.0 | 35.896–39.654 |
| 10,000 | Baseline | 422.3–425.9 / 467.4–473.9 | 403.9–406.7 / 445.3–453.2 | 2.339–2.345 |
| 10,000 | Activated candidate | 25.9–26.6 / 32.4–36.1 | 16.9–17.2 / 20.6–21.6 | 36.208–37.283 |

## Queries and returned data

Median query count increased from 26 to 29 per successful mixed payment. The
improvement comes from less returned history data and shorter processing under
the existing ledger lock, not from fewer SQL statements.

Auto-number probe values below were identical across the paired repeats. Byte
probes run separately and are excluded from timing/throughput. Bytes are compact
JSON UTF-8 representations of decoded result rows, not network or storage bytes.

| Historical invoices | Baseline queries / rows / bytes | Candidate queries / rows / bytes |
|---:|---:|---:|
| 0 | 25 / 329 / 116,520 | 28 / 327 / 116,087 |
| 1,000 | 25 / 1,429 / 226,477 | 28 / 327 / 116,105 |
| 10,000 | 25 / 11,329 / 1,249,789 | 28 / 327 / 116,111 |

## Four simultaneous callers

Each run submitted 40 unique payments once, without automatic retries. The ledger
lock remains nonblocking and serialized; higher concurrency still produces many
HTTP 503 conflicts. Throughput below counts only HTTP 200 commits over the entire
timed interval, including failed attempts. No measured request returned HTTP 409
or an unexpected error. The old 10k runs have only one successful sample each, so
no tail-latency conclusion is drawn from their p95.

| Historical invoices | Version | Successful / 503 attempts, run 1; run 2 | Successful checkouts/s |
|---:|---|---|---:|
| 0 | Baseline | 7 / 33; 7 / 33 | 13.375–13.698 |
| 0 | Activated candidate | 7 / 33; 8 / 32 | 13.787–14.950 |
| 1,000 | Baseline | 4 / 36; 3 / 37 | 6.108–6.120 |
| 1,000 | Activated candidate | 8 / 32; 7 / 33 | 14.528–15.317 |
| 10,000 | Baseline | 1 / 39; 1 / 39 | 1.140–1.202 |
| 10,000 | Activated candidate | 7 / 33; 8 / 32 | 12.663–15.513 |

## Authentication and validation

`/v2/me` used the actual PostgreSQL session/revocation/account-lock checks on a
separate bounded auth pool while payments ran. All timed auth requests returned
200. After each case, the fixture session was revoked in PostgreSQL and `/v2/me`
correctly returned 401.

For the 10k single-caller checkout load:

| Version | Auth samples, run 1; run 2 | Auth p50 / p95 (ms) |
|---|---|---:|
| Baseline | 256; 255 | 6.1 / 291.7–297.7 |
| Activated candidate | 54; 55 | 8.2–8.5 / 13.4–14.9 |

All four byte-probe scenarios and warmups succeeded: automatic number, manual
number, pending payment and combo redemption. Cash totals were 111 and prepaid
combo TIP collection was 11. Every case verified the expected committed invoice
count and unique bill numbers, a duplicate receipt replay, and revoked-session
rejection. Per-scenario success/error counts, phase p50/p95, SQL timings and sample
counts are preserved in the raw files.

## Reproduction identity and limits

- Baseline business code: `762600ac6395477ad3d6d63e9754a4ff9e1e3cb9`.
- Baseline checkout including harness-only commits: `9c0260f48a42b9b911404b6da3569d0a342d85d8`.
- Candidate code: `e880562d53decf380e0ee0b94860d2ac1696fe63`.
- Identical harness SHA-256: `2fec4f17d26ef67e25a79c9c62ef60dba38953b0ce2341202efdb1247a1b363f`.
- Interpreter: Python 3.12.14, `/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3.12`; PostgreSQL 16.2.
- Same execution host/platform: `Linux-6.18.44-x86_64-with-glibc2.41`, 9 visible CPUs.
- CPU quota was unavailable; this was not dedicated production hardware.
- Packages: fastapi 0.143.0, starlette 1.7.0, httpx 0.28.1, httpx2 2.13.1, SQLAlchemy 2.1.4, psycopg 3.3.6.
- Run order: baseline A → candidate A → candidate B → baseline B. Other task
  tests/builds were paused during each measurement. An earlier contended pilot
  was discarded and is not included. OS/shared-host variation remains possible.
- Workload: 40 timed payments, 4 warmups, 4 byte probes, 48 synthetic active
  employees/customers, 1 or 4 callers. Historical data fingerprints match across
  every paired case; exact fingerprints and core-source hashes are in the JSON.
- Resource and receipt-row storage were active in both versions. Only the
  candidate explicitly called `vera_live_tour_bill_numbers.activate(conn)`.
  These results do not characterize legacy aggregate or inline-receipt storage.
- Background projection/scheduler/queue workers were disabled via an identical
  inert ASGI lifespan. This measures isolated checkout plus auth, not worker
  isolation gains or a full mixed page/worker workload.
- In-process TestClient excludes a real web server, TLS/WAN, browser/DOM and
  device latency. Bounded local non-TLS pools were business=4 and auth=2.
- Pure PostgreSQL lock-wait/wait-event duration is unmeasured. Ledger hold,
  combined lock/read phase, aggregate SQL execution and 503 conflicts are distinct
  measurements. Returned rows are not rows examined or PostgreSQL buffer reads.
- No statistical confidence interval or stable capacity limit is asserted.

Raw sanitized outputs (candidate repeats are split into separate files with
unchanged case values):

- [Baseline A](benchmarks/checkout-phase3-baseline-a.json)
- [Candidate A](benchmarks/checkout-phase3-candidate-a.json)
- [Candidate B](benchmarks/checkout-phase3-candidate-b.json)
- [Baseline B](benchmarks/checkout-phase3-baseline-b.json)

Rerun each baseline with `--history 0 1000 10000 --callers 1 4 --samples 40
--repeat 1`, using the disposable PostgreSQL wrapper and explicit acknowledgement.
Run the candidate with the same arguments and `--repeat 2 --activate
vera_live_tour_bill_numbers:activate`. The reusable runner documentation contains
the complete environment/command setup.
