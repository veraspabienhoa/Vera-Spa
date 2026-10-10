# Shared calendar responsiveness — 10 October 2026

## Scope and confirmed causes

The supplied screenshot identifies the calendar icon beside **Từ ngày**. This
change targets opening that calendar and applying its date, rather than claiming
to fix every server-side report load.

At base `afbfa75681abef65aa97577b6a6f94ac7a4c32a1`:

1. The visible icon button had a `showPicker()` handler but `pointer-events:
   none`. Real taps hit a transparent native date input with no explicit open
   handler. In browsers that distinguish its date segments from its indicator,
   a tap could focus the control instead of invoking the intended picker path.
2. Text blur always reapplied a complete date. Page consumers that create fresh
   filter objects, such as Reports and Online Booking, could start another read.
   Moving from an automatically focus-cleared text draft to the calendar could
   also apply an unintended empty filter before opening it.
3. Several page-specific icon widths did not override the native input's shared
   `32px !important` width. Online Booking had a 36px icon with a 32px hit area;
   staff and compact check-in fields had the opposite overlap.

These are source/event-path findings, not production database measurements.

## Changes

- The actual native hit target invokes focus and `showPicker()` synchronously
  during activation. No timer, network call or deferred mounting precedes it.
- Keep the native input mounted and its direct default action available for
  Safari, including absent, throwing or ineffective `showPicker()` versions.
- Expand the WebKit indicator over the icon hit area; align specialized native
  widths with their existing visible icons.
- Moving from text to its calendar does not commit the text draft. Restore only
  the temporary focus-cleared placeholder; preserve genuine partial edits when
  the picker is canceled.
- Skip only an already-committed, still-valid blur. Explicit Clear and explicit
  date edits still notify consumers, including optional Live Tour date validity
  and preset changes. Revalidate changed bounds.
- Add keyboard reachability, Enter/Space/Alt+Down activation and visible focus.

The shared component occurs at 91 JSX call sites in 33 files. It also backs
`VeraDateTimeInput` and `DateSearchField`. Coverage therefore includes reports,
Live Tour, revenue/purchases, training, attendance, payroll date forms, online
booking, staff/profile, leave, schedule, storage and contract forms. Month-only
fields and preset buttons keep their existing behavior. No route, permission,
cache, auth, database, financial calculation or date-range algorithm changed.
Vietnam business dates, dd-mm-yyyy presentation and ISO API values are retained.

## Reproducible offline measurement

From `web-v2`, run:

```sh
node scripts/benchmark-date-input.mjs afbfa75681abef65aa97577b6a6f94ac7a4c32a1
```

This uses Node + jsdom, 30 samples per interaction, no network, and an explicitly
synthetic 6 ms synchronous consumer callback. A representative run:

| Interaction | Base callbacks | Updated callbacks | Base median | Updated median |
| --- | ---: | ---: | ---: | ---: |
| Open unchanged focused date | 30 | 0 | 6.90 ms | 0.35 ms |
| Type complete date, then blur | 60 | 30 | 14.89 ms | 8.08 ms |

Explicit `showPicker()` invocations on the actual hit target changed from 0 to
30 in the open test. Counts are the deterministic regression evidence; timings
vary with machine load and the simulated consumer cost. They do not measure
native popup painting, mobile response time, network speed or production gains.

## Validation and remaining limits

Regression tests cover repeated opens, no-op/throwing/absent native APIs,
keyboard activation, focus-clear and genuine partial drafts, cancel, drag-away,
typed/picked ISO values, Clear then blur in real LiveTourFilters, leap dates,
min/max changes, disabled/read-only states and specialized hit-area CSS.

Final local checks: **814 Node tests passed**, **4,280 Python tests passed**
with an isolated PostgreSQL instance and external HTTP blocked, and the production
build passed. ESLint has zero errors and the existing AppearanceSettingsPage hook
warning. Independent review passed 79 focused tests. Existing date permission,
account-scope/stale-response and financial-total regressions remain in those suites.

Actual iOS/Android/Desktop native popup rendering and production timing have not
been observed in this environment. No production reads, writes, FaceID refresh,
penalty runs or payroll calculations were performed for this investigation.

A separate read-only inventory found uncancelled obsolete page reads in
Purchase, Online Booking and Snapshot, and repeated client-side history work in
Snapshot/Revenue. Those affect loading after a date is selected and are outside
this small shared-icon patch; their production cost has not been measured.
