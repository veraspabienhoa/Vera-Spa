# Report capture, date ranges and service performance

Employee service/TIP capture now draws the existing filtered/sorted chart directly
onto canvas. It uses no SVG foreignObject or external image/font resources.
TIP amounts marked snapshot-ignore remain excluded. Clipboard starts in the
original click; rendering failures remain errors rather than silent downloads.

Training controls share one row. Exports carry date_from/date_to, and show actual
From/To bounds instead of the old all-time scope text. Daily and submitted
assessment dates use existing business-date semantics. Untrained remains all-time.

Performance records preserve authenticated start and completion actors through
pending and paid invoices, restart, replacement, and room/batch actions. Old
records remain blank. Desktop tables wrap within their width; mobile shows all
fields as two-column record cards, without a horizontal scrolling table.

`/v2/live-tour/report-share?kind=performance&format=pdf|png` uses the same detached,
fully filtered ledger, export permission, Admin restriction and date-policy checks
as Excel. It ignores UI pagination. Output compares standard/actual minutes and
includes dates, result and both actors. PDF is A4 with 40pt margins and continuation
pages; PNG keeps the existing allocation bounds. Files are no-store. User-triggered
native sharing allows choosing Zalo; unsupported devices use download/attachment.
No automatic external sharing occurs.

Early completion notices use the displayed rounded completion_delta_minutes <= -5.
One stable event per completed service prevents batch/retry duplicates. The existing
transactional outbox supplies in_app, popup and push, for admin/quanly/letan and the
exact service employee. Delivery rechecks active account, source/channel switches
and current audience. Actual lock-screen receipt requires push permission/device
subscription. No new penalty or financial record is created.

Validation uses synthetic records, boundary/retry/audience tests, report export
permission and filter tests, UI file lifecycle tests and rendered Vietnamese PDF/
PNG inspection. PostgreSQL outbox integration is assigned to CI's isolated service;
local runtime has no configured PostgreSQL fixture. No VPS deployment or real Zalo
send was performed; native mobile geometry/device push remain unverified here.
