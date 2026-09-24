# FaceGate direct log archive

This stage saves a complete day of raw Control Log metadata in VERA PostgreSQL. It does not activate attendance calculation, change TimeSoft jobs, enroll photos, or match faces. The existing authenticated admin mapping remains the only reference association. Reference-match counts are a snapshot for review, not payroll eligibility; live profile revalidation and shift projection are still required before cutover.

## Commands on the VPS

Keep the existing private tunnel to the device running. Run from /opt/vera-spa/current with /opt/vera-spa/.venv/bin/python.

```bash
/opt/vera-spa/.venv/bin/python vera_facegate_sync.py --date 2026-09-24
/opt/vera-spa/.venv/bin/python vera_facegate_sync.py --date 2026-09-24 --apply
```

The first command is read-only and creates no tables. The second creates the archive schema and commits the batch atomically. Repeat --apply to verify inserted_count=0 for an unchanged day. Never conclude success from the command being invoked: require ok=true and applied=true, then inspect stored_day_count. Failures print only a safe reason/type. A connection loss during commit can leave outcome unknown; rerun safely to determine counts.

## Guarantees and limits

- Default adapter cap: 2,000 events; total_count must equal the unique parsed record count, and truncated must be false. Missing/invalid rows, duplicate IDs and out-of-day records abort before writes.
- Requested dates use Vietnam time. This verifies a complete query snapshot, not finality of today's events or the device clock's accuracy.
- Unique key: device ID, event ID and device timestamp. Identical retries do not duplicate; differing content on the same key rolls back the entire batch. Device reset/reused IDs at the exact same timestamp require operator investigation.
- Unknown/unmapped events are retained, without being assigned to an employee by name. Only metadata is saved; no photos or credentials.
- Network requests run before the write transaction, using no held DB connection. A per-device transaction advisory lock rejects concurrent writers. A decreasing daily device count aborts without deleting retained evidence.
- Archive tables: vera_facegate_event and vera_facegate_sync_day. Deleting old device logs does not delete archived events. This release intentionally provides no destructive purge command.
- Deadline 180 seconds, DB connect timeout 5 seconds, statement timeout 5 seconds, lock timeout 2 seconds. A day too large/slow fails; no incomplete checkpoint is marked complete.
- The CLI is operator-only on VPS, not a public unauthenticated endpoint. No unattended schedule is installed yet. The temporary SSH tunnel remains a connection dependency.

## Production acceptance and next stage

After deploy, preview a known day and compare fetched_count to the device. Apply once, repeat to verify deduplication. Retain unmatched events while admins confirm remaining staff mappings. Next work: archive-backed UI/API, durable relay/scheduling, live-profile validation, verified status policy, attendance projection using VERA shifts, and controlled source cutover. Do not stop TimeSoft until those are validated.

Local tests exercise transactional inserts/rollback with SQLite and simulate the PostgreSQL advisory-lock response. They do not establish real PostgreSQL/device integration. Run the above production acceptance steps before claiming that the archive is operational.
