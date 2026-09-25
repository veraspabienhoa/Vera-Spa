# Admin schedule for completed Live Tour technical jobs

The Admin-only **Cài đặt → Lưu nhật ký** panel saves two independent values:

- Keep completed technical jobs for 1, 2 or 3 days (existing default: 3).
- Check whether cleanup is due every 5 minutes and run it at the configured
  interval, from 1 through 168 whole hours (default: 1 hour).

The interval is measured from the last successfully completed cleanup. Extending
it postpones the next due time; shortening it can make the next check due.
Saving settings does not delete anything or reset the success timestamp. The
panel shows the saved interval, last success, removed count and next due time in
Vietnam time. A failed initial read disables saving until a retry succeeds.
Old clients sending only `days` preserve the configured interval.

## Execution and scope

`vera_technical_retention.py --apply --scheduled` reads the same PostgreSQL
setting as the API. If it is not due, it skips before scanning the queue. A
dedicated session advisory lock prevents overlapping processes, including manual
workflow checks. It is unrelated to the Live Tour action locks. Batches reuse one
connection, commit at most 500 deletes at a time, skip locked rows and have short
statement/lock timeouts. A failed or budget-limited run leaves the prior success
timestamp unchanged, allowing another attempt at the next five-minute check.

Only unlocked, completed `live_tour_projection` jobs older than the configured
number of days are eligible. Pending/running/retry/failed jobs, booking, invoices,
business audit history, reports, attendance and replay protection are untouched.
The existing explicit `--apply` CLI remains available for maintenance without the
due check; production timers and the manual GitHub fallback always use
`--scheduled`.

## Deployment and verification

Deploy VPS Production now migrates the existing settings table, previews eligible
jobs, installs `vera-technical-retention.timer`, and starts one due-checked pass.
The timer runs on the VPS even when no browser is open. This replaces the hourly
GitHub cron; that workflow remains a manual, due-checked fallback. Changes to the
interval require no timer rewrite, service restart or redeployment.

The additive migration preserves the configured retention days and records no
invented historical success. A first run with no success timestamp is due.
Before enabling the timer, deployment must reach the schema and active-release
checks. The installer verifies the enabled/active timer and the service result;
the final deployment gate still verifies the exact commit and both health APIs.
After deployment, open the Admin panel and reload its status to confirm the first
successful pass. Code and CI success alone do not establish production activity.

Rollback: disable/stop `vera-technical-retention.timer` before rolling back to a
release without the runner. Keep the additive columns; old clients ignore them.
The wrapper follows the running API release and never falls back to ungated
cleanup if that release lacks `--scheduled`. Cleanup deletes cannot be undone
without a database backup.

## Regression coverage

Real PostgreSQL tests cover migration, due/not-due behavior, interval changes,
simultaneous runners, failure recovery, bounded-run retry, and unchanged deletion
scope. API tests enforce Admin-only access and reject non-integer/out-of-range
hours. Browser component tests cover loading/saving both controls, Vietnam date
display, invalid values, failed loads and preserved drafts after failed saves.
