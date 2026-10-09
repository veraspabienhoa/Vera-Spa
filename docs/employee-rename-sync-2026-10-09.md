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
