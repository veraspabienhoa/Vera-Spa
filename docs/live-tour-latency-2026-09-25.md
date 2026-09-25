# Booking/start/finish latency — 25-09-2026

## Observed production evidence

The operator reports approximately five seconds for booking, start and finish.
Read-only diagnostic run 36128412508, job 108151608853, sampled the active
8d07bf33 release at 23:12–23:13 Vietnam time. No blocked transactions or active
queue alert were observed in that sample. This does not rule out contention
during an operator action.

The metadata JSON measured 8,318,846 text bytes; 8,307,619 belonged to retained
idempotency receipts. The bounded read/response profiler measured 0.476 seconds
reading an invoice snapshot and 0.404 seconds rendering its first 50 invoices.
It counted 50,097 normalization calls and 817 catalog room-group lookups.
This was a read-only invoice/board probe, not a timed production mutation.

## Changes

- Cache pure short-string normalization with limits of 4,096 entries and 256
  input characters. No state, authorization or financial decisions are cached.
- Build room and private-service lookups for each response. Compute occupied
  beds/private groups once, preserving room availability, PR and retained-worker rules.
- Exclude pending invoices from compact lock discovery when no pending ID is
  used. Authoritative operational validation still reads its full certified set.
- Batch changed resources, deletions and employee history per table in the
  existing atomic transaction; preserve deterministic history order, revisions,
  financial locks, audit trimming and idempotency.
- Log numeric phase timings and SQL counts for actions exceeding 500 ms and
  transaction failures. Never log SQL, bind values, identities or business data.
  Timings start inside the action endpoint after authentication and end before
  HTTP serialization; they do not include network/authentication latency.

## Verification and limits

Synthetic fixture: 45 workers and 50 beds, 30 response builds per version.
Baseline median 50.50 ms; changed median 3.64 ms. Complete response equality
checked for viewer, operator and admin grants. These local numbers are not
production request latency guarantees.

PostgreSQL integration verifies that changing 50 employees uses three write
statements (publication, employee batch, history batch), persists all 50 history
entries in deterministic order and preserves state. Existing scoped action,
replay, conflict, rollback, attendance/auth/notification suites remain required.

The metadata receipt archive still grows and its row is rewritten at publication.
Moving those durable receipts to individual rows requires a migration and
rollback design; this release does not remove them. New LIVE_TOUR_TIMING logs
separate authorization, locked reads, business logic, write, commit, response read
and rendering to guide that decision with actual mutation evidence.
