# Automatic attendance fines: evidence isolation and source parity

## Confirmed source defects

- The FaceGate adapter could identify an issue for one employee, while the
  runtime set `attendance_evidence_issues` on every projected employee. The
  arrival worker and confirmed-return rule then discarded all candidates.
- The standalone snapshot worker called the legacy attendance function, whose
  replacement was installed only by API startup. After FaceGate cutover this
  could read retained TimeSoft caches instead of the selected source.
- Archive publication repeated a range-wide issue count for each date, and the
  Auto Check page displayed the configuration switch without evidence health.

These source reproductions do not establish the exact unresolved production
scan or prove that every reported day was blocked. Deployment and live readback
remain necessary. Existing financial history is not reconciled or backfilled.

## Safety boundaries

Only issues produced after confirmed identity/address validation and exhaustive
VERA shift-window matching can carry an employee-and-business-day scope. The
allowlist is overlapping shifts and unverified status/type. Unknown mappings,
changed device addresses, conflicting duplicates, invalid timestamps and invalid
reviewed evidence remain globally blocking. A username by itself is insufficient.
An overnight ambiguity includes every possible VERA business day. The persisted
conflict ledger is read in the same bounded device/date range, including the
next calendar day for overnight evidence. Missing/unreadable conflict history
fails closed. Even metadata-only drift remains blocked until reviewed; this
repair does not invent a resolution or erase conflict records.

Unaffected employees still require a complete archive capture, a timestamp with
an explicit timezone, and fresh evidence no more than five minutes old. An
ongoing overnight shift needs both relevant calendar-day captures. No required
capture may be dated in the future, and scans later than the completed capture
invalidate completeness. A previous overnight calendar capture must extend
through midnight; the governing current/closed-window capture must be fresh. Late-return
and restricted-outing writes require the same affirmative readiness flag. The
existing payroll-close requirements remain independent and conservative.

Missing-check-in absences remain current-day only, after the strict 17:00/19:00
cutoffs and a later completed capture. They recheck identity, conflicts, freshness
and presence while holding the employee lock before any write. Popup decision
clocks (15:00/17:00 for registered late arrivals) are unchanged. Grace periods,
official amounts, leave exceptions, idempotency and notification ownership remain
unchanged. The live pause switch applies to API and standalone return writers.

The standalone worker calls the explicit canonical source-aware reader on its
existing connection. It does not import API startup or request a second pool
connection. Immediately before a positive write, arrival/return workers reread
canonical evidence on the write connection and defer changed/conflicted facts.
The return worker uses one caller transaction and per-candidate savepoints;
success is reported only after commit. The approved late-return interval matches
the existing API path.

## Diagnostics

The existing Auto Check view gains an explicitly opened Admin-only read-only
status modal with Tạm ẩn, Mở lại and Close controls. Hiding or closing the modal
never changes the penalty switch. Loaded state stays scoped to the current
account/page; late responses cannot reopen a dismissed modal or cross accounts.
It uses a fixed Vietnam today/yesterday range and one repeatable-read, read-only
transaction. Aggregate issue reasons distinguish global blockers from proven
employee/day scopes; capture completeness, freshness and last-sync time are
shown separately from the configuration switch. No employee names, raw event
payloads, device references or financial writes are part of this diagnostic.
The intentionally removed full FaceGate preview panel is not restored.

Publication reports now distinguish per-day applicable blocking issues from
range-wide issue totals. A global issue applies conservatively to every date in
the projection; its presence does not prove it existed on each historical day.

## Verification and deployment handoff

Regression coverage uses synthetic identities and local disposable PostgreSQL.
It exercises scoped multi-employee conflicts, unknown/global conflicts,
overnight dates, stale/incomplete captures, current-day absence rechecks,
standalone source parity, role gates, grace and replay safeguards.

After authorized deployment, inspect the Admin read-only diagnostic and the
current source-health endpoint, verify the deployed commit and both auth and
business health endpoints, then verify current-day worker results. If a global
issue remains, investigate its exact archived evidence with authorized Admin
read-only tools. Do not delete scans, guess an identity, bypass the guards, or
create historical fines to clear the warning.


### Local validation (10-10-2026)

The complete Python suite passed: **3,247 tests**, real isolated PostgreSQL 16,
no skips; six existing SQLite/Python date-adapter deprecation warnings. The test
runner used a local test-only HTTP guard inherited by child Python processes,
blocking external requests before proxy routing. No live device, bank-catalog,
attendance, payroll or production service was accessed by this verification.
All **636 Node tests** passed, including modal open/hide/reopen/Close,
Escape/focus, late responses, repeated clicks and account/session isolation.
Full ESLint reported zero errors and the existing AppearanceSettingsPage hook
warning. The production Vite build and Python compilation passed. Mounted
DOM tests cover behavior; an actual browser screenshot was not verified here.
Exact-commit remote CI must also pass before merge. Production readback still
belongs to the authorized deployment.
