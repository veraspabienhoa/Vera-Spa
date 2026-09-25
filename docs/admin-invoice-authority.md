# Admin invoice corrections

User requirement, 25-09-2026: the authenticated `admin` role can edit or void
invoices of any age. This applies to pending, paid and report invoice actions.
The pending today/yesterday gate and paid same-day void gate apply only to
non-admin identities. A correction reason is optional for admin; an omitted
reason receives a clear system description in the audit record.

The API derives authority from the authenticated identity and passes it as a
server-only function argument. An account named `admin`, delegated feature
permissions, or client payload flags do not grant this authority. Existing
feature grants continue to control non-admin access.

Admin can also void the sale invoice of a used or reserved combo. This reverses
that invoice's revenue and TIP while retaining the entitlement ledger, existing
redemptions and active bookings. The retained purchase has price zero and records
who voided its sale and when. Original price and balances remain in invoice
change history. Entitlements may be adjusted separately through the existing
admin combo tools. Unused, unreserved purchases are removed as before. Voiding a
redemption still restores the exact original component debits.

This changes business authority, not the invoice data format: correction forms
retain their supported fields. Authentication, valid money/date values,
ledger-consistency checks, resource locking, revision checks, idempotency and
atomic writes remain in place. Audit records retain the original invoice,
reports, combo usage, purchase balances, actor and server time.

Regression coverage: old paid/pending/report invoices, absent reason, non-admin
date/reason gates, spoofed authority, combo reservations/redemptions, replay,
rollback in PostgreSQL, and admin/non-admin dialog submission.
