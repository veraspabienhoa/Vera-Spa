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

## Manual GitHub activation workflow (23-09-2026)

After merging and deploying this release with **Deploy VPS Production**, open
**Actions → Live Tour Storage Maintenance → Run workflow**, choose `main` and:

- `status` (default): verify the exact running commit, Auth/business health,
  actual API storage mode and the database authority marker. No service restart.
- `activate`: stop the API systemd control group (including its embedded
  projection scheduler/workers), back up the database, cut over, write the private
  managed mode override, restart the same release and verify runtime health.
- `rollback`: stop writers and export **current** canonical resource data back to
  the aggregate, then restart in shadow mode. This never restores an old dump over
  transactions accepted since activation.

The workflow shares deployment's concurrency group. A local file lock also
excludes simultaneous manual invocations. It refuses a different deployed SHA,
tracked source changes, multiple API units, a different process owner, an
missing/inconsistent API database environment, or a unit without `KillMode=control-group`. For a system
unit, the deployment user needs root or noninteractive sudo permission for
`systemctl stop/start <actual-unit>`; user units use `systemctl --user`. It does
not install packages or widen service permissions. Install compatible `pg_dump`
and `pg_restore` beforehand. Maintenance requires a dedicated/direct or session
pooled PostgreSQL connection; transaction pooling (including port 6543) is not
supported. All direct external Live Tour writers must be stopped separately;
this workflow supports the single VPS API unit discovered at runtime.

Activation/rollback causes a maintenance outage while the backup, conversion and
restart run. Choose a quiet period. The backup directory is
`~/.local/state/vera-spa/live-tour-backups/<UTC-timestamp>-<random>/`, mode 0700;
`database.dump`, `live-tour.json` and optional `storage.env.before` are private (0600).
`pg_restore --list` checks the custom archive before any cutover. Rehearse a full
restore on a separate test database before production activation; the archive
listing is not a complete restore test. Backups are never uploaded to Actions.
Keep them under the existing secure VPS backup/retention policy; they contain
business data. The mode override backup contains only the storage mode.

A dedicated database connection holds both the legacy and resource **session**
fences across migration commits, service restart, health verification and any
automatic recovery. New API writes fail fast until verification finishes. If the
new runtime fails, it is stopped before exporting data back and restoring the
prior configuration. If database fence ownership or recovery is uncertain, the
workflow attempts to leave the service stopped and fails visibly. Do not simply
flip the environment flag or restart an older release.

For a failed run, inspect the private `manifest.json` (release, service, original
mode) and `phase.json` in the newest backup directory through the established VPS
administration channel. If preparation failed, no cutover was applied; verify
both health endpoints. `recovered` means the prior mode was restored and checked.
For any unresolved phase, keep writers stopped, check the database ready marker
and canonical revision using the matching release, and finish/export the
canonical state with `vera_live_tour_cutover.py` before restoring a compatible
mode. If the connection failed during commit, determine committed state from a
fresh connection before taking any recovery action. Restore a dump only through
the separate database disaster-recovery process after reviewing newer writes.

The API health response now includes `live_tour_storage_ready`; a mismatch with
its actual mode returns 503. Deployment's schema helper uses API/managed settings,
and independently refuses to overwrite ready resource rows even when a CLI mode
is wrong. Legacy writes also fail before the best-effort shadow savepoint.

This workflow verifies canonical reads and readiness; it does not create bookings
or financial transactions on production as a test. After activation, observe real
booking → start → completion operations, confirm their results, and measure p50/
p95 latency and conflict rates before reporting an improvement multiplier.

### VPS with systemd environment settings

The maintenance helper accepts either the existing private managed DB/Auth file
or the allowlisted initial environment of every validated API process. It rejects
different worker settings and missing credentials; it never falls back to SSH
shell database credentials. `status` does not stop services or write configuration.

Activation persists only `VERA_LIVE_TOUR_RELATIONAL_MODE` in the private
`~/.config/vera-spa/live-tour-storage.env` (0600). The API and schema helper load
this after their existing settings. Database/Auth configuration stays in its
current location, and no systemd permissions are changed. Failed activation
restores the old override, or removes the newly created file if none existed.
The private manifest records `mode_override_existed` for manual recovery.
`activate` and `rollback` also run an explicit `status` check before maintenance.

### Activation preflight diagnostics

`status` reports `activation_preflight` separately from API/database health.
Its `service`, `scope` and `errors` identify missing noninteractive service-control
permissions, missing PostgreSQL clients, or the unsupported transaction-pool port.
`ok=true` at the top level means storage health passed; inspect
`activation_preflight.ok` before attempting activation. These checks do not stop
writers, grant sudo permissions, or install software. Activation refuses the same
missing requirements before stopping the API.

If the sudo authorization check fails, the VPS administrator must inspect the
existing policy for the exact command/service reported in `errors`. Deployment
permission to run deploy.sh or restart a service does not necessarily authorize
separate stop/start commands. Do not use broad NOPASSWD ALL, bypass service
control with process signals, or disable permission checks. A successful
preflight is not a full backup/restore rehearsal or a performance measurement.

### Backup scope: privileged scheduler excluded

The cutover archive uses `--exclude-schema=cron --exclude-extension=pg_cron`
(PostgreSQL 17+ client; the reported VPS client is 17.11). The API role failed
schema-only dumping with `permission denied for schema cron`. No application
permission is expanded. Other schemas remain included; another permission error
still stops backup and prevents cutover. Do not silently exclude additional schemas.

The archive is a cutover backup, not a complete instance disaster-recovery backup:
cron job definitions/history and the pg_cron extension are excluded. Keep their
separate administrator-managed backup for full database restoration. Cutover does
not change scheduler configuration. The repository's pg_cron watchdog invokes the
API, which remains protected by the existing maintenance fences.

Before conversion, pg_restore's archive listing must contain both TABLE and TABLE
DATA entries in public for the aggregate, metadata, idempotency, room claims and
all resource collection tables. A missing entry or empty archive refuses cutover.
`backup-scope.json` privately records the exclusions and verified table names.
This membership check does not replace a full restore rehearsal on an isolated DB.
