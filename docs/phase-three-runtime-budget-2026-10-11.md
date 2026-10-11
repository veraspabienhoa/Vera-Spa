# Phase three: database runtime budget and observations (11-10-2026)

## Scope and verified limits

Source changes only. Production machine, process/replica count, PostgreSQL role
settings, proxy limits, CPU/RAM, service flags and workload are unverified. This
change does not deploy, restart, alter PostgreSQL roles, set OS/service options,
raise connection defaults or write production data. A source guardrail is not a
host-capacity estimate, and no production throughput multiplier is claimed.

Retain the separate authentication reserve, authoritative session/account checks,
caller-owned transactions, Live Tour locks, outbox delivery after commit and
existing notification/financial rules. The historical incident record is unchanged.

## Existing defaults retained

- Each Web V2 business engine: 2 connections, 0 overflow, 30-second acquisition
  timeout (previously SQLAlchemy's implicit default, now explicit).
- Separate auth engine: 2 connections, 0 overflow, 5-second acquisition timeout;
  fixed 10-second statement, 3-second lock and 15-second idle-transaction deadlines.
  Existing auth size (1–4) and acquisition timeout (1–60 seconds) clamps remain.
- Each legacy `vera_postgres` engine: 8 connections, 12 overflow and 20-second
  acquisition timeout. It remains distinct from the Web V2 business/auth engines.
- Connection establishment: 10 seconds; recycling: 3,600 seconds. TLS enforcement
  and the legacy Cloud SQL socket exception remain as before.
- Business/background SQL deadlines inherit PostgreSQL/database/role settings by
  default. There is no claim that those settings are currently nonzero or adequate.

API and legacy engine first initialization is now serialized. Previously,
concurrent first callers could create separate pools despite the singleton/cache
intent. A legacy schema-initialization failure now disposes its unreturned pool.

## Validated controls

`vera_database_runtime.py` is the shared configuration boundary. Invalid values
fail before creating pools, with setting names only in error messages. These
ceilings are implementation guardrails, never recommended production values.

- `DB_POOL_SIZE`: 1–64; zero (an unbounded SQLAlchemy pool) is rejected.
- `DB_MAX_OVERFLOW`: 0–64; unlimited overflow `-1` is rejected.
- `DB_BACKGROUND_POOL_SIZE`, `DB_BACKGROUND_MAX_OVERFLOW`: the same bounds;
  optional legacy-only overrides. Without them, the existing `DB_POOL_SIZE` /
  `DB_MAX_OVERFLOW` fallback still applies before the legacy 8/12 defaults.
- `DB_POOL_TIMEOUT`: 1–120 seconds, configurable for API and legacy business pools.
- `DB_CONNECT_TIMEOUT`: 3–120 seconds; `DB_POOL_RECYCLE`: 3,600–86,400 seconds.
- Optional `DB_STATEMENT_TIMEOUT_MS`: 1–900,000;
  `DB_LOCK_TIMEOUT_MS`: 1–60,000;
  `DB_IDLE_IN_TRANSACTION_TIMEOUT_MS`: 1–900,000. All are integer milliseconds;
  zero/infinite is rejected. If both statement and lock limits are provided,
  lock must not exceed statement. They do not replace fixed auth deadlines.

SQL overrides are applied only when explicitly configured, using connection
options. An override can replace a stricter server policy: inspect actual role
and per-connection settings before choosing it. Statement deadlines apply per
statement, not to a complete report, transaction or HTTP request. Pool acquisition
also includes connection establishment/pre-ping; these are separate budgets and
must fit the operator's request/proxy deadlines. Do not shorten a financial write
blindly or add automatic mutation retries after an ambiguous result.

The private managed runtime allowlist accepts these controls. DB/Auth managed
values remain authoritative. `VERA_SERVICE_ROLE` supports `combined`, `api`,
`worker`; an explicit process role takes precedence over the shared managed file
so a dedicated worker cannot accidentally start API/combined behavior. Invalid
roles still fail closed. Changes require the normal authorized service lifecycle;
this module never modifies environment files itself.

## Explicit fleet connection budget

All five declarations are required together, or none. No declarations means
`status=undeclared`, which preserves compatibility and explicitly means capacity
has not been established. A partial or exceeded budget fails startup/pool creation.

- `DB_CONNECTION_BUDGET`: approved total connection envelope, 1–100,000.
- `DB_API_POOL_INSTANCES`: count of Web V2 business/auth engine pairs, 0–1,024.
- `DB_BACKGROUND_POOL_INSTANCES`: count of separate legacy/background engines,
  0–1,024.
- `DB_DEDICATED_CONNECTIONS`: total maximum for dedicated/leadership connections,
  0–100,000, including any future singleton connection outside these pools.
- `DB_EXTERNAL_CONNECTION_RESERVE`: explicit allowance for other applications,
  migrations, diagnostics, cron/device jobs and operational headroom, 0–100,000.

The check is:

`API instances × (business size + overflow + auth size) + background instances ×
(background size + overflow) + dedicated + external reserve <= connection budget`.

At least one pool instance must be declared. Opening an engine whose pool type
has a declared count of zero fails closed. Count every process, replica and
rolling-restart overlap, including worker-only processes using the Web V2 engine.
Their auth reserve is conservatively counted even if never opened. A process that
also imports/opens a legacy engine counts in both categories. The new service-role
worker uses existing pooled transactions and adds no dedicated leadership
connection; existing external jobs may still have dedicated connections.

Declarations describe maximum simultaneous engine instances, not CPU cores or
HTTP threads. They are operator-supplied assertions, not discovery. Heterogeneous
process settings must use a conservative common maximum or be represented in the
external reserve. A per-process budget cannot enforce a fleet-wide semaphore.

Synthetic example only: 3 API-pair instances at 2+0+2, 2 legacy instances at
8+12, 1 dedicated connection and 10 external/reserved connections require 63.
A declared budget of 63 passes; 62 fails. This is not a production topology or
recommended allocation. More connections can reduce throughput if PostgreSQL,
CPU, locks or upstream dependencies are already saturated.

## Sanitized observations and readiness

All shared pools emit fixed-label, numeric process-local acquisition/occupancy
observations at most once per minute when acquisitions occur. The public
`ObservedQueuePool.connect()` wrapper preserves SQLAlchemy behavior and observes
successful acquisition, pool timeout and establishment/pre-ping errors. There are
no event-per-request retained records, URLs, SQL, parameters, tokens or identities.
Counters reset on pool recreation/process restart, and are not fleet aggregates.

`VERA_POOL_METRICS` reports configured size/overflow limit, checked-in/out,
current overflow, in-progress acquisitions, completed acquisitions, timeouts,
errors, total/max acquisition milliseconds and ten noncumulative buckets. Bucket
upper bounds in ms are 1, 5, 10, 50, 100, 500, 1,000, 5,000, 30,000 and infinity.
Acquisition includes connecting/pre-ping; it is not pure queue wait, query runtime
or transaction-hold duration. SQL/request durations remain in existing request
metrics. The diagnostics log parser exports only fixed pools and numeric fields.

`/v2/health` still opens the business pool and checks storage-mode agreement. It
also reports the current pool snapshot, declared-budget status and three numeric
actual connection SQL deadlines in milliseconds. A zero is an inherited disabled
deadline, not a false claim of protection. Database/configuration failures yield a
sanitized 503. Auth health and real authenticated business reads must still be
checked separately; capacity declarations do not assert production readiness.
Separate database pools do not reserve ASGI/AnyIO request-thread tokens, CPU or
HTTP admission capacity. Slow synchronous business requests can still exhaust
shared request threads. The pool-isolation tests and low-concurrency synthetic
auth probes do not establish end-to-end login availability under arbitrary load.

Read-only runtime diagnostics add PostgreSQL's max/reserved connections, current
role connection limit, numeric client/role connection counts and allowlisted
explicit database/role deadline overrides. Their own 3-second statement/1-second
lock limits remain separate. Absence of an explicit role override does not mean
the application's effective setting is known. PostgreSQL configuration files,
URL options and proxies can supply other policy. The diagnostic process may see
only its selected managed/initial process environment; corroborate it with live
health and actual service configuration. Fixed application tags distinguish
business/auth/background sessions without exposing host or account names.

## Rollout and rollback gates

1. Run focused regressions with an isolated local PostgreSQL database and outbound
   HTTP/DNS blocked. Preserve attendance connection reuse, auth exhaustion
   isolation, notification outbox and runtime-sanitization checks in CI.
2. Before any separately authorized production change, capture bounded sanitized
   diagnostics and inventory the actual API, combined/worker, cron, legacy,
   dedicated, replica and rolling-overlap counts. Inspect RAM/CPU, PostgreSQL and
   proxy connection limits, role limits and request deadlines. Do not infer them
   from historical incident values or this document's defaults.
3. Review existing numeric environment values against the new guardrails before
   deployment; previously unbounded/out-of-range values now fail closed. Keep
   defaults unless measured evidence supports a specific alternative. Choose an
   envelope below usable server/proxy/role capacity and reserve operational space;
   the smallest applicable limit wins. Configure the five declarations together.
4. Verify exact deployed commit, both health endpoints, actual effective SQL
   deadlines, authenticated profile/session revocation, schedule and Live Tour
   reads plus representative authorized business operations. Confirm worker
   heartbeat/readiness separately when explicit service roles are adopted.
5. Measure a representative read/write/report mix: p50/p95/p99 latency, acquisition
   timeouts, occupancy, request/SQL times, active transactions and lock waits,
   PostgreSQL/host resource pressure and errors. Measure through process/replica
   changes and report workload and test environment alongside results.
6. If budgets/settings cause admission failures or measured regression, stop the
   rollout and restore the prior reviewed environment/source through the existing
   release procedure. Pool observations have no migration or persistent data to
   roll back. Restore specific optional deadlines rather than relaxing all
   safeguards; never weaken auth, locks or financial idempotency to regain green
   health.

## Local verification

130 focused tests pass on isolated real PostgreSQL: configuration bounds, budget arithmetic,
concurrent engine initialization, SQL statement/lock cancellation and rollback
reuse, auth reserve under business saturation, sanitized capacity queries/logs,
managed-role precedence, attendance connection reuse and outbox regressions.
No production endpoints or external devices are contacted. Final aggregate CI and
production measurements remain separate gates owned by the integrating change.
