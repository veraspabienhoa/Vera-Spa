# Live Tour resource storage and bounded UI reads

The board now requests `GET /v2/live-tour?view=board`. Action responses opt into
`response_view: board`; older API clients retain the full response default.
Customer, invoice, report and history data load on demand through
`/v2/live-tour/collections/{panel}` with server-side filters and bounded pages
(default 50, maximum 100 per history group). Report totals cover every matching
record, not only the visible page. Pending drafts remain on the board because
room/payment operations need them. API permissions apply before filtering/counting.

Combo reservation totals are indexed once per response by customer/purchase.
The table, memoized employee rows and six panels are separate components. Panel
callbacks stay stable across clock ticks; detail filters are memoized. Layout
identity application processes inserted/changed subtrees and ignores timer text;
editable-target discovery runs only while the designer is enabled.

## Resource transactions

`VERA_LIVE_TOUR_RELATIONAL_MODE=active` makes normalized resource rows authoritative.
It is **not** safe to set this flag before the offline cutover below. The default
shadow mode is unchanged; API/UI improvements work before cutover, while row-level
writes become active only afterwards.

Booking, employee edits, pending and paid invoice operations use sorted,
non-waiting advisory locks for employee, physical room, customer, invoice and
idempotency resources. A shared maintenance fence allows unrelated work. Invoice
numbering and corrections retain a short ledger invariant lock. Start and start-room now use scoped resource locks too. Reorder, restore,
configuration and projection retain an exclusive fence because they can change
global ordering/roster. Contention returns 503 with Retry-After; stale
resources return 409. Idempotent retries return the committed result.

Transactions read one consistent resource snapshot, validate their locked read
set, and write changed rows only. Publication revision allocation briefly locks
the metadata row at commit, so clients cannot miss a late commit. Independent
client revisions are accepted only when their locked resources and configuration
have not changed. Responses reread canonical state after the commit, outside the
previous transaction. No nested pooled connection is acquired.

## Explicit offline activation

Do this only in an approved maintenance window, first rehearsed against a restored
test database. This PR does not deploy, restart, or activate production storage.

1. Retain a verified database backup and the prior release.
2. Stop **all** API, projection and other Live Tour writers. Do not run mixed old
   aggregate writers with active resource writers.
3. With the new release installed and runtime DB configuration available, run
   `python vera_live_tour_cutover.py --writers-stopped`.
   It locks both storage paths, verifies parity, assigns stable IDs to legacy
   rows lacking IDs, and commits the ready marker atomically. Failure rolls back.
4. Set `VERA_LIVE_TOUR_RELATIONAL_MODE=active` for every API/projection process.
   Start the same release everywhere. Run schema verification, both auth/business
   health checks, and booking → completion → payment → idempotent retry checks.
   Verify pending, customer combo balances, reports and payroll tip reads.
5. Monitor latency p50/p95, 409/503 rates, pool occupancy and ledger parity.

Rollback also requires stopping all writers. Run
`python vera_live_tour_cutover.py --writers-stopped --rollback` while resource
storage is still available. This exports **current resource rows** back to the
legacy aggregate and removes readiness. Only then switch all processes to shadow
mode and start the prior-compatible release. Merely toggling the flag would read
stale financial data and is not a valid rollback.

## Verification and remaining limits

Run `python scripts/run_pytest_offline.py -q`; external sockets are blocked and
loopback PostgreSQL remains available. CI provisions PostgreSQL 16 and sets
`VERA_TEST_POSTGRES_URL` for concurrent-transaction, room conflict, stale revision,
rollback and checkout retry tests. Without that variable these tests skip, so a
local green unit suite alone does not certify PostgreSQL transactions.

The browser tests cover delayed/stale detail requests, pagination, booking/combo
flows and incremental DOM observation. The board payload test verifies a smaller
response with the same visible rows and permissions.

No 30x speedup is claimed: production measurements have not been taken. Actions
still load a resource snapshot and collection filtering currently occurs in Python;
SQL-indexed search/pagination and narrower action reads are further improvements
if profiling shows these dominate. Whole-board maintenance and invoice numbering
remain intentional serialization points. Compare equivalent datasets and cold/warm
runs before making a numeric performance claim.

## Scoped start and manual ordering

In active resource mode `start` and `start_room` share the maintenance fence.
Start locks the selected employee, physical room and customer reservation domain;
start-room resolves every waiting member, locks all those employees/rooms/customers,
and rereads membership after locking. A changed membership rejects the stale plan.
Two unrelated rooms can start concurrently. The same room/customer/employee still
conflicts, preserving PR occupancy, combo reservation and duplicate-start rules.

A standard start sets `manual_order_active=false` instead of deleting flags on all
employee rows. This monotonic invalidation is merged into metadata at commit;
concurrent starts write the same value. Only exclusive manual ordering/replacement
can turn it back on. Reads and public board flags honor the effective value, while
YC starts preserve the current manual-order state. Reorder/restore cannot overlap
starts because their maintenance fence is exclusive. Publication metadata still
has its short commit-time row lock; this is not a claim of zero shared locking.

No new schema migration is needed for this marker. Existing records without it
retain their legacy semantics. Shadow mode still uses its original global lock;
deploying this change alone does not activate resource mode. Follow the offline
activation procedure above. Rollback materializes cleared manual flags before
exporting to the old aggregate, so a prior release cannot revive obsolete ordering.
