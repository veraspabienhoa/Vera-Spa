# HC payroll sources and permitted lateness · 11-10-2026

## User-approved behavior

- Each eligible administrative employee has one persisted salary source: **Thống kê** (VERA daily schedules) or **Chấm công** (verified attendance against VERA schedules). The complete eligible roster gets source controls immediately. Missing legacy values continue to mean Thống kê. Source-only changes preserve inherited rate settings; they do not create explicit zero/default rate overrides. A mixed roster is calculated in one action.
- Time arriving late is unpaid in either source. For an evidenced HC late violation, permitted lateness reduces pay by that unpaid wage only; unpermitted lateness also adds one equal wage-based fine. The total reduction is therefore 1× or 2× respectively.
- The **Đi trễ có phép** checkbox is limited to genuine HC late events with the immutable default 2× wage basis. It cannot authorize a missing punch, early departure, absence, technician penalty, unrelated fine or customized fixed/multiplier policy.

## Evidence and historical safety

The original late event, intervals, wage configuration and amount remain unchanged. An Admin's approval is stored separately with actor, time and before/after audit history. Stale updates are rejected. Automatic event deduplication preserves the saved approval. Changes are refused when that employee/month already has finalized payroll.

Payroll keeps the selected source, pricing basis and evidence in its calculation snapshot. A source change requires saving employee configuration and recalculating a draft. Client-selected source, employee, month, rates or payable-time metadata must not become financial authority. Missing attendance or required schedule/rate configuration leaves payable amounts unavailable and blocks completion, export and sending.

The unpaid late component and additional fine are separate. Only evidenced intervals for the same employee, event and month may prevent a duplicate deduction. No historical financial records are backfilled, recalculated or edited merely by deploying this change. Existing finalized snapshots remain historical records.

The violation ledger labels its recalculated amount **Mức theo đơn giá ghi nhận**. Its checkbox and total use the immutable recorded event basis. Payroll separately displays actual unpaid late wages and the additional fine under that payroll row's entitlement; a later rate change or probation percentage must not silently rewrite the original event. Frozen financial exports retain their values, while email recipients are resolved from the current employee directory before sending.

Payable-time calculation keeps exact seconds separately from rounded display hours. Lateness uses the actual salary entitlement of the payroll row, including the existing probation treatment. The original event amount remains auditable rather than forcing an additional permitted-late fine into a row with a different entitlement.

## Schedule and access behavior

HR department assignment is independent of account role. Existing Quản lý/Lễ tân/Locker/Tạp vụ schedule grants retain their scope. Additional active hourly/monthly HC departments require the new `work_schedule_hc` grant, default off for non-Admin accounts. This source change does not grant any live account permission.

New HC departments use explicit daily start/end times and explicit overtime ranges. No default working times or pay rates are invented. Existing named shift definitions and default hours remain unchanged. Schedule writes validate the employee's HR department under the HR registry lock, and keep the existing per-cell revision safeguards.

Clock-only custom overtime retains the authoritative attendance-window interpretation. Main Ca 2 ending at 01:00 plus overtime 01:00–03:00 is a next-day continuation. Morning overtime 08:00–10:00 before main Ca 2 stays on the same schedule date. A gapped 01:00–03:00 after a main shift ending at 00:30 is ambiguous without a date field and keeps the existing same-day interpretation; this release does not invent a new day-offset rule. Payroll, attendance and HC fines must use matching geometry.

HC FaceGate projection retains a valid final punch, including overnight checkout, for eligible HR staff. Technician, leader and Admin checkout policy remains unchanged even if an HR department is reassigned. Device mappings, evidence readiness, timezone rules and caller-owned database connections remain authoritative.

## UI and release boundaries

Month, account, permission, view version and unmount changes invalidate asynchronous payroll operations and pending confirmations. Stale calculation/draft/save/export results must not populate a newer month or download a stale financial document. Additional HC schedule data is scoped to the active identity and permissions.

Employee configuration, department configuration and mutable payroll records use revision checks. Old tabs without the required revision must reload before editing. A canonical employee rename migrates source/rate map keys atomically and rejects occupied target keys rather than inheriting another identity's configuration.

The frontend checks the HC payroll contract and uses versioned endpoints for financial operations. An older backend cannot accept those new paths, including when a previously loaded browser encounters an old instance during rollback. Unsupported instances show an update-required state and do not fall back to legacy writes. Late approval has its own new endpoint and capability check. Old clients calling the new backend without required revisions fail closed.

Main pushes with these changed files trigger the existing GitHub Pages frontend deployment and CI. They do not match the existing automatic Live Tour watchdog/backend deployment paths. VPS backend deployment remains a separate manual workflow. A frontend/backend mixed-version interval therefore remains read-only for the new payroll operations until the server contract is available. This document does not authorize deployment or activation.

Monthly wages keep the established 26-day denominator; unrelated allowance and overtime policies are unchanged. This change does not introduce a new future-month finalization rule.

Phase 3 activation remains paused. Verification uses synthetic data and disposable local PostgreSQL only; no production payroll calculations, settings changes or violation approvals are part of implementation testing.

## Verification scope

Regression coverage includes mixed-source batching; source-only settings; stale configuration/draft/history writes; same-event late evidence; exact-second and multi-event rounding; probation and changed wage rates; finalized snapshots; current email routing; employee renames; HR schedule membership; missing rate/schedule evidence; overnight checkout and rate segmentation; account/month/permission changes; pending-write ordering; scoped exports; and mixed-version frontend/backend behavior.

The supplied reference screenshot was inspected for checkbox placement. Automated UI checks mount the real React components with synthetic responses. A local headless Chromium attempt could not start because this environment denied its singleton socket, so these checks do not establish rendered-device or live-production visual behavior.

### Checked release-candidate results

- Full offline Python suite with disposable PostgreSQL 16: **4,678 passed**.
- Full Node regression suite: **927 passed**.
- Frontend lint: **0 errors**, with one existing unrelated React-hook warning in `AppearanceSettingsPage.jsx`.
- Production frontend build: **passed**.
- Compilation of all **262** top-level Python files, the **18** CI inline Python check groups, and staged whitespace checks: **passed**.
- Independent financial and UI/access reviews, including mixed-version rollback and current-ledger email reference labels: **no remaining blockers**.

These are local candidate results, not a claim about a deployed instance. GitHub CI and the exact published tree must still be checked before merge.
