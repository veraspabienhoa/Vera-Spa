# VERA SPA maintenance notes

Before changing authentication, PostgreSQL access, attendance, Live Tour, or VPS
deployment, read [the 2026-09-13 incident record](docs/production-incident-2026-09-13.md).
The user requested that this incident and its fixes be retained for future work.

Preserve these reliability constraints:

- Attendance projections must reuse their caller's database connection. Do not
  acquire another pooled connection while holding that transaction or the Live
  Tour advisory lock. Isolate best-effort penalty writes with savepoints, and
  ensure their owning successful transactions commit the event/outbox rows.
- Keep network notification delivery outside database transactions and Live Tour
  locks. The existing TimeSoft worker delivers the committed penalty outbox.
  Preserve retries, deduplication, penalty rules and financial records.
- Keep the bounded local-auth pool separate from the business pool. Continue
  verifying session revocation and account locks in PostgreSQL; do not substitute
  cached identities or bypass authentication to make health checks pass.
- Browser login, refresh and profile verification share `apiConfig.js`. Preserve
  saved refresh credentials on network/timeout/5xx failures, but keep business
  pages gated until server verification succeeds. Confirmed 401/403 rejection
  must still sign out. Keep `authRecovery.test.mjs` and
  `authSessionTransport.test.mjs` in CI when changing these paths.
- For changes to these paths, run the relevant regressions in
  `tests/test_attendance_connection_reuse.py`, `tests/test_auth_pool.py`,
  `tests/test_auto_penalty_employee_notifications.py`, and
  `tests/test_vps_runtime_diagnostics.py`. Preserve the notification CI check and
  the business-database health check in the VPS hotfix workflow.
- Diagnose the actual production host and runtime before changing DNS, database
  settings or restarting services. Capture bounded, sanitized diagnostics before
  a restart when possible. Never print credentials, tokens, SQL parameters or
  customer data in workflow logs.
- Verify the deployed commit, both `/v2/auth/health` and `/v2/health`, and the
  affected business operation. A successful workflow or auth health check alone
  does not establish that all application screens work.

These notes do not grant deployment authority or change existing approval rules.
Update the incident record with new confirmed evidence; distinguish observations
from hypotheses and historical configuration from current configuration.

## Date display policy (user requirement)

- All visible calendar dates must use **dd/mm/yyyy**, with two-digit day/month and four-digit year, including new forms, filters, tables, reports, history, receipts and exports.
- Web V2 date fields use `VeraDateInput`; date/time fields use `VeraDateTimeInput`. Use `formatVeraDate` / `formatVeraDateTime` from `web-v2/src/lib/veraDate.js` for display. Do not introduce visible native `date` / `datetime-local` inputs whose format depends on the browser locale.
- Keep API/database values in their existing ISO formats. Convert at the presentation boundary only; preserve the Vietnam business timezone (`Asia/Ho_Chi_Minh`) and existing date-range semantics. Month-only periods and clock-only fields retain their respective formats.
- Validate real dates, leap years, incomplete input and min/max limits. A partly edited date must not submit the previous saved date silently.

## Shared UI requirements

- Booking suggestions marked “Đang rảnh” follow the employee's displayed STT from the full Live Tour snapshot, matched by employee ID. Do not substitute imported STT, alphabetical order, historical service times or positions in a filtered list. Preserve booking eligibility and the configured remaining-time threshold.
- Tables, header rows and buttons use clear, solid borders throughout desktop and mobile. Extend `web-v2/src/clear-borders.css` for shared styling; retain danger/selected states, VIP gold borders, shift highlights and keyboard focus. In the Live Tour table, the employee-name button and inline appointment input have no border because their table cells already provide the grid; retain a focus outline and keep the quick appointment toolbar bordered. Keep Clear buttons stationary on hover and their menus closed after clearing.
- Table capture images must also have legible grid lines. Do not change receipt dimensions or financial data to adjust borders.
