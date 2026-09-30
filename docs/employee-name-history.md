# Employee rename continuity — 30-09-2026

The operator confirms that Anh Nguyễn / Anh Nguyen is the employee now named
Gia Anh (directory full name Nguyễn Gia Anh). The combo ledger previously
grouped by its original employee_username while the directory used the new
username. The system-name route omitted that ledger, so old sales disappeared
from the current employee's group and commission count.

The shared name-history resolver uses explicit previous usernames, not fuzzy
matching or customer names. This confirmed legacy alias requires the known
current directory identity. An occupied name (including a deleted account) or
an alias claimed by multiple employees is not remapped. Device identity reviews
and raw scan payloads do not use this resolver.

Combo list/export/count project the same canonical owner without changing
stored sales. Each existing sale ID is counted once. Add/edit/import canonicalize
an old form or workbook to the current username, within the same transaction.
Writes lock directory keys to serialize with renaming. No ledger is deleted,
duplicated or automatically saved to payroll by deployment.

Future system-name changes record the full name chain in employee payload and
update the existing direct references plus combo sales, Face ID photos/settings,
training/evaluation assignments/recipients and HR leave periods atomically.
Conflicting dependent keys reject the rename and roll everything back. Auth
user ID follows the existing FK cascade. Historical names are not login aliases.
Live Tour reconciliation recognizes the chain without replacing an employee's
stable tour ID or clearing open work.

Scope and verification: this is not a migration of arbitrary text, audit actors,
paid invoice snapshots, saved payroll JSON, FaceGate mapping/review evidence or
legacy external archives. Those stores must retain their original evidence and
need explicit reader-specific treatment before claiming every historical screen
has been relabelled. Attendance work remains paused. No production DB was read
or changed during implementation. After backend deployment, verify Gia Anh's
combo list and Excel for the affected month and confirm the same sale IDs/count;
inspect any occupied/ambiguous old account instead of silently merging it.

Regression tests cover alias collisions, repeated renames, PostgreSQL rollback,
photo bytes/auth ID preservation, list/export/count parity, stale-form writes
and Live Tour continuity. CI provides isolated PostgreSQL; local compilation
does not establish production correctness.
