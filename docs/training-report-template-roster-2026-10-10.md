# Training report template, filenames and no-record roster (10-10-2026)

## Requested changes

- PDF follows the supplied reference: daily journal table, dated training and
  evaluation history cards, paired skill-progress/latest-radar cards, and the
  evaluation chart. Pale-gold gutters, rounded white cards and Vietnamese text
  are drawn as a real A4 document, with table/card continuations on longer data.
- PNG keeps its previous complete paginated drawing layout. Both formats now
  use the employee's existing report display name, for example
  `Thảo Linh_VERA_DaoTao.pdf` and `Thảo Linh_VERA_DaoTao.png`.
- The two requested roster instruction/filter-explanation lines are removed.
  Day, month, custom dates, employee search and report actions remain available.
- A read-only table at the bottom lists active authorized employees without any
  recorded daily training or submitted evaluation, across all time.

## Scope and filename safety

The top roster still applies the selected report dates. The bottom roster is the
all-time complement of the same active, role-authorized employee catalog; it does
not infer a person's real-world training history. Its concise caption makes the
no-record/all-time meaning explicit. A submitted evaluation excludes a person
from the no-record table even without a daily training log. Draft or cancelled
assignments without submitted results do not. Existing daily-log status semantics
are unchanged. Someone trained outside the selected dates is never put in the
no-record table simply because that period is empty.

Both tables share the existing name search. Bottom rows cannot create training,
assignments or reports. Existing verified identity, `training_view`, role-pair
checks, inactive/deleted exclusion and stale-account cancellation remain in place.
No feature grants, self access, database schema or business records are changed.

The backend uses the existing report display name and sends a percent-encoded
RFC 5987 `filename*`; a static ASCII fallback keeps headers safe. The frontend
retains that validated filename in the prepared File used by view, download and
native share, with the same display-name fallback. Vietnamese Unicode is NFC
normalized and preserved. Path characters and controls are replaced; the name
prefix is bounded to 200 UTF-8 bytes without splitting a character. Authentication,
abort/revocation handling, share cancellation and object-URL disposal are retained.

## Verification

- Full offline Python suite with isolated PostgreSQL: 4,280 passed, zero skipped.
- Full Node suite: 799 passed; focused UI/transport checks: 14 passed.
- ESLint passed with zero errors and one pre-existing AppearanceSettingsPage hook
  warning. Production build and changed-module Python compilation passed.
- Independent final review found no blockers; 56 focused route/export/template
  tests passed. Eighteen final PDF pages were visually inspected.
- Representative, long-note and empty PNG bytes match the verified base exactly.


Focused tests cover date-filter-independent no-record membership, submitted-only
and draft/cancelled evaluations, role-pair/active/deleted constraints, read-only
SQL, real PostgreSQL dates, Vietnamese filenames, unsafe names and header parsing,
transport/filter identity, full-report pagination, file sharing and cancellation.

The PDF renderer is verified with a reference-like two-session document, a
populated evaluation/radar document and a long-note multipage stress document.
Actual pages are rendered with Poppler and visually inspected; tests also check
A4 dimensions, embedded Vietnamese fonts, bounds, missing-score gaps and trailing
content. The PNG renderer keeps its original full-record and allocation checks.

Chromium UI screenshot verification remains unavailable in this task container:
startup is blocked by denied UNIX socket creation. Synthetic DOM interaction tests
cover the requested UI and mobile-safe CSS structure; this is not a claim that a
real browser screenshot was verified.

No production reports were exported, no real training data was changed, and no
merge or deployment is authorized by this implementation.
