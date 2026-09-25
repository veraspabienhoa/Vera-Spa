"""Policy agreed with the owner: identical retail content is allowed.

This selects policy from canonical, locked rows, never an untrusted client flag.
The existing /v2/live-tour/action remains the payment boundary; this example is
not a second route and does not replace its validation, locks or accounting.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class InvoicePolicy:
    kind: str
    request_replay_protection: bool
    content_duplicate_check: bool
    protect_combo_consumption: bool


def invoice_policy(canonical_entries):
    uses_combo = any(bool(entry.get('combo_purchase_id')) for entry in canonical_entries)
    return InvoicePolicy(
        kind='combo' if uses_combo else 'retail',
        request_replay_protection=True,
        content_duplicate_check=False,
        protect_combo_consumption=uses_combo,
    )


# Actual canonical execution order in VERA:
# 1. Authenticate caller; require payment permission; validate request_key.
# 2. Begin transaction, lock affected resources and load canonical booking lines.
# 3. Replay same request key only if actor/action/payload hash match; otherwise 409.
# 4. Derive policy above from canonical lines. For retail, do NOT search prior
#    invoices by customer/amount/time to reject an otherwise valid new sale.
# 5. For combo, atomically validate reservation, available units and redemption
#    identity; debit once while holding the same resource locks as invoice write.
# 6. Persist invoice, reports, combo debit and request receipt in one transaction.
# 7. Commit, then send response/notification; never retry a payment with a NEW key.
# Mixed invoices follow combo rules for each combo line; retail lines remain valid.
# Sale of a new combo is an inventory/money operation and retains existing safety.
