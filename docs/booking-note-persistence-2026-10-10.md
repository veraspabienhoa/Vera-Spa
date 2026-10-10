# Booking note persistence

This is a source change. No production data migration, historical note recovery,
or backend deployment is performed by this patch.

## Note ownership

- A new booking starts with the submitted note, or an empty note when omitted.
  It never inherits an employee's previous customer's note.
- An existing booking keeps its saved note when an update omits the field. An
  explicit empty string clears that booking's editable note.
- Finish and direct checkout snapshot each booking's note into its own entry
  before releasing the employee assignment. Clearing an assignment clears its
  current note as well.
- Pending and paid invoices have a separate, editable invoice-level note. Its
  initial default is the distinct nonempty booking notes in source order, joined
  by line breaks. Each entry retains the employee/room association for its own
  original booking note.
- Omitting a checkout note preserves the pending invoice note, including an
  explicitly saved empty note. When there is no saved invoice note, checkout
  derives the default from the booking entries. Explicitly clearing an invoice
  note does not erase the original entry snapshots.

## Operator behavior

The booking dialog keeps its note visible for active service and completed or
pending service. Pending edits use the existing invoice editor and its existing
permissions, revision checks, correction-reason and date rules. Checkout loads
the selected source's note and resets it when the operator switches sources.
Canceling a dialog does not save its unsent edits.

Booking and checkout drafts keep the revision of the source they displayed.
Background refreshes do not rebase an older note onto another operator's newer
booking or invoice. A conflicting edit requires reopening the current source.

Receipt, report and customer-history views can distinguish booking notes from
the invoice note. Existing paid records are left unchanged; notes already lost
by old code cannot be reconstructed automatically from this change.

## Verification and rollout

Regression coverage exercises booking creation and omitted-versus-empty updates,
Finish, grouped entries, direct and pending checkout, source switching, deliberate
clearing, employee reuse, read-only historical presentation and transaction
rollback/retry. Run the complete Python suite against an isolated PostgreSQL
database and the complete Web V2 Node suite, lint and production build.

Financial totals, payment idempotency, resource concurrency controls and
authorization remain on their existing paths. There is no schema migration.
Merging Web V2 changes triggers the repository's existing GitHub Pages workflow;
server-side persistence requires a separately authorized VPS backend rollout.
