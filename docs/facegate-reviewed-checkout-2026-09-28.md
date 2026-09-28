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
