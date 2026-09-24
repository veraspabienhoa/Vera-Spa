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
counts, and verify saved image hashes. The reviewed manifest importer below is available; converting a real TimeSoft
export to that manifest still requires its actual format and confirmed mapping.

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

## Reviewed export importer

`vera_face_id_import.py` is an operator CLI, not an automatic TimeSoft downloader.
It accepts up to 50 photos per batch beside a UTF-8 JSON manifest:

```json
{"source":"timesoft","entries":[{"employee_code":"TIMESOFT_CODE","username":"VERA_USERNAME","file":"photos/employee.png","sha256":"SHA256_OF_EXACT_FILE","mapping_confirmed":true}]}
```

An operator must confirm the TimeSoft code-to-VERA username relationship from
source records. The importer checks exact VERA usernames; it cannot independently
verify a code in TimeSoft without access to that source. It rejects duplicate
codes/usernames/files, files outside the manifest directory, hash mismatches,
invalid/oversized photos and existing VERA Face ID photos. Images must already
meet the editor's 3:4 and size limits; it does not crop faces automatically.
No attendance source is changed.

On the VPS with the application environment and approved export available:

```sh
/opt/vera-spa/.venv/bin/python vera_face_id_import.py /secure/export/manifest.json
```

The default uses a read-only database connection and prints only count, plan
hash and applied=false. After reviewing all mappings, use that exact plan hash:

```sh
/opt/vera-spa/.venv/bin/python vera_face_id_import.py /secure/export/manifest.json --apply --plan-sha REVIEWED_HASH --actor OPERATOR_USERNAME
```

Apply validates again, locks employee rows, writes photos and import audit in
one transaction and never overwrites. Cross-batch code/username uniqueness is
enforced in the audit table. Changed mappings or image bytes invalidate the
reviewed hash. Logs do not expose images, employee identifiers or credentials.
No real import has been executed. Device enrollment and direct attendance
collection remain outstanding.
