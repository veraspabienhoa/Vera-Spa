# Phase three: shorter checkout locks and explicit worker isolation

This change contains source and synthetic verification only. Production host
capacity, process counts and current runtime configuration have not been
inspected. It does not deploy, migrate financial data, stop services or activate
new modes automatically.

## Invoice numbering

The existing compact checkout still fetched every historical invoice-number
header and every void/correction-number header. Python copied and normalized
those headers under the financial ledger lock before choosing the next number.
After explicit activation, checkout reads only operational data and its current
idempotency receipt/current canonical invoice. The separate SQL UNION branches
allow PostgreSQL to skip the entire legacy history scan. Receipt replay after
an edit or void still reads canonical current state, and customer/employee,
combo, date, monetary and permission rules remain unchanged.

`vera_live_tour_bill_numbers` owns an immutable normalized-number primary key,
raw aliases with their original invoice owner, and transactional per-calendar-day
counters. Normalization is the same existing Python Unicode/underscore/whitespace
normalization. PostgreSQL locale is never used as an approximation. VERA and
legacy LIVE prefixes contribute to the same day floor; their manual spellings
retain existing distinct-number behavior. Checkout uses its effective Vietnam
calendar day; combo sales keep their existing business-day calculation.

Backfill includes canonical invoices even when soft-deleted and both sides of
invoice correction history. It preserves existing counter floors. Conflicting
legacy owners or an unindexably long number refuse activation with no partial
change. A 2,000 UTF-8-byte normalized key ceiling leaves room below PostgreSQL's
btree limit; a legacy number over that bound keeps the application on the
unchanged legacy path until explicitly reconciled. Source invoice payloads,
amounts, receipts and histories are not rewritten by activation.

A failed action rolls back its reservation, counter, receipt and financial rows
together. Successfully issued numbers are never released, including after voids.
Manual and automatic allocations take counter/reservation locks in the same
order. The registry guard rejects unregistered numbers from older writers after
activation, and prevents silently dropping readiness or returning to aggregate
storage. Registration rows cannot be deleted, renamed or assigned to a different
invoice. Raw alias additions are append-only.

The full financial ledger lock is deliberately retained. The shared metadata
row still orders publication and commit; it is not replaced with a sequence.
CPU-only row diffs, hashes and query projections now happen before acquiring
that publication row. Independent financial transactions are still serialized
at their ledger boundary and may return the existing retryable 503. Other
resource-scoped operations keep their existing overlap/locking safeguards.

## Safe rollout

1. Deploy this source through the normal owner-controlled workflow. The existing
   schema gate installs the new registry schema only. It does not activate it.
   Until activation, new and old releases retain existing behavior and reads.
2. Rehearse activation and parity with representative disposable data. Check
   transaction/lock deadlines and all running API, projection and CLI writer
   versions. Do not increase timeouts automatically to force a large migration.
3. Schedule a maintenance window and stop every writer. Run from the deployed
   registry-aware release: `python vera_live_tour_bill_numbers.py --activate
   --writers-stopped`. The command obtains both existing transaction fences,
   performs one atomic backfill and installs old-writer guards. A busy fence,
   collision, missing authority or timeout rolls back the attempted activation.
4. Run `python vera_live_tour_bill_numbers.py --verify`. Check its active flag,
   parity and zero missing/counter mismatches before restarting matching writers.
   Restart only registry-aware releases. A rolling deployment with old financial
   writers after activation is unsupported and fails closed on their inserts.
5. Verify the exact deployed SHA, `/v2/auth/health`, `/v2/health`, worker readiness,
   a permitted checkout, duplicate retry, edited/voided receipt read, combo balance
   and backdated date behavior using an operator-approved verification plan.
   Technical health alone does not prove financial or attendance correctness.

## Rollback

Before activation, ordinary code rollback is unchanged. After activation,
prefer a registry-aware release rollback. To permit a pre-registry release, stop
all writers and run `python vera_live_tour_bill_numbers.py --deactivate
--writers-stopped`. It proves every permanently reserved normalized number is
still visible to the old allocator in live invoice or correction-before history,
exports the highest counter floors, then removes only active write guards. It
never drops the permanent registry. Missing legacy coverage refuses rollback;
do not disable the guards or edit reservations to bypass this check.

The existing resource-to-aggregate rollback now performs this same verified
number deactivation first. An old rollback command cannot silently discard the
active registry invariant. Activation can be rerun after a verified rollback;
existing reservations remain permanent and new legacy numbers are reconciled.

## Remaining limits

The optimized number path needs an explicit operator activation. Checkout still
reads its operational/customer/pending set; combo-sale full responses, exports,
full-board responses and other history views retain their previous read profiles.
The ledger lock and global publication row remain shared boundaries. The paired
benchmark explicitly activates the existing indexed receipt storage in both
versions. A deployment still using inline receipts can retain an O(receipt-history)
metadata update even after number activation; this change does not activate the
separate receipt migration automatically, and the live receipt mode is unverified.
Synthetic throughput is neither production latency nor a VPS concurrent-user capacity
promise. Worker isolation is detailed in [the worker rollout guide](worker-runtime-2026-10-11.md),
connection budgets in [the runtime budget guide](phase-three-runtime-budget-2026-10-11.md),
and repeatable measurements in [the PostgreSQL benchmark method](checkout-postgres-benchmark.md).
Split roles require verified host configuration before operator activation.

## Local acceptance checks (11-10-2026)

Repeated after integrating reports hotfix #527 (main `61643b1a`). The benchmark
core/harness hashes are unchanged by this rebase and match the published raw data.

- All 4,411 Python tests passed with an isolated PostgreSQL 16 server and outbound
  HTTP blocked, including concurrent activation, financial rollback/replay,
  migration guards, real worker lifespans and claim ownership.
- All 838 frontend Node tests passed with bounded local test concurrency; lint
  passed with one existing hook-dependency warning, and the production build passed.
- All 266 root/script Python sources compiled. No production database or external
  device was used for these checks.
- Independent source reviews covered financial invariants, worker/runtime behavior
  and the final idempotent trigger-DDL hardening. Exact published-head GitHub CI
  remains a separate merge gate; local results do not stand in for it.
