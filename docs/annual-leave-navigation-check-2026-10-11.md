# Annual-leave notification navigation and overlap check

Source change based on main `726bbc27`. No production requests, approval,
notification acknowledgements or financial/leave records were changed during
investigation.

## Reproduced cause

The per-request **Kiểm tra** route compared Phase-14 `date_from` / `date_to`
TEXT columns directly with PostgreSQL DATE parameters. Using the real
`vera_postgres_phase14._ensure_schema` reproduces `operator does not exist:
text <= date`. The older regression used DATE columns and therefore passed
without exercising the canonical schema.

The read-only route now filters candidates using non-throwing ISO text sort
keys, then validates calendar dates with the existing canonical parser. It
supports day-first slash/dash dates, ISO dates, the existing unambiguous US
slash fallback, empty metadata with payload dates, and actual DATE columns.
Malformed rows cannot crash the check. Trimming matches Python's whitespace
handling. No migration or change to stored dates is required.

The endpoint retains its response shape, Admin requirement, date-span bound,
active employee filtering, request-status filtering, deduplication and
return-to-work clipping. Both reads share one repeatable-read, explicitly
read-only transaction. It does not run synchronization, approval, entitlement,
attendance, penalty or notification writers.

## Browser behavior

Only notifications with the existing `long_leave_requests` payload category
open the existing Phép năm page, subject to its current menu permissions and
navigation guard. Other categories retain their destinations and detail flows.
The system-wide notification modal remains in use. Rapid activation does not
create duplicate actions; failed acknowledgements retain their existing
unread/retry semantics.

The Admin panel ties in-flight reads to the current account and latest request.
Switching accounts, losing the Admin role, navigating away or refreshing
cancels obsolete reads and prevents late responses from populating another
account's page. A synchronous guard prevents double-click overlap requests.
A cancelled/stale check never approves or rejects a request.

## Verification and rollout

Regressions exercise real Phase-14 TEXT schema and legacy DATE schemas,
month/year/leap boundaries, malformed rows and target dates, permission denial
before database reads, read-only SQL, concurrent checks and unchanged records.
Rendered browser tests cover direct notification navigation, category and
permission isolation, dismissal/read behavior, repeated clicks and account
switches, plus checking/retrying without decisions.

The backend change is compatible with the existing frontend response contract;
new frontend navigation uses the existing notification payload category and
page. A new frontend against an old backend still reports a genuine server
failure rather than treating an unsuccessful overlap check as success.

This source change does not establish deployment or the affected operation on
the actual production runtime. Merge/deploy requires the user's authorization.
Phase-three activation remains paused.
