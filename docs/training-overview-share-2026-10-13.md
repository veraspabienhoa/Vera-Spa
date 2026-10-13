## Follow-up: selected date range and one-row controls

The latest change supersedes the original all-time export behavior below:
PDF/PNG now use the selected training dates (all employees, ignoring the name
search). Headers show From/To dates in dd-mm-yyyy. All-time selection resolves
to the earliest/latest authorized record, or today when there are no records.
The untrained roster remains an all-time fact for department nhanvien. Employee,
time preset and share button occupy the same grid row, including mobile.

# Whole-roster training progress sharing

The progress tab has a share button aligned right below the filters. Its modal
prepares PDF and PNG for the full authorized active roster across all time,
independent of either name filter or selected dates. Existing employee-specific
reports retain their filters.

`GET /v2/training/progress-export?format=pdf|png` checks the verified identity and
`training_view`, reuses the established role-pair roster and HR department codes,
and reads daily sessions and submitted evaluations in two bound bulk queries.
It does not use the bootstrap's 300-row limit. No writes or schema changes occur.
Rendering happens after releasing the business connection. Files are no-store.

Bars share one hours scale. Sum each valid positive same-day start/end interval
in seconds before converting to hours; missing/invalid intervals are explicitly
flagged and excluded. An evaluation-only employee has zero training hours.
Under each bar: employee name, then training topics, recorded feedback, grade
counts and per-criterion means of submitted assessments. Missing scores are not
zeroes. Repeated text is deduplicated; long text continues across PDF pages.
The bottom three-column table contains only active `nhanvien` employees without
any training or submitted evaluation in all time, using the same read result.

PDF/PNG use the existing Vietnamese-font drawing engine, with the same pixel
allocation guard for PNG. Oversized PNG responds 413 rather than clipping;
PDF remains available. Prepared files can be viewed/downloaded. Native file
sharing is invoked only by a user click, then the user chooses Zalo and recipient.
No forced Zalo routing or automatic sending is claimed. Unsupported browsers
show download-and-attach guidance. Dismissal, scope changes and denied access
remove prepared URLs; aborted/late requests cannot restore them.

Verification: 38 backend route/render tests and 15 training UI tests passed;
production build and lint passed (one existing AppearanceSettingsPage warning).
Synthetic short/long Vietnamese PDFs and PNG were visually inspected. No real
employee report was exported, no Zalo message sent, and no VPS deployment done.
