# Face ID photo and attendance migration — implementation status

The proposed staff Face ID photo feature stores photos in the separate
`vera_employee_face_id` table. Existing portrait/CCCD storage and PDF queries do
not include this table. Permission keys `employee_face_id_view` and
`employee_face_id_manage` are Admin-only by default and can be delegated using
the existing PostgreSQL permission editor. A delegated user can open the Face ID
card directly from desktop/mobile employee lists without receiving CCCD access.

The UI reuses the existing portrait crop, rotation, compression and camera
editor. It accepts uploaded files, the employee's existing portrait, or a
manually selected image from the existing FaceGate capture API. Capture rows
are NOT employee identity proof. Operators must inspect the selected image in
the editor before saving. Device network requests happen outside DB transactions.

## Remaining work requiring real source/device evidence

No TimeSoft photo import, device enrollment, direct attendance ingestion, or
attendance source switch has been performed by this change.

To import existing photos, obtain a TimeSoft export of registration photos and
its employee-code association, then reconcile each code to exactly one VERA
username. Do not match faces by appearance or names alone. Report missing,
duplicate and conflicting mappings before writing; preserve existing VERA
photos unless an overwrite is explicitly chosen. Record import source and
counts, and verify saved image hashes. This migration utility remains to be
implemented against the actual export format.

To retire TimeSoft, identify the device vendor/model/firmware and its documented
push or polling protocol. The observed FaceGate capture endpoint supplies image
references, but the current adapter is not verified as an authoritative employee
attendance source. A photo stored in VERA is not enrollment on the device.

Implement authenticated device ingestion into a local immutable event table
with unique device/event IDs, confirmed employee mapping, original timestamp,
Vietnam business date, retry/deduplication and checkpoint/backfill. Connect
attendance, Live Tour, breaks and payroll to those local events. Verify real
check-in/out, disconnection/reconnect and duplicate delivery before switching
the source. Retain historical TimeSoft records as history; do not delete them.
The existing payroll/attendance reader and TimeSoft worker remain unchanged
until that implementation is ready, so this PR alone does not satisfy the
requested source cutover.
