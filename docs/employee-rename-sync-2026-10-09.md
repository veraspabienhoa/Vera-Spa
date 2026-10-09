# Employee name synchronization — 09-10-2026

The system-name endpoint moves canonical account references in the employee
transaction. The reference migration covers typed username columns and structured
employee owner fields in business JSON, including payroll snapshots, accumulation,
account permission targets and FaceGate mappings. It uses the existing Live Tour
writer under its maintenance fence, preserving resource IDs, revision checks and
financial values. Customer/service names and previous-name aliases are unchanged.
Raw hardware evidence, retired identity archives and frozen receipts remain
original evidence; they are not reassigned to another employee.

A confirmed FaceGate mapping creates a durable rename job in that transaction.
After commit the API attempts the device update; TimeSoft's scheduled job also
processes pending jobs. The device operation preserves UID, face registration
reference, token and other profile fields, then verifies the read-back. A retry
reads first and accepts an already completed rename. Changed device IP, mapping,
face reference or profile name fails closed. Pending rename jobs prevent another
rename and enrollment/photo replacement until resolved. Network I/O occurs outside
business transactions and Live Tour locks. Offline devices produce a pending
message rather than a false success.

Validation: relevant Python regressions and production frontend build passed.
The PostgreSQL migration/rollback test requires VERA_TEST_POSTGRES_URL and runs
in the existing CI service database; local execution skips it. No production
records or physical device were changed during development. Physical firmware
name updates still require production verification after deployment.

## Physical verification and lifecycle follow-up

Production run 37909870265 deployed merge commit 3155d04 and verified the active
release, both health endpoints and frontend. Owner-authorized maintenance changed
the unique active letan account to Assistant. It initially had no confirmed device
mapping. After the operator enrolled its face, run 37913475510 synchronized the
mapped physical profile and verified the name Assistant, preserved auth identity,
saved face photo and device profile ID. Original registration used full_name;
the newly registered physical profile therefore needed this name correction.

The source follow-up uses the canonical username for new enrollment; photo
replacement retains its already confirmed profile. Firmware name limits are
shared with rename, rejecting an unsupported mapped name before committing the
account transaction. FaceGate's existing minute worker now processes durable name
jobs even while TimeSoft networking is disabled, and still archives attendance
after a name retry failure. The name worker uses one connection for its session
lock and commits every transaction before device I/O. Lost replies are reconciled
by read-back without replaying a completed write. The one-off Assistant workflow
is manual-only after its authorized operation completed.

These follow-up changes require CI and deployment before they affect production.
