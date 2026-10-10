# Live Tour date access: API contract and rollout

This is a source-only permission feature. It does not change production account
grants, rewrite financial records, migrate stored histories, or authorize a
deployment. See [catalog v1](live-tour-date-permission-catalog-v1.md) for the
account/role inheritance and save protocol.

## Date selection versus row visibility

The eight grants identify selectable capabilities, not disjoint sets of dates.
An explicit `today` denial prevents choosing `preset=today`; a granted `month`
still includes today's rows. A bounded request without a named preset may narrow
the union of granted finite ranges, but may not cross an uncovered gap. Omitting
both preset and dates requires `all` on an ordinary list/export endpoint.

- The API derives Today/Yesterday, Monday–Sunday weeks and complete calendar
  months from the trusted Vietnam calendar clock, not browser timestamps or the
  operational counter rollover.
- Named finite presets require that exact grant. Missing dates use their
  canonical range; supplied dates can only narrow it. An exact `date` must also
  lie inside the authorized range.
- `custom` requires its own grant and both valid, ordered ISO dates. Multi-year
  bounded ranges remain supported. A custom grant alone does not authorize an
  implicit unbounded full-state or customer-history response.
- Invalid/partial/reversed custom dates produce 400. Unsupported preset names
  produce 400. Denied capabilities or ranges produce 403 before ledger reading.
  Date-policy 403 responses carry current capabilities for safe UI recovery.
- No available date choice yields empty protected ledgers in aggregate reads
  and 403 on direct section list/export requests.

The capability response is `date_filters: {version: 1, server_today, sections}`,
where each section contains the exact granted preset strings. Hyphenated preset
names (`last-week`, `last-month`) correspond to underscore permission IDs.

## Read surfaces

| Surface | Date scope |
| --- | --- |
| Pending invoice list / pending Excel | `pending` |
| Paid invoice list / paid Excel / nested receipt | `invoices` |
| Report lists, report totals, revenue/TIP/employee/performance exports | `reports` |
| Customer-count PDF and PNG | `reports` |
| Reports-page board snapshot history and its Excel | `reports` |
| Live Tour audit, break history, change history and backup metadata | `history` |
| Customer history | Independent pending/invoices/reports coverage |
| Customer-detail workbook | Same selected range authorized in all three ledgers |

Report revenue values can use invoice source records internally without granting
receipt access. Nested receipt payloads still require the independent paid
invoice read/date scope. Board snapshot history in Reports is distinct from the
Live Tour History & backups panel. Existing parent-read requirements remain
route-specific; date grants never create a missing read grant.

Full/board responses and mutation response payloads use detached, date-filtered
public views. Customer/combo reservation calculations retain every outstanding
draft in their original internal snapshot. Payment, booking, invoice correction,
restore and other mutation authorization and date rules are unchanged. A
successful payment can return a receipt marked date-restricted rather than
exposing a forbidden invoice. Retry receipts are filtered with current grants.
Personal employee TIP self-service and current operational board rows retain
their separate existing authorization.

Historical before/after snapshots and backup invoice numbers obey the source
ledger's independent dates. Sanitization precedes history search/count filters
so hidden invoice numbers cannot become count probes. Financial audit detail
without unrestricted source coverage is conservatively redacted. Internal
snapshots, reservation arithmetic and persisted audit records are not modified.

Indexed primary lists retain server-side canonical ranges and pagination. When
history indexes contain restricted nested fields, or report totals depend on a
restricted secondary ledger, the existing detached fallback filters first and
then calculates counts/totals/pages. This avoids exposing pre-filter counts.

## Browser behavior and revocation

Only granted presets are shown. Arbitrary date entry requires custom access;
server authorization additionally protects direct URLs/manual query requests.
Invalidated selections choose an authorized fallback. Paid invoices prefer
Today when it is available. Persisted date selections are account- and
section-scoped; saved preferences contain no customer searches.

Verified account/policy changes invalidate obsolete readers, cached protected
rows, copied read dialogs and export requests. Responses from canceled scopes
cannot repopulate the UI. Persisted board caches have protected content and
capabilities removed until a fresh server read. An unchanged business revision
still returns fresh date capabilities, so permission changes do not wait for a
financial mutation.

## Release order and limits

The new backend must be deployed before date restrictions can be relied upon.
The frontend may be delivered automatically before a separately deployed
backend; the Admin editor exposes v1 controls only with a v1 catalog and verifies
the version on save. An old backend cannot confirm a successful v1 permission
save. A new backend preserves absent legacy date flags and older tabs' unrelated
permission saves; old list requests remain valid inside their authorized scope.

After backend and frontend deployment, reload old tabs and verify an explicitly
restricted test account across list, report, history and export surfaces before
relying on the production policy. Previously downloaded content cannot be
revoked. No source test establishes that the running production release has
changed, and this branch performs no actual account permission edits.

## Verification

Tests use synthetic accounts, dates and ledger rows. Coverage includes all 32
choices, every role, explicit account/role denials, safe old-client saves, Vietnam
date boundaries, custom ranges, direct endpoints, nested data, exports, totals,
indexed PostgreSQL/fallback parity, request cancellation and account isolation.
The final PR records exact full-suite and independent-review results.
