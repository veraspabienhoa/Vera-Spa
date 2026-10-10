# Phase-one concurrency safeguards (source change)

## Scope

- Daily work schedules use per-cell compare-and-swap revisions. A single PUT
  atomically saves and deletes its batch. Conflicts return HTTP 409; no partial
  batch is committed. The browser keeps unrelated drafts and requires review of
  cells changed by someone else.
- Copy-only `/v2/staff/image-text` OCR uses a dedicated bounded executor and one
  total deadline instead of running Pillow/Tesseract on the ASGI event loop.
- Live Tour details and lookup reads coalesce pending revision changes into a
  trailing read, with stale-scope guards, rather than losing updates or constantly
  cancelling a slow request.

This change does not authorize deployment, change financial calculations or
permissions, or establish that production is healthy.

## Schedule API and migration

The existing deployment schema gate calls `prepare_read_schemas`, which upgrades
`work_schedule` from version 1 to 2 on its caller-owned transaction. It adds a
BIGINT revision using `vera_work_schedule_revision_seq` and a BEFORE UPDATE
trigger. Existing rows receive revisions. Every SQL update gets a fresh revision,
including maintenance writers. Deleting and recreating a row cannot recycle an
old revision. No business row values or history are otherwise changed.

GET `/v2/work-schedule` returns `revision` on every row. PUT requires
`expected_revision` on every upsert (0 only for a cell observed absent), and accepts
`deletes` containing `work_date`, `employee_username`, and `expected_revision`.
DELETE also requires `expected_revision` in the query. Old clients without a
revision fail closed with 422, rather than bypassing stale-write protection.
Excel import remains a preview; the browser supplies its loaded cell revisions
when the user saves the imported values.

Deploy the matching frontend and backend together using the existing schema gate.
Allow the schema migration to complete before serving the new code. Reload open
browser tabs after rollout; do not retry an old unversioned request unchanged.
Rollback to an older API would remove CAS protection even though the revision
column/trigger remain. Do not remove the sequence or reset it during rollback.

## OCR capacity

`VERA_IMAGE_TEXT_WORKERS` defaults to 1 per API process, clamped to 1–4.
`VERA_IMAGE_TEXT_TIMEOUT_SECONDS` defaults to 30 seconds, clamped to 1–60.
The deadline includes upload time and processing. Admission is immediate: excess
requests receive retryable HTTP 503 with `Retry-After: 1`. Timeout returns 504.
Cancelled/timed-out work retains its slot until its actual worker exits; there is
no unbounded executor queue. Subprocess attempts share the remaining deadline.
Images and extracted text are not persisted or logged. The existing authenticated,
copy-only endpoint and type/size/image validation remain in place.

These limits are per process, so multiply capacity by the API worker count when
sizing the host. A Python thread cannot be forcibly killed safely: a stuck image
decoder retains its slot, protecting capacity while the request has timed out.
Environment changes require process restart by the operator.

## Validation and operator acceptance

Regression coverage includes same-cell creates/updates, independent-cell updates,
batch rollback, stale deletes and delete/recreate, missing revisions, permissions,
old-schema migration, slow reads, cancellation, deadline recovery and bounded OCR.
Real PostgreSQL tests require `VERA_TEST_POSTGRES_URL`; skipped local tests must
not be reported as passed. CI provisions its existing disposable PostgreSQL 16
service. No test should use the production database or personal images.

After operator deployment, verify the exact deployed commit, `/v2/auth/health`,
`/v2/health`, and the affected business operations. Use two test sessions editing
the same schedule cell and different cells, a test image, and a slow-network Live
Tour session. A successful build alone does not establish production correctness.

## Pre-merge Node regression repair

The complete Node suite on the original phase-one head reproduced four failures
already present on its main baseline. Three assertions were stale: copied PNG
bytes were incorrectly required to retain Blob object identity, a shared PNG
helper was required to use the older Live-Tour-specific error wording, and the
border test scanned unrelated stylesheet sections after the Live Tour comment.
The implementation still needs to retain PNG bytes/type and source errors, and
the Live Tour body-grid exception still applies on screen and in print.

One failure exposed a real clipboard recovery problem: permission denial was
retried after waiting for image generation, then wrapped in a plain Error. That
lost the NotAllowedError name used by the Live Tour recovery message. Preserve
original errors, handle late image rejection without an unhandled promise, and
limit the one concrete-Blob compatibility retry to TypeError while user activation
has not explicitly expired. Never turn copy failure into download or share.
Source-generation errors take precedence when a browser masks rejected item data.

Regressions now check immediate click-turn writes, byte preservation, malformed
and empty PNGs, pending-image denial, masked source errors, legacy compatibility,
expired activation, parsed border rules and deliberately injected CSS regressions.
Purchase PNG UI tests preserve filtered-table download, explicit preview/share,
unsupported sharing, cancellation, and object-URL cleanup. The production capture,
download/share implementation and CSS are unchanged. CI also runs every
`web-v2/tests/*.test.mjs`, in addition to its named checks, so these tests cannot
silently fall outside the merge gate again. These are synthetic Node/DOM checks;
actual OS clipboard/paste, device share sheets and production remain unverified.
