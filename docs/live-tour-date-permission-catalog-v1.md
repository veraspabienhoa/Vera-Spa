# Live Tour date permission catalog, policy v1

Source-only change. No account data, role configuration or production service is
modified automatically. The API publishes `date_filter_policy_version: 1` and
`date_filter_legacy_inheritance: effective_section_read`. A subsequent authorized
Admin save records the policy version alongside the canonical permission payload.

## Independent settings

Each of `pending`, `invoices`, `reports` and `history` has eight separately
configurable IDs: `live_tour_<section>_date_<preset>`. The presets are `all`
(Tất cả), `today` (Hôm nay), `yesterday` (Hôm qua), `week` (Tuần này),
`last_week` (Tuần trước), `month` (Tháng này), `last_month` (Tháng trước), and
`custom` (Tùy chỉnh). Role and account settings use the existing override store.

The date flag resolves as Admin → explicit account value → explicit role value →
existing effective section read permission. Both explicit true and explicit
false matter. A missing flag does not become false merely because policy v1 was
installed. An explicit false keeps that named preset disabled. Its calendar dates
may still be included in a different granted preset: for example, a granted
month can include today's rows even when the named Today preset is disabled.
`custom` permits explicitly selected broader dates; it is an independent grant.

For non-Admin accounts, the following effective read permissions always bound
date grants, including explicit true grants:

- Pending: `live_tour_pending_view` and `live_tour_invoice_view`
- Paid invoices: `live_tour_paid_invoice_view`
- Reports: `live_tour_reports_view`
- History: either `live_tour_history_view` or `live_tour_backup`

The history alternative preserves the pre-existing backup-metadata reader. It
does not grant history/audit access. Audit and invoice/customer detail redaction
retain their independent checks. Likewise direct exports and standalone Reports
retain section-only access; board and collection routes still enforce their
existing `live_tour_view` requirement. Date grants do not change unrelated
permission precedence or runtime dependencies.

## Admin editor and saving

The editor displays effective inherited checks on its first load. Its
`preserve_unchanged: true` save requires `expected_revision`, compares the
submitted selection with the fresh canonical effective snapshot under the
existing transaction lock, and adds prerequisite reads only for newly enabled
permissions. This prevents an unchanged or unrelated save from lifting an older
explicit view denial. Date prerequisites are already complete, so a new date
selection does not silently add the board grant. Minimal read parents visibly
added by that date selection are not re-expanded as separate action roots during
save. Existing unrelated dependency
expansion remains in place for explicitly enabling unrelated actions.

All eight date checks can be explicitly disabled for a section. Returning an
account to role inheritance removes its overrides and uses the actual current
role defaults. Concurrent stale saves fail with 409 before writing. History date
controls require a selected History or Backup read; choosing a date never
auto-grants audit read to a backup-only account.

The new editor sends `date_filter_policy_version: 1` even when all date checks
are false. A request with explicit date IDs also opts in to the date catalog.
An older client sending neither the version nor date IDs preserves the target's
existing date rows, including missing rows that still inherit. This prevents a
pre-feature tab's unrelated save from fabricating blanket date denials. Resetting
an account to role inheritance still removes every account override.

The API exposes the date feature labels, preset labels, section labels, all-parent
dependencies and any-parent alternatives for clients. `allowed_features` accepts
up to 1,000 registered features, avoiding future catalog growth exceeding the
previous 200-feature request limit. Unknown feature IDs remain rejected.

## Mixed-version rollout safeguard

Deploy the backend policy enforcement and catalog before exposing date controls
in the new frontend. The editor displays date controls only when its loaded
catalog advertises numeric `date_filter_policy_version: 1`. A new frontend with
an old catalog hides these controls and sends no date-policy version request.
An old frontend talking to a new backend keeps its existing date rows unchanged
when it sends neither date IDs nor a policy version, as described above.

The new backend includes `date_filter_policy_version: 1` in permission-save
responses. The new editor verifies that acknowledgement and a refreshed v1
catalog at or beyond the saved revision before reporting date-policy success.
If a cached v1 catalog is followed by an old backend that silently ignores the
new request fields, its generic success response is insufficient: the editor
reports that the date restrictions could not be verified. Missing read-back,
a downgraded catalog, or an older returned revision also produces a verification
warning rather than success. The warning acknowledges that a write may have
occurred; it does not automatically retry a potentially successful save.

Do not claim date restrictions are enforced while requests can reach old backend
instances: old servers do not implement the read guards. Complete backend rollout
and verify the catalog/save version plus the denied read/export behavior before
Admin starts relying on restrictions. This source change does not deploy or
perform production verification.

## Regression checks

- `tests/test_live_tour_date_permission_catalog.py`: every role/section/preset,
  account and role overrides, read denial precedence, compatibility exceptions,
  no-change saves, explicit all-false, account reset and stale revision handling
- `web-v2/tests/permissionCatalog.test.mjs`: effective Admin checkbox state,
  independent overrides, all-false/reset and backup-only/section-only access
- Existing dependency-closure, page-catalog and canonical PostgreSQL save tests

These tests use synthetic identities and permission payloads. They do not mutate
production or establish production deployment/readback success.
