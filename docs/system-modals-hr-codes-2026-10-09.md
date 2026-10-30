# System notification modals and HR department codes

Source changes only; production deployment has not been performed.

Application feedback uses a shared styled modal on every Web V2 page, including
login and Live Tour. Existing inline feedback is presented once and hidden after
presentation; loading indicators, report rows and static help remain page content.
Native alerts, confirmations and prompts use asynchronous modal helpers. Await
the result before writes; cancel/Escape must never approve a destructive action.
Messages use text nodes, preserve line breaks and stay until acknowledged.

Passive notifications queue without the previous toast timeout or truncation.
Booking, missing check-in, attendance, birthday and profile reminders retain
permissions, channel settings, live contents, action callbacks and read semantics.
A confirmation/error can open above its calling notification. Keyboard handling
is limited to the top modal; dismissal restores focus and scrolling. Account
changes cancel pending decisions and clear notifications from the old session.
The layout editor must leave modal controls interactive.

An inactive HR department code can be created again. Only an active code conflicts
with create. Registry revision checks, the existing transaction lock, Admin-only
access, active-name uniqueness and occupied-department deletion guards remain.
Recreating restores the same code, accepts its new name/pay mode, and preserves
existing department settings, assignments, authorization roles and payroll history.
No data migration or deletion of financial history is required.

Validation covers queueing, safe confirmation/cancellation, prompt values, focus,
feedback replay, failed acknowledgements and restored custom/default HR codes.
The existing business fixtures drive the actual modal with their original yes/no
choices. Full PostgreSQL regression coverage runs in repository CI.

## Invoice action feedback (30-10-2026)

Pending and paid invoice edit/delete dialogs now show an acknowledged success
modal after a successful action response. The paid dialog is also shared by the
Reports menu, including service, TIP and combo invoices. Failed actions retain
the editor and use the existing shared error-feedback modal. Success does not
wait for report refresh and does not change financial calculation or permissions.
Dismissal controls follow submit controls in invoice form keyboard order and
retain the shared right-edge styling. System feedback defaults to “Đóng”; both
“Đóng” and “Close” are marked as dismissal controls.

Source validation: 22 invoice/system-dialog tests, targeted ESLint and production
frontend build passed. Production deployment and business operation verification
have not been performed.
