# Training progress reports and compact purchase total (10-10-2026)

## Requested display changes

- Purchase controls explicitly own their grid layout, so Revenue's global summary
  style cannot stretch the purchase total. The VND total keeps a content-sized
  tile; toolbar actions wrap as complete buttons at constrained widths.
- The separate Training History tab and duplicate employee-selector panel are
  removed. Historical training and evaluation records are retained and appear in
  each employee's progress modal. No database deletion or migration is involved.
- Immediately below the trained/evaluated employee heading, the roster supports
  typing a name, selecting a matching employee, a training day, a calendar month,
  or an inclusive custom range. Partial/invalid date drafts do not reuse an old
  range. Display dates use dd-mm-yyyy.
- Selecting an employee opens an accessible modal with the full daily journal,
  skill progress, latest competence radar, seven evaluation criteria and history.
  Escape, keyboard focus restoration, close/reopen and account changes are covered.

## Data and permission semantics

The existing `training_view` permission, verified identity and training role-pair
rules remain authoritative. Explicit `vera_training_scope` records did not govern
report viewing before this change and are not assigned new meaning here.

The roster contains only authorized active employees with actual training or
submitted evaluation records matching the current dates. Training uses the
Vietnam calendar `training_date`; evaluation uses the existing cycle `end_date`.
The UI explains this distinction. All-time truly has no date cutoff.

`_read_training_report` is the shared filtered DTO for journal, history, charts
and both export formats. Query/rating filters also feed aggregates. Unknown grades
and absent criterion values never become fabricated zero scores. Paginated JSON
history is fully loaded before display, and full DTO signatures reject concurrent
same-count edits between pages. All exports load the full filtered history in one
server request, independent of JSON pagination.

Frontend reads are abortable. Account, role or permission changes remount the
training view and discard old report state. Changed filters mask obsolete rows
immediately; late responses cannot restore data or create export URLs. Server
401/403 during preparation removes the selected report and prepared files.

## Export behavior

`GET /v2/training/report-employees` accepts `date_from` and `date_to`.
`GET /v2/training/reports/{employee}/export` accepts `format=pdf|png` plus the
same date/evaluator/keyword/rating filters as the existing report endpoint.
Every request rechecks identity and permission. Responses are `no-store`.
Rendering happens after the business database connection has been released.

PDF is portrait A4 with 40-point horizontal margins, embedded Vietnamese fonts,
headers, footers and continuation pages. Every note and record is preserved.
PNG renders the same full page layout, concatenated vertically. It rejects output
over 36 million pixels or 30,000 pixels high with a clear 413 response advising a
smaller date range or PDF, rather than clipping records or exhausting memory.

The modal offers explicit prepare, view, download and native share actions for
both formats. Native share starts only from the user's click after files are
ready. Cancellation performs no fallback download; the user chooses the app and
recipient. Object URLs are revoked on dismissal/scope changes. No production
report was exported during implementation.

## Verification

- Full Node regressions: 797 passed. ESLint: no errors (one pre-existing
  AppearanceSettingsPage hook warning). Production build passed.
- Full offline Python suite with a synthetic isolated PostgreSQL instance:
  4,266 passed, with no skipped tests. Focused training tests were rerun after
  final rendering/review fixes.
- Focused route tests cover authentication/feature revocation, role scope, actual
  employee records, date bounds, leap months, stable aggregates and full exports.
- Render tests check A4 dimensions, Vietnamese fonts, missing scores, every
  trailing record/long note, PNG allocation bounds and SQL/DTO parity.
- Synthetic multi-page PDF and full PNG pixels were inspected; seven-criterion
  charts, radar, text wrapping, margins and continuation pages were verified.
- Desktop/mobile CSS and DOM regressions pass. Browser geometry screenshots
  could not be verified here: local Chromium cannot create its required UNIX
  socket, and the cloud browser cannot reach the isolated preview server. This
  limitation is distinct from the completed PDF/PNG pixel inspection.

No business data, ratings, existing permissions, production services or FaceID
operations were changed. Backend deployment is needed for the new read/export
routes; publication of this draft does not authorize merge or deployment.

## Reference-template follow-up

The subsequent PDF-only card template, employee-specific filenames, removed helper
lines and all-time no-record roster are documented in
[the template and roster follow-up](training-report-template-roster-2026-10-10.md).
The original verification counts above describe the earlier implementation.
