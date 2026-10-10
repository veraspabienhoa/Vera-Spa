# Phase two: bounded reads and rendering

Base: `84605dd3e0352180448f347157081c202567db86` (phase one, PR #516).
This is a source change. It neither authorizes production deployment nor proves
production latency or browser responsiveness.

## Scope

- Live Tour list queries move filtering, counts and page selection into
  PostgreSQL when the resource store is authoritative and the query projection
  is ready. Filter-wide totals are computed before pagination.
- The standalone reports screen requests its selected tab, filters and one
  100-row page. Financial totals and employee aggregates cover the whole filter.
  Receipt lookup keeps canonical invoice IDs and revisions. Excel/PDF exports
  keep their existing full-filter routes rather than exporting the display page.
- Customer history reads use the stable customer ID to avoid transferring other
  customers' ledgers. The existing complete-history response is retained.
- Purchase and payroll history/draft tables use bounded display pages. Totals,
  financial edits, selection and exports retain their full filtered input.
- Payroll history filters no longer refetch stable configuration, refunds and
  obligations. The latest-draft fallback is requested only when the selected
  period has no saved draft.
- Quarter-hour upcoming-booking reminders stop routine reads in hidden tabs.
  On return, one check catches up across missed boundaries; slow reads do not
  overlap, stopped/account-switched callbacks cannot open a stale reminder.
  Visible checks remain aligned to quarter hours. Live Tour board polling is
  unchanged, including its three-second cadence and conditional revision reads.

## Query projection and rollout

`vera_live_tour_query` owns a versioned projection on the existing resource rows.
It uses the established Python normalization for Vietnamese text, phone numbers
and Vietnam calendar dates, avoiding a change to SQL locale/unaccent semantics.
Existing collection queries retain their previous normalization/date semantics.
The standalone reports contract also stores separately normalized fields matching
the original JavaScript filters: phrase-prefix search, underscore word breaks,
formatted Vietnamese phones and legacy D/M/YYYY dates. Cross-language golden
tests exercise the original JS selectors and money summaries against Python and
PostgreSQL, including orphan invoice metadata and invoice-view-only PII grants.
Resource writes update both projections in their existing transaction. Read paths
reuse the caller's connection and do not acquire business locks or run DDL.

The deployment schema gate installs/backfills the projection and its indexes.
The migration takes relation locks and runs within the existing deployment
transaction/timeouts; it should be rehearsed with representative synthetic data
before a large production backfill. A timed-out migration rolls back; do not
raise timeouts or change storage flags automatically to force it through.

The bounded path requires active resource mode, the committed resource-ready
marker, the projection schema version and matching row projection hashes. The
same MVCC statement checks projection validity and reads the selected rows,
revision and aggregates. Old writers invalidate the projection by changing the
canonical payload hash. If readiness/parity does not hold, the existing canonical
read path remains available. Shadow, verify and off modes are never implicitly
promoted. Old clients retain their response contract.

The phase-one deployment log observed active resource mode and successful parity
on 10-10-2026 at 14:39:38 UTC, revision 11837. This is a deployment-time observation,
not a guarantee of the current runtime or the new projection's readiness:
https://github.com/veraspabienhoa/Vera-Spa/actions/runs/38060412553

Deploy the matching frontend/backend through the normal operator-controlled
workflow. This repository can publish the frontend before the operator deploys
the backend, so a one-release compatibility adapter accepts only the exact
seven-key legacy report response. It retains that account/permission-scoped
snapshot for local filters and pages, computing full-filter totals with the
existing browser helpers. It never reinterprets malformed bounded responses or
HTTP failures as legacy success. Explicit refresh and committed edits invalidate
the legacy snapshot before reading, so a failed read cannot revive stale money.
The next successful server refresh discovers the new bounded contract. Until
then, an old backend still transfers and retains complete report history; this
is compatibility, not a bounded-network performance claim. Rollback preserves
canonical resources; readiness failure falls back without promoting a shadow copy
or dropping history.

After all API and projection workers run the new release, the operator can run
`python vera_live_tour_query.py` to verify projection readiness without logging
financial payloads. If older workers wrote after migration, the read path falls
back safely until `python vera_live_tour_query.py --repair` repairs stale rows.
This explicit repair uses 250-row batches, a bounded batch count, hash
compare-and-swap and the caller's transaction; concurrent canonical changes
cannot be overwritten. It updates projection fields only, with local lock and
statement timeouts. A failure rolls back rather than leaving a partial published
repair. Rerunning the deployment schema gate also repairs stale projections.
Neither command changes resource mode or business values.

## Remaining limits

- Purchase and payroll APIs still return their existing complete filtered data.
  This phase bounds their rendering and redundant requests, not those payloads.
- Purchase PNG export intentionally renders the complete filtered capture only
  for the explicit export. Very large PNG captures can still be expensive.
- Service-time performance reports still build their combined live/pending/paid
  data on the canonical fallback path before returning a bounded display page.
  Moving that derived/deduplicated view to SQL is deferred.
- Customer history retains complete history for one selected customer; it is not
  a new paginated UI. Board-history transport and full-filter export work remain
  proportional to their result size.
- Payroll desktop/mobile representations are each bounded to a page; this is
  not a claim that only one responsive representation is mounted.
- Employee revenue summaries/charts retain one aggregate per matching employee;
  the report no longer needs all underlying history rows for those aggregates.
- Permission-scoped SSE/WebSocket delivery, cross-tab leaders, financial locks
  and invoice numbering are outside this change. No production load test or
  broad idle-request reduction claim is made.

## Acceptance

Run all Node regressions, lint/build and the complete Python suite, including
isolated PostgreSQL integration tests. Use synthetic financial/customer data.
Check page-boundary/filter parity, Vietnam midnight, void/deleted rows, missing
fields, grants, linked receipt revisions, full-filter totals and exports,
projection staleness/rollback and fallback, late responses, account changes,
and page-spanning edits/selections.

After authorized deployment verify the exact frontend/backend commit,
`/v2/auth/health`, `/v2/health`, query schema readiness and representative report,
customer-history, purchase and payroll operations. Compare filtered totals and
exports with a known sample. Production p50/p95, pool/lock waits, browser DOM
cost and cross-client freshness need separate measurements on that deployment;
local synthetic tests cannot establish them.

### Read contract and export parity

`GET /v2/live-tour/reports?tab=...` opts into the bounded contract: `rows`,
page-linked authorized `invoices`, `page`, `page_size`, `total`, `pages`,
filter-wide `summary` and `employee_totals`, plus the existing revision,
capabilities and payment settings. Default page size is 50; maximum is 100.
Omitting `tab` preserves the older complete response. Report pages retain source
order `(ordinal, resource_id)`; existing collection pages retain newest-page,
ascending-within-page order. Counts and linked receipts share one MVCC snapshot.
Exact totals still require work proportional to the matched rows inside PostgreSQL;
this is bounded transfer/rendering, not constant-time aggregation.

Report/employee/TIP Excel and customer-count PDF use the same complete date,
single-date, search and money filters as the screen. Full invoice sibling groups
remain available to allocate export discounts correctly. Customer filtering runs
after the same PII visibility checks, and service-time export requires Admin as
the screen does. PDF daily buckets use the same Vietnam/legacy date resolver.
Explicit full exports remain proportional to the selected export data; they do
not export only the current UI page or discard earlier financial history.

## Final local verification (10-10-2026)

- Complete Python suite: **3,165 passed**, with real isolated PostgreSQL 16
  integration tests enabled; six existing SQLite/Python deprecation warnings.
- Complete Node suite: **617 passed**, zero failures or skipped tests.
- Frontend lint: zero errors; one existing `AppearanceSettingsPage.jsx` hook
  dependency warning. Production build passed.
- Independent review: final query/privacy/JavaScript-oracle/repair suite
  **133 passed**, final mounted compatibility/paging/transport suite **36 passed**.
  A separate interleaved hash-CAS repair test preserved the concurrent writer's
  canonical values, hashes and revisions and projected its latest value.
- `git diff --check` passed. Data and concurrent-write experiments were synthetic;
  these results do not establish production latency or deployment success.

The full Python command was `python scripts/run_pytest_offline.py -q` with
`VERA_TEST_POSTGRES_URL` targeting a disposable `vera_test` database. Node used
`node --test tests/*.test.mjs` from `web-v2`, followed by `npm run lint` and
`npm run build`. Remote CI must also pass for the exact published commit.
