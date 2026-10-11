# Immediate arrival fines · 11-10-2026

Owner requires a late, verified Face ID arrival to be processed as soon as its
archive capture is ingested, for staff other than admin, giamdoc, quanly and
support. Scheduled VERA shifts (including earlier overtime) remain authoritative;
blank export clock cells use saved shift definitions, never guessed clocks.

HC now uses the shared proven employee/day issue scope. A scoped conflict no
longer blocks unrelated staff. Unknown/global conflicts, incomplete/stale
captures, future evidence and identity ambiguity still defer writes. Evidence is
rechecked on the existing write connection after the employee lock. No second
pooled connection or network call is introduced inside a transaction.

HC eligibility checks both account role and assigned department against the four
excluded groups, including custom HC departments and KTV-role accounts assigned
to an HC schedule. KTV departments continue using the existing official-catalog
writer; they do not receive a second wage-based HC fine. Existing activation,
pause, approved leave/holiday, salary settings and replay safeguards remain.
Disabled rules are not silently activated and missing wage data is not invented.

The canonical FaceGate KTV arrival writer accepts every finite positive delay,
including seconds. Registered-late baselines and approved support allowances
remain applied before writing. Shared arrival validation permits these fines;
the existing grace cleanup no longer revokes them. Break-return grace and absence
cutoffs are unchanged. HC already measured fractional-minute lateness.

The FaceGate minute archive worker now invokes the canonical KTV arrival writer
after committing publication, alongside its existing HC path. Candidate reads
close before the writer opens transactions; logs contain aggregate counts only.
Both paths honor the Auto Check pause switch.

The ingestion schedule is still every minute; immediate means the same worker
pass that receives complete verified evidence, not a push event from the device.
This source change does not backfill old fines, edit real schedules, alter stored
financial history, or deploy to production. Verify the deployed SHA, source
freshness, eligibility/activation and actual arrival-to-ledger operation after
operator deployment.
