# Live Tour operation read review — 25-09-2026

## Confirmed code costs

Checkout already supported a partial snapshot, but board mutations and paid-invoice
corrections still loaded every persisted replay receipt and historical collection.
Lock discovery loaded all invoices even when no invoice ID was involved. The
projection worker also read/copy-compared the financial ledger and receipts while
holding its exclusive fence. A board-only action response then read the entire
ledger again after commit, before reducing it to a board response.

Staff Excel export read the directory twice, selected portrait binary data, decoded
and resized every image, then embedded them for another workbook styling pass.

## Changes

- Certified booking/start/finish/employee/pending operations use operational rows,
  existing break events and only the requested replay receipt. Historical audit
  and pending changes are appended under the existing publication row lock.
- Projection uses that operational read set without replay receipts. Original
  connection reuse, attendance rules, queue leases and exclusive fence remain.
- Paid-invoice corrections omit historical receipts/audit/change snapshots, while
  retaining invoices, reports, combo usage, customers and open reservations required
  for correction/refund validation. Adjustment history remains append-only.
- Other compact actions retain their full business read set but select only their
  own receipt. Unknown action types do not get a reduced business read profile.
- Only actions with no invoice ID omit invoices from resource-lock discovery.
- Board responses reread board collections; corrections return a committed receipt
  before the browser refreshes its board and active financial panel separately.
- Metadata revision and configuration revision publish in one SQL update. Projection
  does not rebuild the receipt JSON object when it has no receipt changes.
- Customer/catalog/tip views read their relevant collections. Export files contain
  employee data only, with no photo column, image query, decoder or embedded media.
- The floating Live Tour action popup is removed. Progress stays on the page;
  failures remain visible in forms, and a successful payment still opens its receipt.

## Integrity and limits

Resource locking, actor/payload replay checks, protected financial receipts,
canonical replay responses, permissions and atomic rollback are retained. Partial
snapshots reject writes outside their certified collection sets. Append ordinals
are allocated after publication locking so concurrent writers cannot lose history.
Full readers, legacy storage, backup/restore and financial rules retain their paths.

The existing rule only permits deleting an invoice in the current business-date
field used by invoice validation; this release does not authorize historical voids.
A client timeout is still an unknown outcome until its persisted result is checked.

This is not constant-time processing: invoice corrections still read financial
rows to validate linked usage; protected receipt JSON and metadata publication can
grow with financial history. A separate indexed receipt table would require a
transactional migration and compatibility plan. Customer-history/full exports also
remain explicit heavier reads. No production speed multiplier is claimed.

## Verification

PostgreSQL regressions cover compact operations, current-day corrections, historical
delete rejection, canonical replay, omitted-history preservation, audit retention,
parallel unrelated writes, invalid partial writes, projection and forced rollback.
Excel checks inspect the workbook ZIP after styling to verify no media/drawings and
exercise the endpoint without any image SQL. Existing payment, permission, auth,
attendance, notification, UI and deployment health gates remain enabled.

CI and deployment results belong in the PR/deployment record. Passing tests and
health checks alone do not establish cashier latency or completion of a real sale.
