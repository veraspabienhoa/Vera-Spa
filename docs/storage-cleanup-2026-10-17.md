# Bộ nhớ: phạm vi xóa theo nhóm

Source changes only; no production deletion or deployment.

Admin can select an inclusive date range or all time (including undated rows),
then one of five explicit groups or all five: leave, payroll, attendance
(TimeSoft cache, FaceGate evidence/conflicts/sync status, mobile events), purchase
entries and manual revenue entries. Counts are physical rows, including copies.
Payroll removes normalized rows and cache copies together.

Preview fingerprints bind dataset, scope, dates and actual content, not just
counts. Deletion rechecks under table write locks with a five-second lock
timeout. The caller owns one transaction for all selected groups and the audit
record. Any failure rolls back the entire operation. Non-Admin access remains
blocked regardless of feature grants. The UI ignores stale preview responses,
invalidates confirmation on scope changes and awaits the shared confirmation.

This is NOT a factory reset. Accounts, employee profiles, settings, Live Tour
invoices/bookings/combo ledgers, payroll debts, other business modules, source
files and audit history are retained. External device/source synchronization
can restore deleted evidence. No remote device or Google Sheet data is erased.
The existing three-sheet Excel export remains a date-range report, not a full
system backup. The UI states these boundaries explicitly.

A complete operational reset is still outstanding: it needs consistent handling
of Live Tour aggregate and relational representations, receipts, combo balances,
payroll debts, background jobs, backups and external import sources. It must not
be implemented as schema-wide TRUNCATE/CASCADE or by deleting only one mirror.

Validation: frontend production build; stale-preview UI regression; scope/date
unit test. PostgreSQL regressions cover all-time undated rows, range boundaries
in Vietnam time, copies, same-count changes, atomic rollback, Admin checks and
audit writes. Run those with VERA_TEST_POSTGRES_URL on the CI test database.
