# Face ID photo and attendance migration — implementation status

## Current user workflow: manual photos, bulk upload by username

The user chose to photograph staff manually instead of importing TimeSoft photos.
Use Nhân viên → Tải ảnh FACE ID hàng loạt. Select up to 50 JPG/PNG/WebP photos,
100 MB total (20 MB per original image). Each filename stem must equal the VERA
username / Tên nhân viên, not full_name. Matching trims outer whitespace,
normalizes Unicode and ignores case, but preserves Vietnamese accents and
internal spaces. Ambiguous account names and duplicate filenames are blocked.

Preview shows the exact username and resulting image. Images are compressed
locally and padded to 3:4 without automatically cropping the face. The shared
Crop / Rotate / Compress editor can adjust each before saving. Existing photos
are unselected by default; the operator must select them to replace them.
Uploads run sequentially, retain per-file success/failure and skip successes on
retry. The API rechecks filename mapping and compares the current photo hash
under the employee lock before replacing; a concurrent change returns 409.

This tool stores photos in VERA; it does not enroll them in hardware or switch
the attendance source. The optional TimeSoft manifest importer below is retained
for legacy exports but is not required for the user's chosen workflow.


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

## Read-only device probe for the next step

After deploying the code, `vera_facegate_readiness.py --date YYYY-MM-DD` can run
on the VPS to read one Control Log page (at most 20 events) through the configured
FaceGate connection and summarize stored reference mappings. A 30-second deadline
bounds the probe. It prints only counts and numeric raw status/type codes; it
never prints names, photos, connection settings or credentials. PostgreSQL is
read-only and released before device I/O. It does not prove that a stored mapping
is still current on the device, infer status meanings, or change attendance.

The next integration step requires a known real device scan and its corresponding
Control Log status/type, plus a confirmed enrollment API for the actual device.
The probe deliberately reports attendance_cutover_ready=false until those are
implemented and verified. Manual upload replaces the TimeSoft photo import step,
not the device enrollment or checkin ingestion step.
