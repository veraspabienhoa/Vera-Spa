# Quảng Ngãi — independent revenue workspace

Duplicated the existing Revenue and embedded Purchase screens, retaining entry,
editing/deletion, date and column filters, pagination, append/replace workbook
imports, Excel exports, purchase reconciliation, audit and duplicate analysis.
The title/menu is Quảng Ngãi. Both admin and giamdoc have full access. Other
roles are rejected by the page and every API route, even with revenue grants.

All requests use /v2/quang-ngai. Cash rows/audit and purchase rows/audit/imported
sources/idempotency records use dedicated vera_quang_ngai_* tables. Initial
ledgers are empty; there is no bootstrap/copy from existing financial data and no
Google or Live Tour fallback. TIP and mode switching are absent; remaining cash
is income minus expenses. Purchase reporting is reconciled with manually entered
purchase expenses, as in the original Manual ledger, without double counting.
The original Revenue screen, modes and records are unchanged.

The existing versioned deploy schema gate creates the new tables. RLS and table
grant revocation prevent direct public/anon/authenticated access. API mutations
use the caller transaction; edits/deletions retain audits. Cash imports and
mutations use a separate transaction lock. Purchase retries use their separate
request ledger. Polling and refresh read only the new ledger revision.

Local verification: six rendered frontend tests, 23 Python permission/reliability
tests, lint and production build. Real PostgreSQL tests cover both allowed roles,
CRUD, duplicate confirmation, retry deduplication, reconcile, export, append and
replace imports, rollback of invalid import and original-ledger preservation.
These require VERA_TEST_POSTGRES_URL in CI. Production is not deployed/verified.
