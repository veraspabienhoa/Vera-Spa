# Checkout read scope and independent refresh

Checkout and quick checkout may request `response_view: receipt`. In active
relational storage, these operations read the operational catalog, employee,
customer and pending rows required by validation and combo reservations. Past
invoices and invoice changes contribute document-number headers only. Only the
requested idempotency receipt is decoded; other saved receipts remain in SQL.
Header count still grows with invoice history; this is a payload reduction,
not a claim of constant-time numbering.

Financial/resource locks, actor and payload checks, canonical prices, reserved
combo balances and transaction rollback are unchanged. Historical invoice
headers are read-only. New invoices, reports, combo usage and audit entries
append under the metadata publication lock. Audit retention trims oldest rows
without renumbering retained history. The invoice, employee/customer changes,
report and idempotency result commit together.

Receipt responses return after commit without reloading the full board. Retries
still read the current canonical invoice, including a missing/voided invoice,
instead of printing a superseded saved receipt. Existing full/board clients
remain compatible. The frontend refreshes the board independently and loads
financial panels only after selection; it pauses new detail reads during a save.

Inbox, popup and notification settings share an authenticated feed on one
visible-tab poller every 60 seconds. The training-notice poll is 60 seconds.
The last unsubscriber clears the shared cache; late responses from a prior
session cannot populate a new session. Hidden tabs do not poll. Network push
delivery is unchanged and remains outside business transactions. A 404-only
fallback supports rolling upgrades to the feed endpoint.

Regression coverage includes actual PostgreSQL commit/replay/rollback, duplicate
and voided invoice numbering, current receipt lookup, past-date quick checkout,
combo balance failure/replay, shared notification connection and client polling
isolation. Tests use synthetic fixtures only. Successful CI/health checks alone
do not confirm a cashier's production payment; that requires a real operator
confirmation or authorized inspection of that operation.
