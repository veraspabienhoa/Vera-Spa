# Live Tour: VBA baseline and web-parity contract

> Current scope (user clarification, 8 September 2026): Live Tour operates exclusively on server-held PostgreSQL data. VBA/workbook sections below are historical behavioral references, not live data dependencies. File/Google adapters, import/merge actions and external-report links have been removed. Exports are generated downloads only.


This document is the implementation contract for the new `Live Tour` page. The existing `Bảng tua` page remains unchanged; `Live Tour` starts with the same presentation and then owns the write-capable workflow ported from the attached macro workbook.

The contract describes business intent, not a requirement to reproduce Excel internals. Browser, API and database implementations must preserve the observable workflow while replacing desktop-only and unsafe mechanisms.

## Source provenance and extraction inventory

| Item | Extracted baseline |
| --- | ---: |
| Workbook SHA-256 | `8941a6f933b6cce1b75e1911f6d833bb2c3ce8cf4a864a9be3092ed44af8878f` |
| Workbook size | 640,186 bytes |
| Worksheets | 11: 8 visible, 3 hidden |
| VBA modules | 55 |
| Standard modules | 25 |
| Workbook/worksheet class modules | 12 |
| UserForm code modules | 18 |
| UserForm controls | 283 |
| Procedure declarations | 458 `Sub`/`Function`/`Property` declarations detected by source regex across 45 of 55 modules; the other 10 are data-only/minimal |
| Extracted source | 513,893 characters; 16,389 lines; 13,114 non-blank lines |
| VBA project code page | Windows-1252, with mixed Vietnamese text that requires Unicode normalization |

Both compressed VBA source streams and the compiled P-code cache were inventoried. The P-code disassembly contains the same 55 stream names, but P-code is a compiled cache and can lag behind edited source. It also labels several bodies differently from source: `ThisWorkbook`, `UserFormLogin` and `BangDieuKhien` contain displaced or nonsensical procedure names, while binary controls and source events disagree in several forms. This is consistent with a stale/misaligned compiled cache (or an unreliable symbol-table disassembly), so source and P-code must not be assumed semantically identical. The web port uses readable source, workbook formulas and observed data contracts as its baseline; ambiguous legacy cases must be resolved against the server business rules before financial acceptance; Excel is not a runtime or release prerequisite.

No workbook password, customer record or employee record belongs in source control, logs, fixtures or API error messages.

## Complete module inventory

### Standard modules (25)

| Group | Module names | Responsibility |
| --- | --- | --- |
| Core board and state | `Module1`, `Module3`, `Module6`, `Module7`, `Module10`, `Module13`, `Module14` | Login/session globals, board mutations, sorting/filtering, action routing, backup restore, formatting restore, leave synchronization |
| Form entry points | `Module5`, `Doi_DichVu` | Open booking, payment, control-panel and service-change forms |
| Files, reports and sharing | `BangTour`, `Bao_cao_mua_hang`, `Copy_InputToBang_TourExcel`, `DauTrang`, `Export_ReportTo_GoogleSheet`, `Mo_File_Lich_Nghi`, `Zalo`, `modPathManager` | Board/revenue exports, purchase report, external-file discovery, Google export, Zalo/clipboard output, viewport positioning |
| Excel UI and utilities | `Module2`, `Module4`, `Module8`, `Module9`, `Module11`, `Module12`, `FormartingRoom`, `KhaiBao_BienCucBo` | ActiveX creation, report totals/open helpers, Unicode copy, invoice reminder timer, custom copy/paste, placeholder module, room colours, shared declarations/Win32 helpers |

### Workbook and worksheet class modules (12)

| Class module | Workbook object | Relevant events |
| --- | --- | --- |
| `ThisWorkbook` | Workbook | Authenticate and initialize on open; stop reminders, save and back up on close |
| `Sheet1` | `UserList` | Data-only class in extracted source |
| `Sheet2` | `Input` | Double-click action router; completion/early-finish marker on changes to status |
| `Sheet3` | `Layout` | Data-only class in extracted source |
| `Sheet4` | `Backup` | Data-only class in extracted source |
| `Sheet5` | `Room` | Data-only class in extracted source |
| `Sheet6` | `ChoThanhToan` | Double-click a pending row to open pending checkout |
| `Sheet7` | `MuaDo` | Data-only class in extracted source |
| `Sheet8` | `Backup_CF` | Data-only class in extracted source |
| `Sheet9` | `Item` | Data-only class in extracted source |
| `Sheet10` | `Nghi` | Data-only class in extracted source |
| `Sheet11` | `_LB_Temp` | Hidden draft state for multi-booking |

### UserForms (18, 283 controls)

Control counts include static `Label*` controls. The key interactive controls are listed so the browser dialog for each form has an explicit parity target.

| UserForm | Controls | Key controls | Workflow represented on the web |
| --- | ---: | --- | --- |
| `BangDieuKhien` | 15 | `Zoom`, `Hide`, `Show`, `UpdateBangTour`, `AddNhanVien`, `DeleteNhanVien`, `DauTour`, `PassTour`, six move/close buttons | Control panel: refresh board, add/delete staff, move tour order to top/bottom or ±1/3/5 positions, toggle the compact view and zoom |
| `EditRoom` | 5 | `txtRoomNum`, `lstRooms`, `btnInsert`, `btnDelete`, `btnRefreshInput` | Create/delete room or bed identifiers and rebuild the room display |
| `UserForm1` | 4 | `lstNhanVien`, `CommandButton1`, `CommandButton2`, `TuDongGanYCCa1` | Multi-booking workspace; edit several eligible staff drafts, commit together, or automatically set request `YC` for eligible Ca 1 bookings in the late-night window |
| `UserForm2` | 5 | `ComboBox1`, `ComboBox2`, `ComboBox3`, `btnConfirm`, `btnCancel` | Child editor for service, available room/bed and request flag; cancel restores the draft; confirm rechecks room occupancy and PR exclusivity |
| `UserFormAddNhanVien` | 5 | `txtName`, `btnAdd`, `btnAddVIP`, `btnClose` | Add a board employee or mark an existing employee as VIP |
| `UserFormBaoCaoTienTip` | 9 | `txtTuNgay`, `txtDenNgay`, `txtTuGio`, `txtDenGio`, `btnTaoBaoCao` | Export TIP transactions for an inclusive date/time interval |
| `UserFormBooking` | 20 | `ComboBox1/2/3`, `txtTimKiemKH`, `txtKhachHang`, `txtDienThoai`, `txtVeChuaSuDung`, `lstKhachHang`, `btnMuaCombo`, `btnXuatDanhSach`, commit/cancel buttons | Single booking on the selected employee, including customer/combo lookup, service, request and room validation |
| `UserFormBookingNhanh` | 26 | `listNhanVien`, `TextTimNV`, `listLichHen`, `lstKhachHang`, `txtTimKiemKH`, `ComboBox1/2/3`, `btnBooking`, `btnMuaComboAdd` | Quick booking without first locating a worksheet row; filters eligible employees and shows their appointment details |
| `UserFormCheckVeCombo` | 13 | `txtTimKiemKH`, `lstKhachHang`, customer/phone/balance fields, `btnTraCuuLai`, `btnXuatDanhSach`, `btnDong` | Search combo balance and export a customer's service plus combo-purchase history |
| `UserFormChoThanhToan` | 33 | price, discount, TIP, net and total fields; customer search/list; three service selectors; date/time; `ChoThanhToan`, `btnMuaComboAdd`, `cmdLuiNgay` | Settle a row previously moved to the pending-payment workspace, consume combo uses, create invoice/report records, then remove the pending row |
| `UserFormDoiDichVu` | 16 | customer search/list, phone/balance, `ComboBox1`, `btnMuaCombo`, `btnXuatDanhSach`, commit/cancel buttons | Replace the selected row's service and recalculate duration |
| `UserFormLogin` | 5 | `txtUsername`, `txtPassword`, `btnLogin` | Legacy workbook authentication; replaced by the application's authenticated identity and permissions |
| `UserFormMuaThemDichVu` | 16 | customer search/list, phone/balance, `ComboBox1`, `btnMuaCombo`, `btnXuatDanhSach`, commit/cancel buttons | Append an additional service to the selected tour and increase its duration |
| `UserFormMuaVe` | 21 | customer/phone/search/list, `cmbCombo`, `txtSoVe`, `txtThanhTien`, balance, date/time, `btnLuu`, `btnXuatDanhSach`, `cmdLuiNgay` | Sell a combo, allocate an invoice number, create purchase/customer history and revenue entry |
| `UserFormNhapComBoCu` | 9 | customer, phone, `cmbCombo`, `txtSoVe`, `btnLuu` | Import a pre-existing combo balance without creating a new sale |
| `UserFormTaoBaoCao` | 9 | `txtTuNgay`, `txtDenNgay`, `txtTuGio`, `txtDenGio`, `btnTaoBaoCao` | Export revenue transactions for a date/time interval |
| `UserFormThanhToan` | 33 | price, discount, TIP, net and total fields; customer search/list; three service selectors; date/time; `ThanhToan`, `btnMuaComboAdd`, `cmdLuiNgay` | Checkout the selected `Input` tour, consume combo uses and atomically create invoice/report data |
| `UserFormThanhToanNhanh` | 39 | all normal checkout controls plus `TextTimNV`, `txtNhanVien`, `listNhanVien`; `ThanhToanNhanh` | Find an employee inside the payment dialog and perform checkout without navigating to the row first |

## Workbook-to-web data mapping

### `Input`: operational board

Header row is 20 and records start at row 21. The web API must use named fields; Excel column letters below are compatibility aliases only.

| Excel | Meaning | Web field / rule |
| --- | --- | --- |
| A | STT | Imported `stt`; board order is controlled by `sort_index` |
| B | Tên nhân viên | Stable `id`/API `employee_id` plus `name`; a legacy trailing `*` maps to `vip` |
| C | Lịch hẹn / lý do nghỉ | `appointment`; existing legacy leave reasons remain preserved as stored data |
| D | Dịch vụ | `service`; multiple catalogue tokens use the legacy `&` separator |
| E | Yêu cầu | `request`, canonical value `YC` or empty |
| F | Phòng / giường | `room`, referencing a catalogue room/bed `id`/`name` |
| G | Trạng thái | `status`; legacy aliases include `DANG CHO`, `DANG THUC HIEN`, `DANG SU DUNG` and `CHO THANH TOÁN` |
| H | Thời lượng | `duration`, recomputed from the selected catalogue services |
| I | Bắt đầu thường | `started_at`, displayed here when `request` is empty |
| J | Bắt đầu yêu cầu | The same `started_at`, displayed here when `request=YC` |
| K | Còn lại | Derived countdown, never stored as an Excel-style volatile formula |
| L | Thanh toán / ghi nhận ra sớm | Separate `payment_status`, `completion_note` and `completion_delta_minutes` fields |
| M | Số tua thường | `tour_count` |
| N | Số tua yêu cầu | `request_count` |
| O | Tổng số tua | Derived `M + N` |
| P | Đi làm | `work_status`: `Đi làm`, `Nghỉ phép` or `Nghỉ` |
| Q | Vào ca | `shift`: empty, `Ca 1` or `Ca 2` |
| R | Break | Active state derived from `break_started_at` |
| S | Giờ ra | `break_started_at` |
| T | Thời gian break còn lại | Compatibility field `break_remaining_minutes`; live countdown is derived from the 90-minute allowance |
| U | Giờ vào | Imported `clock_in`; a completed web break stores `ended_at` in break history |
| V | Ghi chú | `note`; completion and break outcome remain separate structured fields |
| W | Giờ booking | `booked_at` |
| X | Header says steam time; start logic also stores customer wait minutes | Separate `steam_elapsed_minutes` and `wait_minutes` |

### `Item`: service and combo catalogue

| Range | VBA use | Web entity |
| --- | --- | --- |
| `A:D` | Service ordinal, name, duration and ticket price | `state.services[]`: `id`, `name`, `duration`, `price` |
| `F:H` | Non-request service lookup used by legacy validation/layout | Service tags/eligibility, not a duplicate master |
| `J:M` | Requested-service lookup and duration values | Request eligibility and duration override |
| `O` | Request tokens, principally `YC` | `request_type` enum |
| `Q:T` | Combo ordinal, name, number of uses and price | `state.combos[]`: `id`, `name`, `tickets`, `price` |

Service strings containing multiple entries are split on `&`. Price, duration and `ticket_units` are resolved from catalogue records at the server boundary. The names above are logical entities inside the current aggregate state, not claims that dedicated normalized tables already exist.

### `Room`: room/bed catalogue and live occupancy

| Excel | Meaning | Web rule |
| --- | --- | --- |
| A | Ordinal | Display order |
| B | Bed identifier | Unique `state.rooms[].name` with stable `id` |
| C | Physical room | `state.rooms[].group`; normally the portion before the bed suffix |
| D | Current service | Derived from the active tour |
| E | Current employee | Derived from the active tour |
| F | Current state | Derived from the active tour |
| G | Remaining minutes | Derived from the active tour clock |

The room-card layout, capacity counts and colour thresholds are views of these entities; they are not separately editable totals.

### External `Report`: revenue and activity ledger

| Column | Meaning |
| --- | --- |
| A | Sequential display number |
| B:V | Snapshot of `Input!B:V` at checkout or report time |
| W | Business date |
| X | Business time |
| Y | Authenticated actor |
| Z | Invoice number |
| AA | Net ticket amount after discount |
| AB | Discount |
| AC | TIP |
| AD | Total paid |
| AE | Checkout note; some export code incorrectly reuses the header as a count |
| AF:AH | Reserved invoice-edit audit fields: edit date, edit time and reason |

On the web this becomes an immutable transaction ledger plus explicit revision/audit records. A report row is never updated silently.

### External `KhachHang`: customers and combo balances

| Column | Meaning |
| --- | --- |
| A | Legacy ordinal |
| B | Customer name |
| C | Phone |
| D | Purchased combo |
| E:F | Purchase date and time |
| G | Purchased combo uses |
| H:I | Latest recorded use date and time |
| J | Combo uses consumed |
| K | Remaining uses, derived as `G - J` |
| L | Operator who sold/imported/last touched the record |
| M | Ordinary service-use counter added by later payment code |

The web model separates `customer`, `combo_purchase` and append-only `combo_usage`. Balance is the transactional sum of purchases minus usages, which removes the spreadsheet's duplicated and occasionally stale counters.

## Business workflow and state machines

### Tour lifecycle

| From | Action | Preconditions | Atomic result |
| --- | --- | --- | --- |
| Available | `booking` / `multi_booking` | Employee is working, in Ca 1/Ca 2, not on break; service and free room are valid | Customer/appointment, service, request and room set; state becomes waiting; `booked_at` captured |
| Waiting | `start` | Required fields exist and state is waiting | State becomes running; choose normal/request start timestamp; increment M or N; derive duration, total and wait minutes; snapshot/audit created |
| Running | `add_minutes` / `add_service` / `replace_service` | Active tour; permitted operator | Recompute duration and countdown from normalized service lines |
| Running | `complete` | Active tour | Freeze actual finish/remaining values, release room occupancy, record early/late completion, set payment state to pending |
| Payment pending | `move_pending` | Selected rows are pending | Preserve their complete snapshot in the pending workspace while freeing the employee row for the next tour |
| Payment pending | `checkout` / `quick_checkout` | Valid amounts, actor, customer/combo constraints | Create invoice, revenue ledger, combo usage and audit in one database transaction; mark paid and clear only tour-specific fields |

`DANG SU DUNG` is treated as a legacy alias of running. State changes use canonical enum values in storage and Vietnamese labels only at the UI boundary.

### Work, shift and break state

| Action | VBA intent preserved on the web |
| --- | --- |
| `set_work_status=working` | Mark working through an explicit action after active-tour/break validation; opening the page never resets the row |
| `set_work_status=leave` | Mark leave; block new booking; retain stored reason and audit actor |
| `set_shift=ca_1/ca_2` | Requires working; replaces the worksheet's double-click toggle |
| `start_break` | Requires an entered shift and no active/unpaid service; sets `clock_out`, starts a 90-minute countdown and appends a `break_events` start record |
| `end_break` | Requires an active break; sets `clock_in`, clears the active break and appends an end record with elapsed, remaining and late minutes |

Workbook-open code clears selected shift, break and count columns. That destructive session reset is not ported; web state persists until an explicit action or configured business-day rollover.

### Single booking, multi-booking and room locking

- Single booking uses customer name/phone search, combo balance, service, room/bed and optional request.
- Quick booking finds an eligible employee first. Multi-booking keeps all edits as client/server draft rows and commits the batch transactionally; cancelling restores the original draft.
- Before commit, the server rechecks employee eligibility and room occupancy. Client-side disabled options are only a convenience.
- A busy bed cannot be selected by another booking.
- A service is private-room service when its normalized name contains the legacy `PR`, `P.R` or `P.Riêng` marker, or preferably when its catalogue record has `requires_private_room=true`.
- Private-room locking applies to the physical room prefix, not just one bed. One PR booking reserves every bed in that room; an existing PR booking blocks all other bookings in the room. A prominent circular `PR` badge is shown at the bottom-right of the room card.
- The server repeats the PR check under a row/advisory lock at commit time to prevent two browsers from passing the same availability check.

### Payment, invoice, combo and business day

- Service subtotal is the sum of selected catalogue prices (or a bounded manual ticket price only when every selected service has catalogue price zero). Discount must not exceed subtotal; `net = subtotal - discount` and `total = net + tip` are recomputed by the server.
- TIP must be a valid non-negative amount. The VBA heuristic that rejects a value only because it contains exactly five digits is intentionally removed.
- Invoice numbers are zero-padded with at least three digits, but are allocated by a database sequence/locked counter so simultaneous checkouts cannot duplicate a number.
- Combo use count is the number of selected service tokens classified as combo; ordinary-use count is the remainder. Checkout fails without side effects when the customer lacks enough uses.
- Combo sale creates invoice, purchase, report and audit records in one transaction. Combo import creates an opening-balance event and no sale unless the operator explicitly chooses a sale.
- Customer matching uses a normalized phone identity plus a reviewed name. A phone already owned by another customer is a conflict, not a new row.
- Legacy forms assign transactions between `00:00:00` and `11:09:59` to the previous business date and set the display time to `23:59:00`; from `11:10:00` onward they use the calendar date. The web stores the real timestamp and a separately derived `business_date`, preserving the cutoff without falsifying the event time.
- Manual “Lùi ngày” is available only with both payment and admin permission. It requires a reason, rejects client-supplied timestamps, keeps the real `recorded_at`, and derives `effective_at=23:59` on the preceding business date for invoice numbering, report date and audit.

### Server reports, break history and work status

- Revenue, TIP and customer-detail exports accept explicit date/time bounds and are not affected by hidden rows or a previous filter.
- Export kinds are board/custom, revenue, TIP, customers, one customer's detailed multi-sheet history, pending payment, break events and operational history; PNG is available for the current board.
- Break start/end produces a state-level append-only `break_events` ledger with actor, employee, timestamps, 90-minute allowance, remaining minutes and late minutes. The ledger is admin-visible/exportable and survives restore.
- Live Tour has no external leave-source check, synchronization, or cleanup operation. Work status, shifts and breaks are managed through its own server actions; legacy reasons already stored remain intact.

### Reorder, control panel, export and backup

- Reorder actions preserve the VBA choices: top, bottom, up/down one, three or five. The web changes `sort_index`; it does not forge start timestamps by ±1 second.
- Board filters reproduce “sắp xong”, Ca 1, Ca 2, working/free/running and room order without hiding database records.
- Add/delete employee, VIP flag, room, service and combo catalogue changes are admin actions with confirmation and audit history.
- The compact/full-screen Excel actions become `Ẩn Menu` / `Hiện Menu`, responsive layout and a standalone “Mở tab mới”; they do not attempt to control browser chrome.
- Refresh reads only persisted Live Tour state. First initialization reads the server employee table; subsequent staff additions use Live Tour admin controls.
- `backup` creates a versioned database snapshot and `restore` creates a new revision from it. No restore deletes ledger, invoice, combo-usage or audit history.
- Formatting backups and pivot refreshes become CSS theme tokens and database/report queries; they are not persisted as business data.

## Safe web replacements for desktop-only VBA

| VBA/Excel mechanism | Web replacement |
| --- | --- |
| Plaintext `UserList`, sheet/workbook protection | Application authentication, hashed credentials and server-enforced RBAC |
| `ActiveCell`, double-click and Selection | Stable row IDs, selected-row state and explicit action buttons |
| `_LB_Temp` hidden worksheet | Validated draft object with optimistic version and transactional batch commit |
| `NOW()` formulas and `Application.OnTime` | Server timestamps plus client countdown and an accessible 15-minute in-page pending-payment reminder; a server/push job is needed only if reminders must survive a closed tab |
| Hard-coded drive files and `Workbooks.Open` | Server-owned PostgreSQL state; no file/Drive/Sheets adapters |
| Hidden rows, AutoFilter and cell colour sorting | Query parameters and deterministic UI filters/sort keys |
| Win32 top-most APIs, Ribbon/scrollbar manipulation | Accessible browser modal, sticky controls, menu toggle and standalone tab |
| Clipboard/shape/ActiveX automation | Explicit React controls; browser clipboard/download APIs where permitted |
| Pivot refresh | Server-side aggregation and generated Excel reports |
| File copies on close | Versioned snapshots, retention policy and restore audit |
| Silent `On Error Resume Next` | Typed validation errors, rollback, structured logs and user-visible failure state |

Every mutating request carries the authenticated actor, an idempotency key and the last observed revision. The backend binds each idempotency entry to actor, action and a canonical payload hash, rejects a reused key with different content, and serializes the aggregate state with a PostgreSQL advisory lock plus optimistic revision. Checkout, room assignment, combo consumption, invoice allocation and multi-row booking are committed as one state transaction. Legacy external-sync actions now return HTTP 410 before replay or side effects; historical markers remain stored without retrying any external write.

## VBA defects and ambiguities the web contract intentionally corrects

These deviations preserve business intent and are required for a safe multi-user system:

1. Several checkout routines assign a 21-column source array to a 22-column destination range. Web serialization uses named fields and rejects an invalid shape.
2. Report routines disagree whether data starts on row 2 or row 3 and calculate STT differently. Database IDs are stable; STT is presentation-only.
3. `Input!L` mixes payment status with early-finish text, and completion is partly inferred by clearing `G`. Web storage must separate tour state, payment state and completion note, with an explicit `complete` action.
4. `X` is labelled as steam time but is also overwritten with customer wait minutes. The web contract uses distinct fields.
5. `AE` is written as a note but some export code uses it as a count formula. Note and report count are distinct fields.
6. Workbook open clears shift/break and tour-count cells. The web never clears operational state merely because a user opened a page.
7. Double-click handling claims to toggle the work-status column, but its implementation is commented out. The web exposes explicit working/leave actions.
8. Service replacement adds the new duration to the old duration even after overwriting the old service. The web must recompute duration from current service lines.
9. The procedure named as a “less than -3” cleanup actually compares against an extreme negative value. `clear_expired` must use a documented configurable threshold and dry-run count.
10. Status spelling/case varies (`Vao ca`, `Ca 1`, `DANG SU DUNG`, and others). Persistent storage must use enums and an alias layer.
11. The legacy five-digit TIP check is not a monetary validation rule and is removed.
12. Invoice increment by reading the last cell is race-prone. The web must allocate invoices under a database lock/sequence.
13. Business-date treatment and “today” report filters are inconsistent around midnight. All reports must filter the explicit `business_date` while preserving real timestamps.
14. `UserFormLogin` contains a `cmbCombo_Change` handler referencing controls not present on that form. It is treated as misplaced/dead source and is not ported.
15. Hard-coded local paths, embedded secrets, UI blocking waits and swallowed errors are removed.
16. Mixed legacy encodings can corrupt Vietnamese text. Inputs are stored as UTF-8 NFC; search keys are accent-insensitive without changing displayed names.
17. No readable VBA assignment to `CHO THANH TOAN` was found although several routines depend on it, and no assignment to `DANG SU DUNG` was found although validators reserve it. The web owns explicit, audited transitions instead of relying on an external/manual cell change.
18. Booking variants disagree on clearing payment state, stamping booking time and treating `DANG THUC HIEN` as occupied. One server validator must be shared by single, quick and multi-booking.
19. Customer balance is aggregated by name while deduction updates one exact name/phone row, so VBA can reject or debit the wrong record. The web must resolve one customer ID and consume append-only combo units atomically.
20. `EditRoom` loads its header as selectable data, rebuilds fields differently after insert/delete and silently limits the fixed layout to six beds. Web catalogue validation and responsive room cards remove those worksheet-shape assumptions.
21. Payment and combo-sale error paths can leave external workbooks open or unprotected. Web mutations must either commit completely or roll back without changing authorization state.

## Current implementation status and explicit gaps

The branch now contains substantive Live Tour workflows, not only a route scaffold. Focused backend/frontend tests cover the contracts described as implemented below. “Implemented” means the code path and focused test exist; it does not by itself prove pixel parity, production identity/database wiring, concurrent-browser behavior or every observable workbook edge case.

| Status | VBA workflow / requirement | Current web status and remaining work |
| --- | --- | --- |
| Implemented; visual QA pending | Independent page and Bảng tua presentation | Dedicated route/menu, independent per-user session cache, `Mở tab mới`, menu toggle, counters, filters, room cards, VIP/PR display and employee list are present. Exact responsive/pixel parity still needs screenshot regression on supported viewport sizes. |
| Implemented; server-only | Initialization and saved state | First boot creates an independent board from active KTV/leader records in the server employee table, with off-duty/no-shift defaults. Existing state is loaded unchanged from PostgreSQL. A database read error aborts bootstrap instead of persisting an empty fallback board. File bootstrap and merge are removed. |
| Implemented | Single, quick and multi-booking | Quick booking has accent-insensitive eligible-employee search and appointment suggestions. Multi-booking edits service/request/room per employee, commits atomically, restores client draft on cancel, and implements late-night Ca 1 automatic `YC`. Server validation repeats eligibility, bed occupancy and physical-room PR locking under the state lock. |
| Implemented | Tour lifecycle | Booking captures `booked_at`; start captures wait minutes and one tour counter; add/replace recomputes service time; completion records early/late delta, releases the room logically and moves the row to explicit payment-pending state; pending transfer preserves a payable snapshot. Canonical transition guards prevent forged state jumps. |
| Implemented | Work/shift/break | Work and shift aliases normalize to canonical values. Invalid work/shift/break sequences are rejected; start/end append actor-attributed `break_events`, retain clock-out/clock-in, and record the 90-minute allowance and on-time/late outcome. The ledger is admin-only in state responses and has a bounded-date Excel export. |
| Removed by user requirement | External leave synchronization | No source check, Drive patch, workbook merge or retry runs in Live Tour. The legacy Tour sync route has no callback into Live Tour. Work status, Ca and break actions continue directly on server state. |
| Implemented; external invoice revision semantics unverified | Pending payment and checkout | Direct and pending checkout derive entries, catalogue price, discount, TIP, total and combo units on the server; customer identity conflicts, mixed sources, insufficient combo and invalid amounts roll back without side effects. UI can choose an eligible purchased combo and server-derived ticket use is append-only. Legacy `AF:AH` reserves edit date/time/reason, but those columns alone do not establish an invoice-edit workflow; no corresponding editing UserForm was found among the 18 extracted forms. |
| Implemented | Combo sale/opening balance and customer ledger | Combo sale takes only quantity from the client and derives tickets/price from the catalogue; sale creates purchase, invoice and report. Admin import creates opening balance without a sale. Duplicate-phone ownership is rejected and usage is append-only. Existing server customer records remain intact; old combo opening balances are entered manually, not read from a file. |
| Implemented | Sequential invoices, business date and backdate | Bill numbers use a locked per-business-date counter (`LIVE-YYYYMMDD-NNNN`) and reject duplicate manual values. The 11:10 Vietnam-time cutoff is explicit. Admin “Lùi 1 ngày” keeps real and effective timestamps separately, requires a reason and assigns the effective bill/business date server-side. |
| Implemented server reports; external launchers removed | Reports and customer lookup | Board, revenue, TIP, customer, customer-detail, pending, break and audit/history Excel outputs plus board PNG are generated from server state with optional business-date/cross-midnight time bounds and permission-aware hidden-row handling. Custom board export now offers column checkboxes and all/displayed/selected employee scopes. The server validates the board-column whitelist and selected employee IDs after applying hidden-row permissions, preserves requested column order, and rejects empty, deleted or unauthorized hidden selections. It does not apply financial-report date/time filters to the current board. Exact-ID customer history joins invoices, service lines, purchases, combo use and pending rows, and its Excel output is formula-injection safe. `Bao_cao_mua_hang.bas` (71 lines) only opens/activates external `BaoCaoMuaHang.xlsb`; it contains no purchase-report calculation/layout implementation. The launcher/link is removed from Live Tour per the server-only requirement; this external purchase workbook is not part of its runtime. |
| Intentional web replacement | Google/Zalo/clipboard output | Browser copy/share and authenticated Excel/PNG downloads replace desktop clipboard, shape and Zalo automation. There is no direct Zalo delivery; the VBA's nominal Google export also produced a local workbook, so a Google upload connector is an optional extension rather than parity evidence. |
| Implemented while page is open | Pending-payment reminder | A zero-to-positive pending transition announces immediately, then repeats every 15 minutes through an accessible live region and opens the pending panel. Closed-tab push/background delivery is outside the current browser replacement. |
| Implemented | Control panel, visibility and cleanup | Reorder, add/delete/VIP, hide/show/show-all and room/service/combo catalogue controls are permissioned and audited; operators can explicitly request hidden rows for recovery/export. Admin cleanup accepts an integer grace period of 0–1440 minutes (default 15), previews names/services/rooms/end times without writing, and requires a matching confirmation token plus current revision. A newly expired row invalidates the preview; confirmed rows retain the payable service and move to payment-pending without creating revenue. |
| Implemented; deliberately restricted | Backup/restore safety | Restore is rejected if either current board or backup has a service, unpaid job, pending payment or active break. Idle-board/catalogue restore retains financial/customer ledgers, break events, audit, counters, idempotency and recovery state. This restriction prevents a paid job or completed break from being resurrected. |
| Implemented aggregate storage; normalization optional | Durable server storage | The aggregate domain is persisted as JSON in PostgreSQL `vera_app_setting` with advisory transaction locking and revisions. Dedicated financial/customer tables are a future scaling design, not a dependency on files. There is no automatic historical workbook migration. |
| Not verified end-to-end | Production concurrency, permissions and security | Focused unit/contract tests cover locks, revisions, idempotency, PR collision, invoices, combo balance, PII redaction and capability guards. An authenticated real-PostgreSQL and concurrent multi-browser E2E run remains a release gate. |

Desktop-only behavior intentionally replaced in the preceding table—Win32 top-most windows, worksheet selection, ActiveX, browser-chrome hiding and hard-coded file copies—is not a missing feature. The observable business outcome is the parity target.

### Integration update — 8 September 2026

- Rebased the uncommitted Live Tour implementation onto `main` at `873ecbb`; original `TourPage.jsx` is unchanged. Live Tour includes the newer mobile sticky-header behavior and per-room customer count.
- Room summary groups are separate from bookable beds; new bootstrap uses server catalogue defaults; existing room metadata is preserved. VIP is inferred only for physical groups 16–21. PR works from service text or the catalogue flag. Referenced room/service names, eligibility, duration, PR and combo-unit semantics cannot change until associated jobs are settled.
- Service admin exposes combo ticket units, PR, YC/non-YC eligibility and optional YC duration. New employees default to `Nghỉ` with no shift.
- Counter rollover is 10:00 Vietnam time; the financial day still rolls at 11:10. Rollover resets counters, not active jobs, payments or breaks.
- Revenue summary and Excel include separately labelled expected unbilled revenue, including pending snapshots without double-counting. Unknown/zero prices are flagged; estimated amounts never enter collected revenue.
- Every new mutation requires a revision and a validated idempotency key. Legacy sync markers remain archived and cannot trigger external recovery. Financial/sync receipts do not expire at the ordinary-request soft limit. The aggregate JSON and financial ledgers therefore need a scale/retention design before high-volume production use.
- Focused regression tests include actual HTTP routes with an in-memory database fixture. They are not proof of real PostgreSQL locking, authenticated browser rendering or real deployment persistence. See `live-tour-integration-status.md` for validation results and release gates.
- Follow-up exposes admin break-event history and its date/time-filtered Excel export, and removes the external purchase-report launcher. A read-only synthetic preview uses the actual backend DTO; its server and API guard pass, while browser rendering remains unverified because the session browser blocks localhost.

## Web endpoint, action and permission mapping

The following table is the route and permission mapping currently present in the branch. The backend, not React visibility, enforces each feature.

| Endpoint | Contract | Required feature / default roles |
| --- | --- | --- |
| `GET /v2/live-tour?include_hidden=false` | Board, room cards, catalogues, counters, allowed financial data, response capabilities and revision. Customer PII is redacted without payment permission; hidden rows require operate/admin recovery capability. | `live_tour_view` |
| `GET /v2/live-tour/customers/{customer_id}/history` | Exact stable-ID customer history: invoices, service lines, purchases, combo usage and pending rows with aggregate totals. No fuzzy name/phone fallback. | `live_tour_payment` |
| `POST /v2/live-tour/action` | `{action, expected_revision, idempotency_key, payload}`; employee targets live in `payload.employee_id`, `payload.employee_ids` or per-row `payload.bookings`. Every mutation requires the idempotency key and returns the refreshed state/revision. | Per-action rules below |
| `GET /v2/live-tour/export.xlsx?kind=…` | `board`, `custom`, `revenue`, `tip`, `customers`, `customer_detail`, `pending`, `breaks` or `history`; data kinds accept optional `date_from`, `date_to`, `time_from`, `time_to`, and customer detail requires `customer_id`. | `live_tour_export`, with additional rules below |
| `GET /v2/live-tour/export.png?kind=board` | Render current board without customer/phone detail. Hidden rows are included only when explicitly requested by operate/admin. | `live_tour_export` |

| Permission | `action` values |
| --- | --- |
| `live_tour_operate` | `booking`, `multi_booking`, `start`, `add_minutes`, `complete`, `set_work_status`, `set_shift`, `start_break`, `end_break`, `reorder`, `hide_employee`, `show_employee`, `show_all`, `replace_service`, `add_service` |
| `live_tour_payment` | `move_pending`, `checkout`, `quick_checkout`, `combo_purchase` |
| `live_tour_admin` | `add_employee`, `delete_employee`, `set_vip`, `room_upsert`, `room_delete`, `service_upsert`, `service_delete`, `combo_upsert`, `combo_delete`, `combo_import`, `backup`, `restore`, `clear_expired`, `clear_expired_preview` |
| `live_tour_payment` **and** `live_tour_admin` | `checkout`, `quick_checkout` or `combo_purchase` when `payload.backdate_one_day=true`; a correction reason is mandatory |
| `live_tour_payment` in addition to operate | `booking` / `multi_booking` payloads that contain customer identity fields |
| `live_tour_export` | Board/custom Excel and board PNG. Revenue/TIP/customers/customer-detail/pending additionally require payment; history/breaks additionally require admin. Hidden board/PNG rows additionally require operate or admin. |
| `live_tour_view` | Read endpoint and menu visibility; it is not an action-envelope value |

Response capabilities are server-derived: `operate`, `payment`, `admin`, `export` and `hide_recovery`; `catalog_admin` and `manage_catalog` are aliases of `admin`. `hide_recovery` means operate or admin; no sync capability is exposed. These capability names are not additional permission-registry keys.

Current role defaults are: admin receives all five Live Tour permissions; both quản lý and lễ tân receive view/operate/payment/export but **not** `live_tour_admin`; leader, nhân viên and locker receive view only; tạp vụ receives no Live Tour permission. Legacy `tour_leave_sync` permission is unrelated to Live Tour. Account overrides may grant or revoke any registered feature. There are no separate `live_tour_checkout`, `live_tour_visibility_manage` or `live_tour_sync` permission keys.

## Release parity checklist

All boxes remain acceptance gates even where a route or button already exists; check only after behavioral verification.

- [ ] `Live Tour` has its own route, menu item, `live_tour_view` permission, independent cache key, `Mở tab mới`, `Hiện Menu` and `Ẩn Menu`.
- [ ] Initial layout is a visual and responsive copy of the current `Bảng tua`; changes to Live Tour do not mutate the legacy page or its source configuration.
- [ ] Summary counters, Ca filters, Standard/VIP rooms, room colours, PR badge and employee lists match the current board without nested employee-list scrolling.
- [ ] Every action named in the endpoint contract is wired from UI to backend and returns a refreshed revision.
- [ ] Single, quick and multi-booking enforce working/shift/break eligibility, room occupancy and physical-room PR exclusivity on the server.
- [ ] Start, countdown, add minutes/service, replace service, completion, early/late note, pending transfer and employee reuse pass deterministic clock tests.
- [ ] Checkout and quick checkout atomically create invoice, revenue, payment, combo usage and audit; a failed validation changes nothing; admin backdate preserves real/effective time and requires a reason.
- [ ] Combo sale/import, insufficient-balance rejection, duplicate-phone conflict and customer history behave consistently.
- [ ] Boundary tests cover `23:00`, `03:00`, `11:09:59` and `11:10:00`, including report `business_date`.
- [ ] Working/leave, Ca 1/Ca 2 and break start/end transitions reject invalid sequences; start/end break events and 90-minute outcome survive restore.
- [x] Server-only regression: initialization, refresh, saved bookings and retired endpoints require no external source; old sync/merge actions reject before side effects. Real PostgreSQL deployment acceptance remains separate.
- [ ] Reorder, hide/show, employee/VIP, room/service/combo catalogue, backup/restore and expiry cleanup are permissioned and audited; expiry cleanup requires a reviewed preview.
- [ ] Excel exports for board, revenue, TIP, customers, exact-ID customer detail, pending, breaks and history plus board PNG are generated from server data and do not leak hidden personal fields.
- [ ] Concurrent booking, checkout, invoice allocation and combo-use tests prove no double room, duplicate invoice or negative combo balance.
- [ ] A production decision covers normalized customer/financial/break/revision tables and retention of existing server history.
- [ ] No plaintext secret or real customer/employee fixture is committed; database and API security checks pass before Production deployment.
