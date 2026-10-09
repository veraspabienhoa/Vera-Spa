# Employee deletion and FaceGate profile removal — 09-10-2026

Deleting employees through the Admin staff endpoint queues the uniquely confirmed
FaceGate UID/name/face-reference in the same transaction as account deletion and
session revocation. The serving mapping is detached immediately; only the durable
job retains the binding needed to delete the old device profile. Local Face ID photo and self-update authorization are removed
in that transaction, preventing a new person reusing the name from inheriting them.
VERA financial and attendance history retain their existing preservation policy.

After commit, a bounded worker reads both the complete device roster and profile
detail, checks the expected UID/name/reference, and uses the operator-supplied
firmware's `bwlist.js` / `funDelList` command:
`/webs/setWhitelist?action=del&group=LIST&LIST.uid=<uid>`.
It reads the roster again and requires both UID and face reference to be absent
before completing the job and removing its corresponding completed enrollment journal.
A reused UID or moved face reference fails closed. A lost delete reply is reconciled
by reading, without repeating a successful delete. Offline jobs remain durable;
the existing FaceGate minute schedule retries independently of TimeSoft networking.
Enrollment/photo replacement, rename and manual mapping changes are blocked while
a deletion is pending. An unresolved enrollment or pending name change blocks
account deletion before any local data is committed. Unknown/multiple/stale-device
mappings require review instead of deleting profiles by name.

The worker holds one pooled connection and one session lock; no device HTTP call
runs in an open database transaction. Errors expose only pending status/type and
cannot stop attendance archiving. The deletion dialog and response describe the
profile deletion and distinguish verified completion from pending verification.

## Limits and production verification

This command removes the firmware's registered person/profile and its face
association. Its observed UI does not expose per-person deletion of historical
capture images/control logs, old orphaned photo storage or secure erasure of flash.
Do not claim all historical or physical bytes have been erased. Global log clearing
would destroy other employees' evidence and is not used. Full per-person historical
data erasure requires a verified firmware/vendor capability before implementation.

No production employee or device has been deleted to test this change. After
deployment, an owner-authorized actual deletion must verify the exact deployed
commit, both health endpoints, profile/face-reference absence, pending retry
recovery, and subsequent registration of a new employee with the reused name.
