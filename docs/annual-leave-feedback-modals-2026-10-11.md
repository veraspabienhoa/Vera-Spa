# Annual-leave feedback modals

The Phép năm route shares two components across roles: the Admin pending-request
panel and the request/approved-list section. All operation feedback now uses the
existing shared system-dialog manager with a Đóng button, keyboard dismissal,
focus restoration, queued notices and the existing responsive scrollable layout.

Coverage inventory:

- Admin pending-list and overlap-overview load failures.
- Read-only annual-request overlap checks: no overlap, overlapping employees,
  complete daily counts/request lists, network errors and HTTP errors.
- Explicit overview checks: results, thresholds, invalid dates and failures.
- Approve/reject validation, unchanged confirmation choices, success and errors.
- Employee annual-leave, beauty-leave and resignation submission, server warnings,
  missing/invalid fields, success and errors.
- Approved-request edits, cancellation prompts, return-to-work validation and
  confirmation, legacy-sync errors/pending warnings and success.

Existing employee/role/permission gates remain enforced. Read-only dashboard
counts, eligibility/pause descriptions, heatmap/card status, loading indicators,
empty lists and form help remain persistent page data rather than notifications.
Success feedback no longer opens a separate custom success dialog. Invalid form
feedback is owned by this page, so navigation/account changes remove it too.
Existing configured feedback-category routing is preserved without routing new
read-only check results or duplicating confirmations and validation notices.

Repeated actions are guarded before awaiting a decision or request. Account and
permission changes clear owned queued/visible dialogs and abort old requests;
late responses cannot display another user's data or trigger a stale session
refresh. Failed writes keep editable drafts. Closing feedback does not approve,
reject, cancel or otherwise change the request. Cancellation still needs the
existing explicit prompt/confirmation choices.

Mounted regressions use actual components, API transport and shared dialogs with
isolated synthetic responses. They cover modal feedback, long safe-text lists,
Close/Escape/Back, repeated clicks, retry/error retention, both role variants,
partial date drafts and account/permission/session races. Existing direct
notification navigation and annual-request date-range tests remain in place.
No production business data, notification-read state or Phase 3 settings are
changed by this source patch.
