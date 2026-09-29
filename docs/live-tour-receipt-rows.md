# Live Tour receipt row storage

The metadata JSON held roughly 10.9 MB of durable idempotency receipts on
29-09-2026. Every changed receipt rewrote this archive while holding the global
publication row lock. The new format stores each entire original receipt in the
reserved mutation table's `result` column, indexed by idempotency key. The
metadata row retains the short commit-order revision and small configuration.
Resource and receipt changes still commit atomically on the caller connection.

## Activation after merge and deployment

1. Deploy the merged compatible release normally. Deployment alone leaves the
   current receipt format unchanged.
2. Run **Live Tour Storage Maintenance → status** on `main`. Require active
   resource storage, matching deployed SHA and successful activation preflight.
3. Run **optimize_receipts**. The workflow briefly stops the API and embedded
   writers, holds both writer fences, validates its private backup, migrates and
   checks exact canonical parity, then verifies the restarted release.
4. Run **status** again: require `receipt_storage: rows`, `mode: active`, and
   `resource_ready: true`. Both auth/business health gates must pass. Test normal
   booking → start → finish and a repeated payment request using an approved test
   record. Re-measure actual production latency before claiming a speedup.

No financial receipt is expired or reconstructed from business guesses. Unknown
legacy fields survive migration. A nonempty unrecognized mutation table blocks
migration. The PostgreSQL benchmark uses a synthetic ~10 MB archive and seven
write/commit samples per format; CI prints its results separately. Those numbers
measure isolated database work, not the production end-to-end speedup.

## Rollback

Before deploying an older release, run **restore_receipts** while this compatible
release is still running. This exports all current receipt rows back into the
inline archive and verifies parity. Never manually remove the readiness marker:
the database guard rejects inline writes or marker removal after activation.
The existing whole-storage **rollback** action also exports current receipts
before switching to aggregate storage. Backups include the mutation table.

If maintenance reports automatic recovery incomplete, leave writers stopped and
inspect the private phase file/service state. Do not change flags or restore an
old snapshot over current financial data. The workflow does not grant permission
to deploy or migrate production by itself.
