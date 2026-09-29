# FaceGate: reviewed extended checkout (28-09-2026)

## Confirmed evidence, not a general shift rule

The operator confirmed that Yen Linh's scan at 28-09-2026 00:33:58 is
checkout for work day 27-09-2026, following arrival at 27-09-2026 10:08:07.
The supplied read-only VPS output contains five events, all on the current
registered device and directly mapped to Yen Linh, observed status/type 1/0:

| Event | Local timestamp (+07:00) | Reviewed use |
| --- | --- | --- |
| 79010 | 27-09-2026 10:08:04 | Preserve arrival-cluster evidence |
| 79011 | 27-09-2026 10:08:07 | Explicit arrival anchor |
| 79012 | 27-09-2026 10:08:09 | Preserve arrival-cluster evidence |
| 79106 | 28-09-2026 00:33:56 | Preserve checkout-cluster evidence |
| 79107 | 28-09-2026 00:33:58 | Explicit checkout anchor, work day 27 |

The anchor span is 51,951 seconds (14:25:51), not verified payable hours.
No inference is made for Trong Nguyen, Le Son or another employee/date.

## Implementation and boundaries

`vera_facegate_checkout_review.py` stores reviewed exceptions in
`vera_app_setting` under category `facegate`, key `checkout_reviews_<device>`.
Deployment alone writes no review. Only explicit local-root CLI `--apply`
adds the approved case after checking every event, exact timestamps, current
confirmed mapping, role, device, status and payload fingerprints. It backs up
prior reviews in a root-only file, serializes review writes, pins registry and
mapping rows, and preserves previous audit on an identical repeat. Changed
saved reviews are rejected, not overwritten.

The shadow reader uses the caller's connection and no network. It includes the
previous day only when needed to validate a persisted adjacent review. It
reassigns only the five specified IDs and removes only their resolved
`no_vera_shift` issues. The selected representative timestamps are separate from
all five preserved raw events in `reviewed_raw_events`. Scheduled start/end,
raw archive, employee mappings, production attendance, payroll and penalties
are not written. Invalid reviews remain blocking; other off-shift events and
existing comparison/cutover gates are unchanged.

## Local checks and remaining verification

29 local checks passed: pure validation/projection and engine integration with
mock database/shared-reader dependencies. Python syntax was compiled. These
are not live PostgreSQL, device, browser, full-suite or production tests.
Existing broader reliability regressions in AGENTS.md remain required in CI;
no green full-suite or successful VPS deployment is asserted here.

## Operator execution after the manual deployment

Run on the deployed release, as the local VPS administrator:

```bash
cd /opt/vera-spa/current
/opt/vera-spa/.venv/bin/python vera_facegate_checkout_review.py --case yen-linh-2026-09-27
/opt/vera-spa/.venv/bin/python vera_facegate_checkout_review.py --case yen-linh-2026-09-27 --apply
```

The first invocation is read-only. The apply invocation validates the proposed
shadow result before writing, backs up the review setting, then reads the
committed setting and projects both days again. Preserve its backup path.
Expected: the reviewed row for day 27 has 10:08:07 -> next-day 00:33:58; day 28
retains its separate scans. A failure after commit reports `committed: true`;
do not treat a readback failure as a rolled-back write or blindly retry.
`payroll_and_penalties_written` and `attendance_cutover_ready` remain false.
TimeSoft comparison normalization and the other cutover conditions are not
resolved by this patch.

## 29-09-2026: operator preview evidence and CI repair

The supplied VPS log now shows a successful isolated preview of the pinned
`dbfd0abd87acb4851e4b403b6d34b955481bbb2e` source: five events verified,
`applied: false`, `already_applied: false`, and no Yen Linh-specific issues.
Day 27 uses 10:08:07 -> next-day 00:33:58; day 28 remains 09:09:21 -> 18:06:05.
The log reports `current` at `0c896b97cabc5699a2719b34964b859ab9040ad5`;
this identifies the directory, not independent verification of the serving PID.
No apply, restart, production deployment or payable-hours verification is
established by that log. All seven reported cutover blockers remain unresolved.

CI run 36449959151 on the pinned source reported two failures and 2070 passes.
One failure exposed a real identity guard gap: missing or invalid references
could enter the unique-confirmed-name fallback intended for valid stale refs.
The adapter now rejects invalid refs before that fallback; direct mappings,
valid stale refs, device/status checks, raw payloads and shift logic are retained.

The other failure used obsolete archive expectations. `persist_batch` already
skips empty event INSERTs and audits metadata drift separately. Tests now assert
three SQL statements for exact replay, unchanged original rows, valid observed
payload/hash pairs, conflict observation counts, 250-row chunk boundaries and
transactional rollback of events, conflict audit and day metadata together.
A real-PostgreSQL shadow-preview test also keeps missing references blocking.
The archive writer, database schema, connection handling and workflows are not
changed to satisfy these tests; no production data is written by this patch.

At patch preparation, the full adapter source and existing modified files were
matched to their GitHub blob hashes. The isolated adapter regression run changed
from 15 failed / 16 passed before the fix to 31 passed after it. Dependencies were
isolated; this is not the full application or a PostgreSQL run. PostgreSQL 16 and
all AGENTS.md reliability regressions remain CI gates before merge. Deployment
remains operator-only after the required checks, followed by verification of
the serving commit, both health endpoints and the affected business operation.
Do not run --apply from the isolated diagnostic checkout or enable production
FaceGate attendance solely because this preview or CI is successful.
