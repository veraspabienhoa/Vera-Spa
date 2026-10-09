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
