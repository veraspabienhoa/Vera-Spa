# Attendance summary-card filters

The four cards on **Chấm công nhân viên** now filter the existing attendance
table. The first card restores all records. Selecting an already-selected group
also restores all records; **Bỏ lọc** resets the group and employee/department/shift
searches while retaining the selected date range.

The predicates retain the previous card-count definitions:

- **Bản ghi chấm công:** every row in the authorized date/search result.
- **Đủ cặp nghỉ giữa ca:** both break-out and break-in, without a restriction.
- **Vi phạm nghỉ / ra ngoài:** a restricted row with break-out, a positive existing
  excess/return-late duration, or an open break past its return deadline.
- **Đang nghỉ / thiếu FaceID vào lại:** unrestricted, break-enabled rows missing
  either side of a break pair, including a not-yet-started break.

Groups intentionally overlap. Their meaning is unchanged; they are not a new
penalty-eligibility calculation or evidence that a financial penalty is missing.
Counts use the entire current date/search result, not the selected subset. There
is no pagination on this table. Card clicks filter locally without new network or
device requests; the existing clock updates open-break counts and rows together.
Naive/fallback return deadlines use Vietnam time; offset-bearing timestamps keep
their supplied offset. Calendar displays touched here use dd-mm-yyyy.

Each card is a native button with a selected state, table association and visible
keyboard focus. The existing two-column mobile/four-column desktop grid remains.
Selection survives ordinary refresh and date/search changes. Account or permission
scope changes reset the component, cancel old reads/downloads and drop old data.
New query results are protected from slow earlier requests; exports are disabled
until the active query has loaded and pending search edits have applied. Changing
filters while an export is pending cancels that download.

Excel uses the existing fresh server-read contract and existing export permission.
The validated `summary_filter` parameter accepts `all`, `breaks`, `over` or
`incomplete`, applied after existing date/name/department/shift filtering. Export
predicates match the card predicates, but records/time may have changed since the
browser load. The export tooltip describes data at export time. The JSON snapshot
still returns the full scoped result, and workbook columns remain unchanged.

No attendance source, shift, penalty, financial record, department switch,
permission grant or Phase 3 setting is changed. No production data was read or
written to implement or test this feature.

## Verification

Regression coverage includes all four groups and overlap, deadline boundaries and
Vietnam parsing, native button semantics/focus, rapid/repeated selection, scoped
counts, zero matches, date/search/reset composition, filtered XLSX contents,
export permission denials, invalid-filter rejection, stale reads and stale private
downloads. The normal full Node/Python checks, lint and build apply to this change.

JSDOM tests do not establish native iPhone rendering or actual keyboard/touch
behavior. No real-browser visual check was run for this change; the deployed UI
still needs that verification. Deployment and production operation are not
verified by local tests or a draft pull request.
