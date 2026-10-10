# Birthday menu: holiday leave — 09-10-2026

The holiday leave section appears below the birthday list. It supports all active
staff, one/multiple HR departments, or selected employees. Scope uses the saved
HR department assignment, independently of authorization role. System Admin
accounts and former/temporarily inactive employees are excluded; working/trial
staff remain eligible even if their login is locked.

Choose one full day, multiple individual dates, an inclusive day range, or an
exact date/time interval (including overnight). Visible dates use dd-mm-yyyy;
naive input times use Asia/Ho_Chi_Minh. Periods are half-open; whole-day end is
midnight after the last selected date. Adjacent dates merge; gaps are preserved.
A registration covers at most a 366-day window. The active cohort is snapshotted
when saving; later staff/department additions do not silently inherit the leave.
Member FKs follow canonical employee renames and detach on employee deletion.
Original member/department snapshots remain in the registration audit payload.

Birthday permissions include holiday_leave_register and holiday_leave_cancel.
Both depend on birthday; cancellation additionally depends on registration.
Admin has access; other roles default ungranted. Registered/cancellation users
can see cohort entries; other birthday users see only their own memberships,
with other employees redacted on the server. Cancellation is revision checked,
soft archived, and requires the distinct cancellation grant.

PostgreSQL is canonical. Registration uses a caller-owned transaction, fixed
advisory locks, idempotent request UUID/hash, and atomic overlap checking across
all selected employees. Duplicate requests cannot create extra memberships;
a retry cannot silently expand a previously captured cohort. No Google/device/
notification networking runs in the transaction. Read paths do not create schema.

The holiday resolver reuses the caller's connection. Live Tour's scheduled
projection shows Nghỉ lễ during the exact interval and does not finish services
or change counters, shifts, invoices or manual work status. Booking/start/change
operations refresh their action-owned employees directly from holiday records,
including future booked_at times, rather than trusting cached flags. A shared
holiday lock permits concurrent service operations while serializing registration
and cancellation; it precedes Live Tour resource locks. Admin outside-shift
privileges cannot bypass approved holidays. Expiry/cancellation restores the
underlying eligibility on the next operation/projection.

Attendance retains real scans and payable evidence, annotates holiday periods,
removes only approved lateness and suppresses missing-shift expectations when
the whole actual shift is covered. HC automatic missed-wage pricing excludes
holiday intervals, including hourly/overnight boundaries. KTV full/half absence
and check-in alerts use the existing conservative approved-leave policy: any
holiday registration that day defers an automatic absence decision for manual
review. Outside/break-return catalog penalties overlapping an approved interval
are also deferred, while unaffected intervals retain their existing rules.
Every holiday registration returns calculated_days=0 and displays Số ngày tính
as 0, for all scopes and day/hour modes. Registration/cancellation never writes
ordinary leave_records, so existing employee leave limits remain unchanged.
No holiday entry consumes ordinary/annual leave quotas, invents check-ins or
paid hours, recalculates stored payroll, or deletes prior violations. Holiday
wage entitlements are outside this registration change.

Local and CI tests cover scope resolution, permission revocation/privacy,
time intervals, exact boundaries, atomic overlap/rollback, idempotence,
cancellation, stable employee renames/reused names, future booking guards,
attendance and HC pricing. UI tests exercise confirmation, scope selection and
shared date/time inputs. Production has not been written or deployed for this
change; actual registration/cancellation needs read-back after deployment.

## 10-10-2026 — Separate day and clock selection

The form selects one day, several dates or an inclusive date range independently
from All day / From time to time. Clock windows repeat for each selected date.
10-10-2026 with 17:00:00 to 00:00:00 ends at midnight starting 11-10-2026.
An earlier end clock rolls into the next day; equal clocks are rejected (use All
day for a full day). Gaps between daily windows remain working time. Both clocks
are required, with second precision and Vietnam local time. Legacy absolute
hours requests and existing registrations remain readable. Stored timed periods
use mode hours for exact history display. Calculated leave days remain zero.
