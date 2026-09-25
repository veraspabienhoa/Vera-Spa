# Bounded audit ordering writes

A synthetic state at MAX_AUDIT (3,000 entries) reproduced 3,003 database
execute calls for one appended event. Removing the oldest entry shifts the
retained array ordinals, and the resource writer formerly sent one UPDATE
per shifted entry while holding transaction locks.

Collect payload-identical ordinal changes by collection and apply each group
with one UPDATE FROM jsonb_to_recordset statement. Preserve all requested
ordinals, payloads, soft deletions, insertions, financial receipts, revision
semantics and the enclosing transaction. The existing metadata row update
continues to serialize publication through commit. This change does not
disable idempotency or release a transaction's locks early.

test_live_tour_audit_batch.py checks that a full-ring append needs no more than
six execute calls. PostgreSQL coverage in test_live_tour_receipt_postgres.py
checks retained event order, unchanged payload revisions and payment receipts,
and atomic rollback of a subsequent eviction.
