# Leave quota controls, notification month and deployment follow-up

## Confirmed causes

- The personal-list statistics widget read its dates by parsing the first
  heading paragraph. Adding the active-month heading displaced the date-range
  paragraph, leaving its context empty and the quota button disabled.
- The quota monitor scanned all report months and re-enqueued active historical
  alerts. A new notification creation date did not imply a current report month.
- Deploy VPS Production #543 passed deployment, active-release and schema checks,
  then failed at the new timer installer with `sudo: a password is required`.
  The final health gates did not run. This is not proof that the whole API failed.

## Changes

The list publishes its ISO date range and employee filter through explicit data
attributes. Its statistics and quota control observe those values, independent
of translated or hidden headings. The requested month/date summary, registration
autosave note and violation-catalog note are removed; filter controls, autosave,
quota permissions, loading/error states and business checks remain.

Automatic quota alerts cover only the current month in Asia/Ho_Chi_Minh. Manual
quota checks still report the selected month/range. Historical leave required to
calculate previously borrowed allowances remains part of that calculation.
Routed notifications carry a structured quota month. Inbox, popup, details and
push delivery check the month again. Legacy messages with an ISO month in their
body are filtered too, without deleting business leave records or notifications
from other families.

Cleanup now runs through a lifecycle-managed background worker in the existing
API service. It starts checking after 30 seconds and repeats every five minutes;
the persisted Admin interval and separate database lock control whether cleanup
actually runs. Multiple workers, service restarts and optional manual checks
share the same due check. Shutdown signals the worker to stop. The deployment
workflow performs a due-checked pass without invoking a privileged installer or
changing sudo permissions. Existing active-release/schema and final health gates
remain required.

## Validation and rollout

Component tests reproduce the disabled-button regression, exercise hidden and
changed headings, changing months, request retry and permission visibility.
PostgreSQL tests verify current-month alert activation and legacy/current/future
message filtering; worker tests cover lifecycle and retry. The full CI must pass
before merge. After merge, start a new Deploy VPS Production run on current main;
rerunning #543 would use the old workflow/commit. Confirm both health gates, the
Admin cleanup status, and quota checking in the browser after deployment.

This record distinguishes verified code/runtime-log causes from production
verification that still requires the corrected release to be deployed.
