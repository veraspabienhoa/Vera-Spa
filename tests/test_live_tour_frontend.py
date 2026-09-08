import re
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "web-v2/src/App.jsx"
SHELL = ROOT / "web-v2/src/components/AppShell.jsx"
API = ROOT / "web-v2/src/lib/api.js"
LIVE_TOUR = ROOT / "web-v2/src/pages/LiveTourPage.jsx"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_quoted_literal(source: str, value: str) -> bool:
    return bool(re.search(rf"(['\"])({re.escape(value)})\1", source))


def test_live_tour_has_its_own_route_menu_entry_and_permission():
    app = _source(APP)
    shell = _source(SHELL)

    assert "'live-tour'" in app
    assert "import('./pages/LiveTourPage')" in app
    assert re.search(r"page\s*===\s*['\"]live-tour['\"].*<LiveTourPage\b", app)
    assert re.search(
        r"id:\s*['\"]live-tour['\"].*label:\s*['\"]Live Tour['\"].*permission:\s*['\"]live_tour_view['\"]",
        shell,
    )


def test_live_tour_uses_an_independent_session_cache():
    source = _source(LIVE_TOUR)

    assert "vera-live-tour-cache:" in source
    assert "sessionStorage" in source
    assert "vera-tour-cache:" not in source


def test_live_tour_api_exposes_read_write_and_export_contracts():
    api = _source(API)

    for method in (
        "liveTour",
        "liveTourAction",
        "exportLiveTourExcel",
        "exportLiveTourPng",
    ):
        assert re.search(rf"\b{method}\s*:\s*", api), f"Missing veraApi.{method}"

    assert api.count("/v2/live-tour") >= 4
    action_method = re.search(
        r"liveTourAction\s*:\s*(.*?)(?=\n\s*[A-Za-z_$][\w$]*\s*:|\n})",
        api,
        re.DOTALL,
    )
    assert action_method
    assert "method: 'POST'" in action_method.group(1) or 'method: "POST"' in action_method.group(1)
    assert "JSON.stringify" in action_method.group(1)


def test_live_tour_wires_every_vba_equivalent_action_to_the_backend():
    source = _source(LIVE_TOUR)
    expected_actions = {
        "booking",
        "multi_booking",
        "start",
        "add_minutes",
        "complete",
        "move_pending",
        "checkout",
        "quick_checkout",
        "set_work_status",
        "set_shift",
        "start_break",
        "end_break",
        "reorder",
        "hide_employee",
        "show_employee",
        "show_all",
        "add_employee",
        "delete_employee",
        "set_vip",
        "replace_service",
        "add_service",
        "room_upsert",
        "room_delete",
        "service_upsert",
        "service_delete",
        "combo_upsert",
        "combo_delete",
        "combo_purchase",
        "combo_import",
        "backup",
        "restore",
        "merge_current_tour",
        "clear_expired",
        "sync_leaves",
    }

    missing = sorted(action for action in expected_actions if not _has_quoted_literal(source, action))
    assert not missing, f"Live Tour is missing action contracts: {', '.join(missing)}"


def test_live_tour_exposes_the_main_board_controls_and_workspaces():
    source = _source(LIVE_TOUR)
    expected_labels = {
        "LIVE TOUR",
        "Mở tab mới",
        "Điều khiển",
        "Đặt lịch nhanh",
        "Đặt lịch",
        "Đặt lịch hàng loạt",
        "Bắt đầu đã chọn",
        "+30 phút",
        "Hoàn thành",
        "Chờ thanh toán",
        "Thanh toán nhanh",
        "Đi làm",
        "Nghỉ phép",
        "Ca 1",
        "Ca 2",
        "Bắt đầu break",
        "Kết thúc break",
        "Ẩn đã chọn",
        "Hiện tất cả",
        "Thêm nhân viên",
        "Xóa nhân viên",
        "Đánh dấu VIP",
        "Đổi dịch vụ",
        "Khách hàng & combo",
        "Báo cáo",
        "Lịch sử & sao lưu",
        "Danh mục",
        "Xuất bảng tua",
        "Xuất doanh thu",
        "Xuất tiền TIP",
        "Xuất khách hàng",
        "Xuất chờ thanh toán",
        "Xuất lịch sử",
        "Xuất PNG",
        "Đồng bộ toàn bộ lịch nghỉ",
    }

    missing = sorted(label for label in expected_labels if label not in source)
    assert not missing, f"Live Tour is missing controls/workspaces: {', '.join(missing)}"


def test_live_tour_can_open_itself_in_a_standalone_new_tab():
    source = _source(LIVE_TOUR)

    assert "Mở tab mới" in source
    assert re.search(r"searchParams\.set\(['\"]page['\"],\s*['\"]live-tour['\"]\)", source)
    assert re.search(r"searchParams\.set\(['\"]standalone['\"],\s*['\"]1['\"]\)", source)
    assert re.search(r"window\.open\([^\n]+['\"]_blank['\"]", source)


def test_live_tour_reuses_an_idempotency_key_until_the_same_request_succeeds():
    source = _source(LIVE_TOUR)

    assert "function stableSerialize" in source
    assert "function requestSignature(action, payload)" in source
    assert "const requestEntriesRef = useRef(new Map())" in source
    assert "const existing = entries.get(signature)" in source
    assert "if (existing && !preferredKey) return existing" in source
    assert "window.sessionStorage.getItem(storageKey)" in source
    assert "window.sessionStorage.setItem(storageKey, entry.key)" in source

    signature_function = source[
        source.index("function requestSignature") : source.index("function signatureHash")
    ]
    assert "expected_revision" not in signature_function

    execute_action = source[
        source.index("const executeAction") : source.index("const runSelected")
    ]
    api_call = execute_action.index("await veraApi.liveTourAction(body)")
    release = execute_action.index(
        "releaseIdempotencyEntry(requestEntriesRef.current, requestEntry)"
    )
    catch = execute_action.index("} catch (err) {")
    assert api_call < release < catch
    assert "releaseIdempotencyEntry" not in execute_action[catch:]


def test_live_tour_only_reloads_on_a_confirmed_revision_conflict_and_keeps_real_409_text():
    source = _source(LIVE_TOUR)

    conflict_helper = source[
        source.index("function isRevisionConflict") : source.index("const PAYMENT_ACTIONS")
    ]
    assert "if (error?.status !== 409) return false" in conflict_helper
    assert "revision_conflict" in conflict_helper
    assert "live tour đã thay đổi ở thiết bị khác" in conflict_helper.lower()

    execute_action = source[
        source.index("const executeAction") : source.index("const runSelected")
    ]
    assert "const message = liveTourErrorDetail(err)" in execute_action
    assert "if (isRevisionConflict(err))" in execute_action
    assert "await load(true, true)" in execute_action
    assert execute_action.count("setError(message)") >= 2
    assert "err?.status === 409 ||" not in execute_action
    assert "xung đột|revision|phiên bản" not in execute_action


def test_live_tour_guards_controls_and_requests_with_server_capabilities():
    source = _source(LIVE_TOUR)

    for capability in (
        "canOperate",
        "canPayment",
        "canAdmin",
        "canExport",
        "canSyncLeave",
        "canRecoverHidden",
    ):
        assert f"const {capability}" in source

    assert "capability('operate'" in source
    assert "capability('payment'" in source
    assert "capability('admin'" in source
    assert "capability('export'" in source
    assert "capability('sync'" in source
    assert "capability('hide_recovery'" in source
    assert "const canOperate = capability('operate', isAdmin ||" in source
    assert "const canPayment = capability('payment', isAdmin ||" in source
    assert "const canAdmin = capability('admin', isAdmin ||" in source
    assert "const canExport = capability('export', isAdmin ||" in source
    assert "const canSyncLeave = capability('sync', isAdmin ||" in source
    assert "isAdmin || capability('operate'" not in source
    assert "const SYNC_ACTIONS = new Set(['sync_leaves'])" in source
    assert "if (SYNC_ACTIONS.has(action)) return capabilities.sync" in source
    assert "if (HIDDEN_RECOVERY_ACTIONS.has(action)) return capabilities.hideRecovery" in source
    assert "if (!canRunAction(action" in source
    assert "disabled={!canRecoverHidden}" in source
    assert "if (!canExportKind(kind))" in source
    assert "if (!canSyncLeave)" in source


def test_live_tour_syncs_leaves_atomically_through_the_live_tour_action():
    source = _source(LIVE_TOUR)
    sync_flow = source[
        source.index("const syncLeaves") : source.index("const exportData")
    ]

    assert "executeAction('sync_leaves', { sync_action: syncAction }, [], { idempotencyKey: recoveryKey })" in sync_flow
    assert "const syncLeaves = async (syncAction = 'sync_all', recoveryKey = '')" in sync_flow
    assert "result?.state?.sync_status" in sync_flow
    assert "actionResult?.sync?.message" in sync_flow
    assert "actionResult?.merge?.message" in sync_flow
    assert "syncTourLeave" not in sync_flow
    assert "merge_current_tour" not in sync_flow


def test_live_tour_leaves_auto_yc_timing_to_the_server():
    source = _source(LIVE_TOUR)

    assert "auto_yc_ca1: Boolean(form.auto_yc_ca1)" in source
    assert "Tự động gán YC cho Ca 1 từ 23:00–03:00" in source
    assert ".getHours()" not in source


def test_live_tour_modal_supports_escape_focus_trap_and_focus_restore():
    source = _source(LIVE_TOUR)
    modal = source[
        source.index("function LiveTourModal") : source.index("const EMPTY_FORM")
    ]

    assert "const previousFocus = document.activeElement" in modal
    assert "event.key === 'Escape'" in modal
    assert "event.key !== 'Tab'" in modal
    assert "previousFocus?.focus?.()" in modal
    assert 'tabIndex="-1"' in modal
    assert 'role="dialog"' in modal
    assert 'aria-modal="true"' in modal


def test_live_tour_export_access_depends_on_the_requested_data_kind():
    source = _source(LIVE_TOUR)
    helper = source[
        source.index("function hasLiveTourExportAccess") : source.index("function compactExportQuery")
    ]

    assert "if (!capabilities.export) return false" in helper
    assert "if (kind === 'board' || kind === 'custom') return true" in helper
    assert "if (kind === 'history' || kind === 'breaks') return capabilities.admin" in helper
    assert "PAYMENT_EXPORT_KINDS.has(kind) && capabilities.payment" in helper
    assert "new Set(['revenue', 'tip', 'customers', 'pending', 'customer_detail'])" in source

    assert "disabled={!canExportKind('pending')}" in source
    assert "disabled={!canExportKind('customers')}" in source
    assert "disabled={!canExportKind(kind)}" in source
    assert "disabled={!canExportKind('board')}" in source
    assert "disabled={!canExportKind('history')}" in source


def test_export_permission_matrix_includes_breaks_without_escalation():
    source = _source(LIVE_TOUR)
    helper = source[source.index("function hasLiveTourExportAccess"):source.index("function compactExportQuery")]
    kinds = ["board", "custom", "history", "breaks", "revenue", "tip", "customers", "pending", "customer_detail", "unknown"]
    cases = [
        ({"export": False, "admin": True, "payment": True}, []),
        ({"export": True, "admin": False, "payment": False}, ["board", "custom"]),
        ({"export": True, "admin": True, "payment": False}, ["board", "custom", "history", "breaks"]),
        ({"export": True, "admin": False, "payment": True}, ["board", "custom", "revenue", "tip", "customers", "pending", "customer_detail"]),
    ]
    prelude = re.search(r"const PAYMENT_EXPORT_KINDS = .*", source).group(0)
    script = prelude + "\n" + helper + "\nconst kinds=" + json.dumps(kinds) + ";\n"
    script += "console.log(JSON.stringify(" + json.dumps([case[0] for case in cases]) + ".map(c => kinds.filter(k => hasLiveTourExportAccess(k, c)))));"
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == [case[1] for case in cases]


def test_purchase_report_link_uses_existing_authorized_revenue_destination():
    source = _source(LIVE_TOUR)
    revenue = _source(ROOT / "web-v2/src/pages/RevenuePage.jsx")
    assert "const canViewPurchaseReport = isAdmin || user?.permissions?.revenue_view === true" in source
    assert "if (!canViewPurchaseReport) return" in source
    assert "url.searchParams.set('page', 'revenue')" in source
    assert "url.hash = 'purchase-reconcile'" in source
    assert "reports: canPayment || canExport || canViewPurchaseReport" in source
    assert "key === 'reports' && !canPayment && !canExport && !canViewPurchaseReport" in source
    assert 'id="purchase-reconcile"' in revenue
    assert "document.getElementById('purchase-reconcile')?.scrollIntoView" in revenue


def test_live_tour_export_filters_are_optional_and_forwarded_to_the_api():
    source = _source(LIVE_TOUR)
    api = _source(API)

    assert "const EMPTY_EXPORT_FILTERS = { date_from: '', date_to: '', time_from: '', time_to: '' }" in source
    assert "const [exportFilters, setExportFilters] = useState(EMPTY_EXPORT_FILTERS)" in source
    assert 'aria-label="Bộ lọc thời gian xuất dữ liệu"' in source
    assert source.count('type="date"') >= 2
    assert source.count('type="time"') >= 2
    for key in ("date_from", "date_to", "time_from", "time_to"):
        assert f"exportFilters.{key}" in source
        assert f"'{key}'" in api

    export_flow = source[
        source.index("const exportData") : source.index("const removeSelectedEmployees")
    ]
    assert "FILTERED_EXPORT_KINDS.has(kind) ? compactExportQuery(exportFilters) : {}" in export_flow
    assert "veraApi.exportLiveTourExcel(kind, query)" in export_flow
    assert "veraApi.exportLiveTourPng(query)" in export_flow
    assert "query.date_from && query.date_to && query.date_from > query.date_to" in export_flow
    assert "query.time_from > query.time_to" not in export_flow
    assert "kind === 'board' && showHidden && canRecoverHidden" in export_flow
    assert "query.include_hidden = 'true'" in export_flow

    api_helper = api[
        api.index("function liveTourExportParams") : api.index("export const veraApi")
    ]
    assert "new URLSearchParams({ kind })" in api_helper
    assert "if (value) params.set(key, value)" in api_helper
    assert "'include_hidden'" in api_helper
    assert "liveTourExportParams(kind, query)" in api
    assert "liveTourExportParams('board', query)" in api


def test_live_tour_quick_booking_is_independent_and_uses_a_stable_employee_id():
    source = _source(LIVE_TOUR)
    stable_helper = source[
        source.index("function stableEmployeeId") : source.index("function recordId")
    ]
    submit = source[
        source.index("const submitModal") : source.index("const columns")
    ]

    assert "_employee_id" in stable_helper
    assert "employee_id" in stable_helper
    assert "row-" not in stable_helper
    quick_button = next(
        line for line in source.splitlines()
        if "Đặt lịch nhanh" in line and "openModal('quick_booking'" in line
    )
    assert "rowIds: []" in quick_button
    assert "selectedIds" not in quick_button
    assert "disabled={!canOperate}" in quick_button
    assert "if (modal.kind === 'quick_booking')" in submit
    assert "action = 'booking'" in submit
    assert "employee_id: stableEmployeeId(selectedQuickBookingRecord)" in submit


def test_live_tour_quick_booking_search_ignores_accents_and_keeps_vba_appointments():
    source = _source(LIVE_TOUR)

    assert "employee_id: '', employee_search: ''" in source
    assert "const needle = normalizedColumn(form.employee_search)" in source
    assert "normalizedColumn(cellValue(record, employeeColumn)).includes(needle)" in source
    assert "const selectedQuickBookingRecord" in source
    assert "Lịch hẹn hiện tại:" in source
    assert "Không có lịch hẹn" in source
    assert "const appointmentOptions = useMemo" in source
    assert 'type="text" list="live-tour-appointment-options"' in source
    assert "appointment: appointment" not in source
    assert "employee_search: name, appointment" in source
    assert 'type="datetime-local"' not in source


def test_live_tour_quick_booking_excludes_rows_the_server_would_reject():
    source = _source(LIVE_TOUR)
    helper = source[
        source.index("function isQuickBookingEligible") : source.index("function asArray")
    ]

    assert "stableEmployeeId(record)" in helper
    assert "record?._hidden" in helper
    assert "isCurrentlyOnBreak(record)" in helper
    assert "isRoomAssignmentActive(record)" in helper
    assert "'DI LAM'" in helper
    assert "shiftBucket(record, columns)" in helper
    assert "serviceNameColumn(columns)" in helper
    for status in ("DANG CHO", "DANG THUC HIEN", "DANG SU DUNG", "CHO THANH TOAN"):
        assert status in helper


def test_live_tour_pending_reminder_runs_on_zero_to_positive_then_every_15_minutes():
    source = _source(LIVE_TOUR)
    reminder_flow = source[
        source.index("const pendingReminderCount") : source.index("const toggleRow")
    ]

    assert "const PENDING_REMINDER_INTERVAL_MS = 15 * 60 * 1000" in source
    assert "previousCount === 0 && pendingReminderCount > 0" in reminder_flow
    assert "pendingCountRef.current = pendingReminderCount" in reminder_flow
    assert "if (pendingReminderCount === 0) setPendingReminder(null)" in reminder_flow
    assert "if (!hasPendingReminder) return undefined" in reminder_flow
    assert "announcePendingPayments(pendingCountRef.current)" in reminder_flow
    assert "window.clearInterval(pendingReminderTimerRef.current)" in reminder_flow
    assert "[announcePendingPayments, hasPendingReminder]" in reminder_flow


def test_live_tour_pending_reminder_is_accessible_and_opens_the_pending_panel():
    source = _source(LIVE_TOUR)

    assert 'role="status" aria-live="polite" aria-atomic="true"' in source
    assert "<span key={pendingReminder.id}>{pendingReminder.text}</span>" in source
    assert "onClick={openPendingPanel}" in source
    assert "setActivePanel('pending')" in source
    assert 'aria-controls="live-tour-pending-panel"' in source
    assert 'id="live-tour-pending-panel" role="tabpanel"' in source


def test_live_tour_cache_recursively_removes_customer_identity_and_action_results():
    source = _source(LIVE_TOUR)
    cache_helpers = source[
        source.index("const PRIVATE_CACHE_KEYS") : source.index("function normalizedColumn")
    ]

    for key in ("customer_id", "customer_name", "customer_phone", "phone"):
        assert f"'{key}'" in cache_helpers
    assert "value.map(sanitizeLiveTourCacheValue)" in cache_helpers
    assert "Object.entries(value).flatMap" in cache_helpers
    assert "delete safeData.result" in cache_helpers
    assert "combo_usage: []" in cache_helpers
    assert "combo_purchases: []" in cache_helpers
    assert "cacheSafeLiveTour(cached.data)" in cache_helpers
    assert "JSON.stringify({ savedAt: Date.now(), data: cacheSafeLiveTour(data) })" in cache_helpers


def test_live_tour_booking_pi_is_payment_gated_and_never_prefills_the_employee_name():
    source = _source(LIVE_TOUR)
    open_modal = source[source.index("const openModal") : source.index("const closeModal")]
    submit = source[source.index("const submitModal") : source.index("const columns")]

    assert "customer_name: source.customer_name ?? context.defaults?.customer_name ?? ''" in open_modal
    assert "customer_name: source.customer_name ?? source.name" not in open_modal
    assert "sourceIsCapturedEmployee ? source.customer_phone" in open_modal
    assert submit.count("...(canPayment ? { customer_id:") >= 3
    picker = source[source.index("const renderBookingCustomerPicker") : source.index("return <>", source.index("const renderBookingCustomerPicker"))]
    assert "if (!canPayment) return null" in picker
    assert source.count("{renderBookingCustomerPicker(") >= 3


def test_live_tour_checkout_uses_server_preview_without_sending_client_totals():
    source = _source(LIVE_TOUR)
    submit = source[source.index("const submitModal") : source.index("const columns")]
    checkout = submit[
        submit.index("} else if (['checkout', 'quick_checkout'].includes(modal.kind))") :
        submit.index("} else if (modal.kind === 'add_employee')")
    ]

    assert "previewEntryPrice(entry, services)" in source
    assert "previewEntryTicketUnits(entry, services)" in source
    assert "Dịch vụ và giá dự kiến từ dữ liệu server" in source
    assert "Giá, tổng tiền và số vé cuối cùng luôn do server tính lại" in source
    assert not re.search(r"\b(total|services|combo_units)\s*:", checkout)
    assert "ticket_price: ticketPrice" in checkout
    assert "checkoutRequiresTicketPrice" in checkout
    assert "checkoutAllZeroPricing" in source
    assert "checkoutHasMixedPricing" in source
    assert "Không thể thanh toán chung dịch vụ đã có giá với dịch vụ giá 0" in checkout
    assert "checkoutHasUnresolvedPricing" in checkout
    assert "max=\"1000000000\"" in source
    assert "payment_method: paymentMethod" in checkout
    assert "form.combo_purchase_id ? 'COMBO'" in checkout
    assert "Server sẽ trừ" in source and "vé combo" in source


def test_live_tour_combo_purchase_is_catalog_priced_and_supports_new_customers():
    source = _source(LIVE_TOUR)
    submit = source[source.index("const submitModal") : source.index("const columns")]
    purchase_payload = submit[
        submit.index("} else if (modal.kind === 'combo_purchase')") :
        submit.index("} else if (modal.kind === 'combo_import')")
    ]
    purchase_form = source[
        source.index("{modal.kind === 'combo_purchase' && <>") :
        source.index("{canAdmin && ['checkout', 'quick_checkout', 'combo_purchase']")
    ]

    assert "Mua combo cho khách mới" in source
    assert "newCustomer: true" in source
    assert "readOnly={!modal.newCustomer}" in purchase_form
    assert "comboPurchasePreviewAmount" in purchase_form
    assert "readOnly aria-readonly=\"true\"" in purchase_form
    assert "amount:" not in purchase_payload
    assert "form.amount" not in purchase_form
    assert "payment_method: form.payment_method" in purchase_payload
    assert "bill_no: form.bill_no" in purchase_payload
    assert "<option>CHUYỂN KHOẢN</option>" in purchase_form


def test_live_tour_checkout_can_link_an_exact_existing_customer_and_load_history():
    source = _source(LIVE_TOUR)
    api = _source(API)

    assert "const checkoutCustomerMatches" in source
    assert "checkoutCustomerNeedles.every" in source
    assert "customer_id: id, customer_name: itemLabel(customer)" in source
    assert "Đã liên kết đúng mã khách hàng" in source
    assert "const openCustomerHistory" in source
    assert "veraApi.liveTourCustomerHistory(customerId)" in source
    assert "const query = compactExportQuery(exportFilters)" in source
    assert "exportLiveTourExcel('customer_detail', { ...query, customer_id: customerId })" in source
    assert "liveTourCustomerHistory: (customerId)" in api
    assert "/v2/live-tour/customers/${encodeURIComponent(customerId)}/history" in api
    api_params = api[api.index("function liveTourExportParams") : api.index("export const veraApi")]
    assert "'customer_id'" in api_params


def test_live_tour_financial_correction_requires_admin_and_a_reason():
    source = _source(LIVE_TOUR)
    submit = source[source.index("const submitModal") : source.index("const columns")]

    assert "form.backdate_one_day" in submit
    assert "if (!canAdmin)" in submit
    assert "correctionReason.length < 3" in submit
    assert "payload.backdate_one_day = true" in submit
    assert "payload.correction_reason = correctionReason" in submit
    assert "Lùi 1 ngày (Admin)" in source
    assert "Lý do điều chỉnh" in source


def test_live_tour_quick_checkout_is_independent_and_uses_stable_employee_ids():
    source = _source(LIVE_TOUR)
    helper = source[
        source.index("function isQuickCheckoutEligible") : source.index("function asArray")
    ]
    button = next(
        line for line in source.splitlines()
        if ">Thanh toán nhanh</button>" in line and "openModal('quick_checkout', { rowIds: [] })" in line
    )

    assert "stableEmployeeId(record)" in helper
    assert "_payment_pending" in helper
    assert "CHO THANH TOAN" in helper
    assert "disabled={!canPayment}" in button
    assert "selectedIds.size" not in button
    assert "const quickCheckoutMatches" in source
    assert "[stableEmployeeId(selectedQuickCheckoutRecord)]" in source
    assert "Tìm nhân viên chờ thanh toán" in source
    assert "customer_id: employee?.customer_id || ''" in source
    assert "phone: employee?.customer_phone || ''" in source


def test_live_tour_exposes_all_supported_leave_sync_modes_and_structured_recovery():
    source = _source(LIVE_TOUR)
    sync_ui = source[source.index("onClick={() => syncLeaves('check')") : source.index("<div className=\"live-tour-action-group\"><strong>Thứ tự")]

    for sync_action in ("'check'", "'reason-only'", "'cleanup'", "'sync_all'"):
        assert f"syncLeaves({sync_action})" in sync_ui
    assert "Kiểm tra nguồn lịch nghỉ" in sync_ui
    assert "Dọn trạng thái nghỉ (Xóa)" in sync_ui
    assert "syncOutcome.sync.stats" in sync_ui
    assert "syncOutcome.sync.target.verified" in sync_ui
    assert "syncOutcome.merge.conflict_count" in sync_ui
    assert "syncOutcome.status.retriable" in sync_ui
    assert "syncOutcome.status.marker_persisted" in sync_ui
