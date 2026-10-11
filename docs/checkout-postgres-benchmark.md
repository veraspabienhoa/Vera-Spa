# Checkout PostgreSQL benchmark

This is an offline synthetic benchmark, not a production/VPS capacity estimate.
It exercises the actual `/v2/live-tour/action` route, PostgreSQL row storage,
resource/ledger advisory locks, publication revision, receipt writes and commits.
Each request uses the actual PostgreSQL session verifier and normal Admin grants.
A concurrent caller exercises the actual `/v2/me` route through a separate pool.
The harness does not patch authentication results or replace database writes.
After installing the routes, it replaces the ASGI lifespan with an inert context
identically for both versions. Projection/scheduler/queue workers therefore do not
mutate the fixture or consume pools during the measured checkout-plus-auth load.
This experiment does not measure background-worker contention or lifecycle.

## Safe, repeatable execution

Use an unprivileged account and installed PostgreSQL binaries. The wrapper creates
a fresh temporary cluster bound to `127.0.0.1`, creates randomly named benchmark
databases, then stops and removes its own cluster. It does not deploy anything.
Never provide a production DSN or a local tunnel to production. The Python runner
requires explicit acknowledgement of a disposable local server and rejects a
non-loopback hostname. External HTTP, DNS and socket connections are blocked
before application imports, including requests routed through an HTTP proxy.

```bash
PG_BIN=/path/to/postgresql/bin PYTHON=/path/to/venv/bin/python \
  scripts/run_checkout_postgres_benchmark.sh \
  --allow-disposable-local-postgres --history 0 1000 10000 --callers 1 4 \
  --samples 40 --repeat 2 --output /tmp/checkout-baseline.json
```

Run the same harness file, interpreter, package environment, PostgreSQL settings,
host and workload arguments at the baseline and candidate revisions. For an
allocator-enabled candidate, append:

```text
--activate vera_live_tour_bill_numbers:activate
```

The candidate migration runs explicitly after synthetic fixture seeding and before
any timed request. Resource storage and indexed receipt storage are activated for
both versions. The candidate alone activates its new numbering registry. Initial
application-state SHA-256 fingerprints must match for each workload size. Results
also record Git revision, core source hashes, harness hash, interpreter, package
versions, OS, CPU count and PostgreSQL version. Preserve both JSON output files.
For development in a pre-started local disposable cluster, set
`VERA_BENCH_POSTGRES_URL` and invoke the Python script with the same arguments.

Run versions serially, avoid other tests/builds during measurement, and alternate
baseline/candidate ordering for repeated experiments. Shared-machine contention,
OS page cache and checkpoint variation remain possible. Repeat before interpreting
a change, and disclose that host resources are not dedicated when applicable.

## Dataset and load

- Historical paid invoices: 0, 1,000 or 10,000, each with one report and durable
  receipt. Voided-number history is 10% of paid history. Audit history is capped
  at 2,000 rows. Historical invoice detail contains synthetic text only.
- The active fixture size is `samples + warmups + 4` employees/customers, with one
  pending invoice per four operations. It stays fixed across historical sizes.
- Four scenarios rotate equally: auto-number cash, manual-number cash, pending
  cash and combo redemption. Each operation uses a distinct employee/customer.
  The money checks require 111 for cash and 11 collected TIP for prepaid combo.
- Four warmups are excluded. Four sequential byte probes run before the timed
  load and are excluded from latency/throughput. They exercise all four scenarios.
- One or four closed-loop callers submit one attempt per unique payment. They do
  not automatically retry financial mutations. Expected fail-fast 409/503 results
  are counted separately. Successful throughput uses only committed HTTP 200s
  divided by the entire timed load interval, including failed attempts.
- A separate thread requests `/v2/me`, pausing 10 ms after each response, while
  checkouts run. The business pool is bounded at 4 connections; auth at 2, both
  with zero overflow. This local non-TLS fixture is not a production pool/SSL test.

The runner verifies the exact invoice count and unique bill numbers, replays one
successful payment through the same route, and revokes the fixture session in
PostgreSQL before asserting `/v2/me` rejects it with 401. Existing regression
suites remain necessary for rollback, permissions, stale writes and financial
edge cases; this harness is not a replacement for those tests.

## Metric definitions and limits

- Successful latency: in-process TestClient request wall clock, including real
  session verification, route execution, transaction commit and response encoding.
  It excludes a real web server, TLS/WAN, browser rendering and UI interaction.
- SQL count: actual DBAPI execute calls in each request, including authentication.
  SQL execution time ends when the driver returns, before Python fetch/decode work.
- Returned rows: actual driver `rowcount` for row-returning statements, including
  scalars and `RETURNING`. This is not PostgreSQL rows examined or buffer reads.
- Decoded result bytes: UTF-8 length of compact JSON representations of fetched
  result rows/columns, measured only in the separate probes. It is not wire bytes,
  PostgreSQL storage size or Python heap usage. Serialization instrumentation is
  excluded from timing runs to avoid inflating the old history-heavy path.
- Ledger hold: successful acquisition of the ledger advisory lock through return
  from the same transaction's actual commit. The timestamp begins immediately
  after fetching the successful acquisition result. It includes the critical
  read/apply/write/commit period, but not prior discovery or authorization work.
- Pure PostgreSQL lock-wait/wait-event duration is **not measured**. Ledger hold
  is not lock wait. The nonblocking ledger acquisition can return HTTP 503; the
  combined lock/read phase and aggregate SQL time cannot isolate server waits.
- Phase timings: the actual route's `ActionTiming` marks: authorize, lock/read,
  apply, write, commit, response read and render. SQL and phase intervals overlap;
  do not sum them with each other.
- p50 is the median; p95 is nearest-rank `ceil(0.95*n)`. Every aggregate includes
  its sample count. Four-caller success tails can have few samples because ledger
  contention intentionally fails fast. Do not treat a small-sample p95 as stable.

The invoice ledger lock remains deliberate. More simultaneous payment attempts
can raise conflict counts rather than multiply successful throughput. Neither
successful auth probes nor this checkout workload establishes all-page health or
any production concurrency target.
