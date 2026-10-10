import { confirmDialog } from '../lib/systemDialogs'
import useTablePage from '../lib/useTablePage'
import TablePager from '../components/TablePager'
import CustomerCountShareDialog from '../components/CustomerCountShareDialog'
import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import LiveTourFilters from '../components/LiveTourFilters'
import LiveTourRevenueSummary from '../components/LiveTourRevenueSummary'
import LiveTourEmployeeRevenueBreakdown from '../components/LiveTourEmployeeRevenueBreakdown'
import LiveTourPaidInvoiceDialog from '../components/LiveTourPaidInvoiceDialog'
import LiveTourReceipt from '../components/LiveTourReceipt'
import { defaultTourYesterdayFilters } from '../lib/liveTourFilters'
import { EMPTY_REPORT_PAGE, REPORT_PAGE_SIZE, reportReadQuery, adaptReportResponse, isLegacyReportResponse } from '../lib/liveTourReportPage'
import { invoiceMoneyValues } from '../lib/liveTourInvoiceMoney'
import './SpaManagementPage.css'
import './LiveTourReportsPage.css'

const money = v => `${Number(v || 0).toLocaleString('vi-VN')} đ`
const isRequestedBooking = row => String(row?.request || '').trim().toLocaleLowerCase('vi') === 'yc'
const performanceStart = (row, requestedColumn) => {
  const requested = isRequestedBooking(row)
  if (requestedColumn !== requested) return ''
  return requested ? (row.board_yc_started_at || row.started_at) : (row.board_started_at || row.started_at)
}
export default function LiveTourReportsPage({ user }) {
  usePageRefresh(() => tab === 'history' ? setHistoryRefresh(value => value + 1) : refresh(), () => Boolean(busy || loading || historyLoading || deletingHistory || activeContext))
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const allowed = user?.role === 'admin' || user?.permissions?.live_tour_reports_view === true
  const [result, setResult] = useState(null)
  const [historyResult, setHistoryResult] = useState(null)
  const [filters, setFilters] = useState(defaultTourYesterdayFilters)
  const [tab, setTab] = useState('revenue')
  const [performanceTiming, setPerformanceTiming] = useState('all')
  const [context, setContext] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [position, setPosition] = useState({ scope: '', page: 1 })
  const [historyRefresh, setHistoryRefresh] = useState(0)
  const [historyNotice, setHistoryNotice] = useState('')
  const [deletingHistory, setDeletingHistory] = useState(false)
  const [error, setError] = useState('')
  const [pdfFilters, setPdfFilters] = useState(null)
  const historyDateFrom = filters.date_from
  const historyDateTo = filters.date_to
  const historyEmployee = filters.employee
  const running = useRef(false), keys = useRef(new Map())
  const loadVersion = useRef(0), loadController = useRef(null), mounted = useRef(true), legacySnapshot = useRef(null)
  const identityKey = JSON.stringify([user?.id, user?.employee_username, user?.role, user?.permissions])
  const appliedFilters = useMemo(() => ({ ...filters, total_amount: tab === 'revenue' ? filters.total_amount : '', tip_amount: tab === 'tip' ? filters.tip_amount : '' }), [filters, tab])
  const scope = JSON.stringify([identityKey, tab, appliedFilters, performanceTiming])
  const page = position.scope === scope ? position.page : 1
  const query = useMemo(() => reportReadQuery(appliedFilters, tab, performanceTiming, page), [appliedFilters, tab, performanceTiming, page])
  const queryKey = JSON.stringify([identityKey, query])
  const data = result?.scope === scope ? result.data : EMPTY_REPORT_PAGE
  const activeContext = context?.identityKey === identityKey ? context : null
  const activeReceipt = receipt?.identityKey === identityKey ? receipt : null
  const activePdfFilters = pdfFilters?.identityKey === identityKey ? pdfFilters.filters : null
  const historyScope = JSON.stringify([identityKey, historyDateFrom, historyDateTo, historyEmployee])
  const history = historyResult?.scope === historyScope ? historyResult.data : { rows: EMPTY_REPORT_PAGE.rows, columns: EMPTY_REPORT_PAGE.rows }
  const reportGrants = result?.identityKey === identityKey ? result.data.capabilities : null
  // Old history responses predate capabilities. Once that authorized read has
  // succeeded, use retained report grants or only the verified shell export bit.
  const grants = tab === 'history' && historyResult?.identityKey === identityKey
    ? Object.hasOwn(historyResult.data, 'capabilities') ? historyResult.data.capabilities || {}
      : reportGrants ?? { export: isAdmin || user?.permissions?.live_tour_export === true }
    : reportGrants || {}
  const load = useCallback(async ({ refresh = false } = {}) => {
    if (!mounted.current || !allowed || tab === 'history') return
    const version = ++loadVersion.current
    loadController.current?.abort()
    const controller = new AbortController()
    loadController.current = controller
    setLoading(true)
    // A failed refresh must not resurrect a pre-edit legacy financial snapshot.
    if (refresh) { legacySnapshot.current = null; setResult(null) }
    try {
      // A legacy server already returned its full snapshot. Reuse it for local
      // filter/page changes; refresh and committed edits recheck the API contract.
      const cached = !refresh && legacySnapshot.current?.identityKey === identityKey ? legacySnapshot.current.data : null
      const response = cached || await veraApi.liveTourReports(query, { signal: controller.signal })
      if (version === loadVersion.current && !controller.signal.aborted) {
        const adapted = adaptReportResponse(response, query)
        legacySnapshot.current = isLegacyReportResponse(response) ? { identityKey, data: response } : null
        setResult({ queryKey, identityKey, scope, data: adapted })
      }
    } catch (e) { if (version === loadVersion.current && !controller.signal.aborted) throw e }
    finally { if (version === loadVersion.current) setLoading(false) }
  }, [allowed, tab, query, queryKey, identityKey, scope])
  const latestLoad = useRef(load)
  latestLoad.current = load
  useEffect(() => {
    setContext(null); setReceipt(null); setPdfFilters(null); legacySnapshot.current = null
  }, [identityKey])
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  useEffect(() => {
    setError('')
    setLoading(false)
    load().catch(e => setError(e.message))
    return () => { loadVersion.current += 1; loadController.current?.abort() }
  }, [load])
  useEffect(() => {
    if (result?.queryKey === queryKey && page > data.pages) setPosition({ scope, page: data.pages })
  }, [result, queryKey, page, data.pages, scope])
  useEffect(() => {
    if (!allowed || tab !== 'history') { setHistoryLoading(false); return undefined }
    const controller = new AbortController()
    setHistoryLoading(true); setError('')
    veraApi.liveTourBoardHistory({ date_from: historyDateFrom, date_to: historyDateTo, employee: historyEmployee }, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setHistoryResult({ data: value, scope: historyScope, identityKey }) })
      .catch(e => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setHistoryLoading(false) })
    return () => { controller.abort() }
  }, [allowed, historyDateFrom, historyDateTo, historyEmployee, tab, historyRefresh, identityKey, historyScope])
  const cleanupHistory = async () => {
    if (deletingHistory) return
    setDeletingHistory(true); setError(''); setHistoryNotice('')
    const scope = { date_from: historyDateFrom || null, date_to: historyDateTo || null, employee: historyEmployee || '' }
    try {
      const preview = await veraApi.previewBoardHistoryCleanup(scope)
      if (!preview.count) { setHistoryNotice('Không có lịch sử khớp bộ lọc.'); return }
      const dates = `${scope.date_from ? formatVeraDate(scope.date_from) : 'Tất cả'} → ${scope.date_to ? formatVeraDate(scope.date_to) : 'Tất cả'}`
      if (!(await confirmDialog(`Xóa vĩnh viễn ${preview.count} bản ghi lịch sử bảng tua?\n${dates}\nNhân viên: ${scope.employee || 'Tất cả'}\nKhông thể hoàn tác. Dữ liệu bảng tua hiện tại và hóa đơn vẫn được giữ nguyên.`))) return
      const result = await veraApi.deleteBoardHistory({ ...scope, cutoff_id: preview.cutoff_id, confirm: true })
      setHistoryNotice(`Đã xóa ${result.deleted} bản ghi lịch sử.`)
      setHistoryRefresh(value => value + 1)
    } catch (e) { setError(e.message) } finally { setDeletingHistory(false) }
  }
  const act = async (action, payload, _ids, options) => {
    if (running.current) return null
    running.current = true; setBusy(true); setError('')
    const mapped = action.replace('paid_invoice_', 'report_invoice_')
    const signature = JSON.stringify([mapped, payload])
    if (!keys.current.has(signature)) keys.current.set(signature, crypto.randomUUID())
    try {
      const result = await veraApi.liveTourAction({ action: mapped, payload, expected_revision: options.expectedRevision, idempotency_key: keys.current.get(signature), response_view: 'receipt' })
      keys.current.delete(signature);
      legacySnapshot.current = null; setResult(null)
      // The receipt confirms a committed write. Close the editor immediately;
      // fetching the report is a separate read and cannot turn success into failure.
      latestLoad.current({ refresh: true }).catch(() => setError('Đã lưu điều chỉnh. Bấm Làm mới để tải dữ liệu mới nhất.'))
      return result
    } catch (e) { setError(e.message); return null }
    finally { running.current = false; setBusy(false) }
  }
  const invoiceById = useMemo(() => new Map(data.invoices.map(invoice => [invoice.id, invoice])), [data.invoices])
  const rows = tab === 'history' ? history.rows : result?.queryKey === queryKey ? data.rows : EMPTY_REPORT_PAGE.rows
  const historyPagination = useTablePage(history.rows, historyScope)
  const pagination = tab === 'history' ? historyPagination : {
    rows, page, pages: data.pages, total: data.total, pageSize: REPORT_PAGE_SIZE,
    setPage: value => setPosition({ scope, page: Math.max(1, Math.min(value, data.pages)) }),
  }
  const refresh = async () => {
    if (tab === 'history') { setHistoryRefresh(value => value + 1); return }
    setBusy(true); setError('')
    try { await load({ refresh: true }) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  if (!allowed) return <div data-ui-key="u-58587e19c2e9" className="panel">Tài khoản chưa có quyền Xem báo cáo.</div>
  return <div className="feature-page spa-page live-tour-reports-page" data-report-read-mode={data.read_mode || 'loading'}>
    {activePdfFilters && <CustomerCountShareDialog key={identityKey} filters={activePdfFilters} onClose={() => setPdfFilters(null)}/>}
    <div data-ui-key="u-9e11e35c221d" className="page-heading"><div><span className="eyebrow">VERA SPA</span><h1>Báo cáo</h1><p>Hóa đơn, doanh thu, TIP và các giao dịch combo.</p></div><button data-ui-key="u-801a859b2628" data-ui-label-default="Làm mới" className="secondary-button" disabled={busy || loading || historyLoading} onClick={refresh}><UiCustomText uiKey="u-801a859b2628">Làm mới</UiCustomText></button></div>
    <StableFeedback>{(loading || historyLoading) && <p role="status">Đang cập nhật báo cáo…</p>}{error && <p className="error-box" role="alert">{error}</p>}</StableFeedback>
    <section data-ui-key="u-cc5b99345633" className="panel spa-content">
      <UiToolbar data-ui-key="u-ad5f380e835e" className="spa-tabs" role="tablist" aria-label="Loại báo cáo">{[['revenue', 'Doanh thu'], ['employee', 'Theo nhân viên'], ...(isAdmin ? [['tip', 'Tiền Tip'], ['performance', 'Thời gian dịch vụ']] : []), ['combos', 'Combo'], ['history', 'Lịch sử Live Tour']].map(([key,label]) => <button data-ui-key="u-a7458184ac7f" key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}</UiToolbar>
      <div className={tab === 'history' ? 'history-filter-scope' : ''}><LiveTourFilters showDate={tab !== 'history'} value={filters} onChange={setFilters} showTotal={tab === 'revenue'} showTip={tab === 'tip'} rows={rows}/></div>
      {tab !== 'history' && <p className="report-filter-hint">Gợi ý từ trang hiện tại. Nhập để tìm trong toàn bộ báo cáo.</p>}
      {tab === 'performance' && <div className="performance-status-filter" role="group" aria-label="Lọc kết quả thời gian dịch vụ">{[['all', 'Tất cả'], ['ontime', 'Đúng giờ'], ['late', 'Trễ'], ['early', 'Sớm']].map(([key, label]) => <button data-ui-key="u-ee49af6dd36a" type="button" key={key} className="secondary-button" aria-pressed={performanceTiming === key} onClick={() => setPerformanceTiming(key)}>{label}</button>)}</div>}
      {tab === 'tip' && <div className="live-tour-report-metrics"><div className="live-tour-report-metric"><span>Nhân viên có Tip</span><strong>{data.summary.tipEmployeeCount}</strong></div><div className="live-tour-report-metric"><span>Tổng tiền Tip</span><strong>{money(data.summary.tip)}</strong></div></div>}
      {tab === 'revenue' && <LiveTourRevenueSummary summary={data.summary}/>}
      {tab === 'employee' && <LiveTourEmployeeRevenueBreakdown summary={data.employee_totals}/>}
      {tab !== 'performance' && <p>{tab === 'history' ? rows.length : data.total} dòng</p>}
      <UiToolbar className="report-summary-toolbar">
      <div className="report-export-actions">
      {grants.export && <button data-ui-key="u-7dae37cfbfcd" data-ui-label-default="Xuất excel" className="secondary-button" onClick={() => (tab === 'history' ? veraApi.exportLiveTourBoardHistory(filters) : veraApi.exportLiveTourExcel(tab === 'tip' ? 'tip' : tab === 'performance' ? 'performance' : tab === 'employee' ? 'employee' : 'reports', { ...appliedFilters, preset: '', ...(tab === 'combos' ? { report_kind: 'combos' } : {}), ...(tab === 'performance' ? { performance_timing: performanceTiming } : {}) })).catch(e => setError(e.message))}><UiCustomText uiKey="u-7dae37cfbfcd">Xuất excel</UiCustomText></button>}
      {tab === 'revenue' && grants.export && <button type="button" data-ui-key="u-customer-count-pdf" className="primary-button report-share-pdf-button" disabled={busy || loading} onClick={() => setPdfFilters({ filters: { ...appliedFilters }, identityKey })}>Chia sẻ số khách · PDF</button>}
      </div>
      {tab === 'revenue' && <div className="live-tour-report-extra-metrics" aria-label="Thống kê hóa đơn theo bộ lọc"><div><span>Hóa đơn chưa thanh toán</span><strong>{grants.pending_view && grants.invoice_view ? data.summary.pendingInvoiceCount ?? '—' : '—'}</strong></div><div><span>Hóa đơn tổng tiền = 0</span><strong>{data.summary.zeroInvoices}</strong></div><div><span>Tổng giảm giá</span><strong>{money(data.summary.discount)}</strong></div></div>}
      {tab !== 'employee' && <TablePager pagination={pagination} label="Báo cáo" alwaysVisible/>}
      </UiToolbar>
      {tab === 'invoices' && !grants.paid_invoice_view && <p>Cần quyền Xem hóa đơn đã thanh toán để mở báo cáo hóa đơn.</p>}
      {tab === 'history' && isAdmin && <button data-ui-key="u-77eae750dea1" className="danger-button" disabled={busy || deletingHistory || historyLoading} onClick={cleanupHistory}>{deletingHistory ? 'Đang xử lý…' : 'Xóa lịch sử theo bộ lọc'}</button>}
      <StableFeedback>{tab === 'history' && historyNotice && <p role="status">{historyNotice}</p>}</StableFeedback>
      {tab === 'history' && <div className="responsive-data-table live-tour-history-table"><table data-ui-key="u-48afbbb5e074"><thead><tr><th data-ui-key="u-5e35ef2cfcb2" data-ui-label-default="Ngày"><UiCustomText uiKey="u-5e35ef2cfcb2">Ngày</UiCustomText></th><th data-ui-key="u-2f9a4ecbc2a7" data-ui-label-default="Giờ"><UiCustomText uiKey="u-2f9a4ecbc2a7">Giờ</UiCustomText></th><th data-ui-key="u-82554cd980ae" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-82554cd980ae">Nhân viên</UiCustomText></th><th data-ui-key="u-94e16131b619" data-ui-label-default="Người thao tác"><UiCustomText uiKey="u-94e16131b619">Người thao tác</UiCustomText></th><th data-ui-key="u-8769603feee2" data-ui-label-default="Hành động"><UiCustomText uiKey="u-8769603feee2">Hành động</UiCustomText></th><th data-ui-key="u-695833d58542" data-ui-label-default="Cột thay đổi"><UiCustomText uiKey="u-695833d58542">Cột thay đổi</UiCustomText></th>{history.columns.map(column => <th data-ui-key="u-382f396e1a6e" key={column}>{column}</th>)}</tr></thead><tbody>{pagination.rows.map(row => <tr key={row.id}><td>{row.changed_date_label || row.changed_at_label?.split(' ')[0]}</td><td>{row.changed_time_label || row.changed_at_label?.split(' ')[1]}</td><td><strong>{row.employee_name}</strong></td><td>{row.actor || 'Hệ thống'}</td><td>{row.action}</td><td>{(row.changed_columns || []).join(', ') || '—'}</td>{history.columns.map(column => <td key={column}>{row.changed_columns?.includes(column) && row.before?.[column] !== undefined ? <><small>{String(row.before?.[column] ?? '—')}</small><br/><strong>{String(row.after?.[column] ?? '—')}</strong></> : String(row.after?.[column] ?? row.before?.[column] ?? '—')}</td>)}</tr>)}</tbody></table></div>}
      {tab !== 'employee' && tab !== 'history' && (tab === 'performance' ? <div className="responsive-data-table live-tour-report-table performance-report-table"><table data-ui-key="u-f2da963e5c35"><thead><tr><th data-ui-key="u-b3569a36e464" data-ui-label-default="Nhân viên / dịch vụ"><UiCustomText uiKey="u-b3569a36e464">Nhân viên / dịch vụ</UiCustomText></th><th data-ui-key="u-5b5eab3eb26f" data-ui-label-default="Booking"><UiCustomText uiKey="u-5b5eab3eb26f">Booking</UiCustomText></th><th data-ui-key="u-758efc84d79d" data-ui-label-default="TG bắt đầu thực hiện"><UiCustomText uiKey="u-758efc84d79d">TG bắt đầu thực hiện</UiCustomText></th><th data-ui-key="u-28590208a06b" data-ui-label-default="TG bắt đầu thực hiện YC"><UiCustomText uiKey="u-28590208a06b">TG bắt đầu thực hiện YC</UiCustomText></th><th data-ui-key="u-14a27c2fe79e" data-ui-label-default="Hoàn thành"><UiCustomText uiKey="u-14a27c2fe79e">Hoàn thành</UiCustomText></th><th data-ui-key="u-ad92fbd067f7" data-ui-label-default="Quy định"><UiCustomText uiKey="u-ad92fbd067f7">Quy định</UiCustomText></th><th data-ui-key="u-cba24e881324" data-ui-label-default="Thực tế"><UiCustomText uiKey="u-cba24e881324">Thực tế</UiCustomText></th><th data-ui-key="u-dbad5aa81df7" data-ui-label-default="Kết quả"><UiCustomText uiKey="u-dbad5aa81df7">Kết quả</UiCustomText></th><th data-ui-key="u-d8920956d970" data-ui-label-default="TG Xông Hơi"><UiCustomText uiKey="u-d8920956d970">TG Xông Hơi</UiCustomText></th></tr></thead><tbody>{pagination.rows.map(row => <tr key={row.id}><td data-label="Nhân viên / dịch vụ"><strong>{row.employee_name}</strong><br/>{[row.service, row.room].filter(Boolean).join(' · ')}{row.booking_note && <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>Ghi chú booking: {row.booking_note}</div>}</td><td data-label="Booking">{formatVeraDateTime(row.booked_at)}</td><td data-label="TG bắt đầu thực hiện">{formatVeraDateTime(performanceStart(row, false))}</td><td data-label="TG bắt đầu thực hiện YC">{formatVeraDateTime(performanceStart(row, true))}</td><td data-label="Hoàn thành">{formatVeraDateTime(row.completed_at)}</td><td data-label="Quy định">{row.duration == null ? '—' : `${row.duration} phút`}</td><td data-label="Thực tế">{row.actual_duration_minutes} phút</td><td data-label="Kết quả"><span className={Number(row.completion_delta_minutes) < 0 ? 'report-early' : Number(row.completion_delta_minutes) > 0 ? 'report-late' : 'report-ontime'}>{row.completion_result}</span></td><td data-label="TG Xông Hơi">{row.steam_minutes == null ? '—' : `${row.steam_minutes} phút`}</td></tr>)}</tbody></table></div> : <div className="responsive-data-table live-tour-report-table"><table data-ui-key="u-d03584ec2dff"><thead><tr><th data-ui-key="u-c511da5cd528" data-ui-label-default="Ngày giờ hóa đơn"><UiCustomText uiKey="u-c511da5cd528">Ngày giờ hóa đơn</UiCustomText></th><th data-ui-key="u-02c82b3dc8a3" data-ui-label-default="Hóa đơn / khách hàng"><UiCustomText uiKey="u-02c82b3dc8a3">Hóa đơn / khách hàng</UiCustomText></th><th data-ui-key="u-a79d19f13b4d" data-ui-label-default="Nhân viên / dịch vụ / phòng"><UiCustomText uiKey="u-a79d19f13b4d">Nhân viên / dịch vụ / phòng</UiCustomText></th>{tab !== 'tip' && <><th data-ui-key="u-3d09af303979" data-ui-label-default="Tiền dịch vụ" className="report-money-column"><UiCustomText uiKey="u-3d09af303979">Tiền dịch vụ</UiCustomText></th><th data-ui-key="u-7c39d2a9327f" data-ui-label-default="Giảm giá" className="report-money-column"><UiCustomText uiKey="u-7c39d2a9327f">Giảm giá</UiCustomText></th></>}<th data-ui-key="u-ae41b83fe0c2" data-ui-label-default="Tiền Tip" className="report-money-column"><UiCustomText uiKey="u-ae41b83fe0c2">Tiền Tip</UiCustomText></th>{tab !== 'tip' && <th data-ui-key="u-9d5d83332a57" data-ui-label-default="Tổng tiền" className="report-money-column"><UiCustomText uiKey="u-9d5d83332a57">Tổng tiền</UiCustomText></th>}<th data-ui-key="u-759cbaffd995" data-ui-label-default="Thao tác" className="report-actions-column"><UiCustomText uiKey="u-759cbaffd995">Thao tác</UiCustomText></th></tr></thead><tbody>{pagination.rows.map(row => {
        const invoice = tab === 'invoices' ? row : invoiceById.get(row.invoice_id)
        const amounts = invoiceMoneyValues(invoice || row)
        return <tr key={row.id}><td data-label="Ngày giờ hóa đơn">{formatVeraDateTime(row.effective_at || row.business_date)}</td><td data-label="Hóa đơn / khách hàng">{row.bill_no}<br/>{row.customer_name || 'Khách lẻ'}{row.note && <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>Ghi chú hóa đơn: {row.note}</div>}</td><td data-label="Nhân viên / dịch vụ / phòng">{row.entries ? row.entries.map((entry, index) => <div key={index}>{[entry.employee_name, entry.service, entry.room].filter(Boolean).join(' · ')}{entry.note && <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>Ghi chú booking: {entry.note}</div>}</div>) : <>{[row.employee_name, row.service, row.room].filter(Boolean).join(' · ')}{row.booking_note && <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>Ghi chú booking: {row.booking_note}</div>}</>}</td>{tab !== 'tip' && <><td className="report-money-cell" data-label="Tiền dịch vụ">{money(amounts.service)}</td><td className="report-money-cell" data-label="Giảm giá">{money(amounts.discount)}</td></>}<td className="report-money-cell" data-label="Tiền Tip">{money(row.tip ?? amounts.tip)}</td>{tab !== 'tip' && <td className="report-money-cell report-total-cell" data-label="Tổng tiền">{money(amounts.total)}</td>}<td className="report-actions-cell" data-label="Thao tác">{invoice && <UiToolbar data-ui-key="u-70ed053ad7b0" className="spa-actions report-invoice-actions"><button data-ui-key="u-4364fc470e5e" data-ui-label-default="Xem" className="secondary-button" aria-label="Xem hóa đơn" title="Xem hóa đơn" disabled={busy || loading} onClick={() => setReceipt({ invoice, paymentSettings: data.payment_settings, identityKey })}><UiCustomText uiKey="u-4364fc470e5e">Xem</UiCustomText></button>{grants.reports_edit && <button data-ui-key="u-e6973c1a4bef" data-ui-label-default="Sửa" className="secondary-button" aria-label="Sửa báo cáo hóa đơn" title="Sửa báo cáo hóa đơn" disabled={busy || loading} onClick={() => { setError(''); setContext({ item: invoice, mode: 'edit', revision: data.revision, identityKey }) }}><UiCustomText uiKey="u-e6973c1a4bef">Sửa</UiCustomText></button>}{grants.reports_delete && <button data-ui-key="u-fd737e2f6f78" data-ui-label-default="Xóa" className="secondary-button danger-button" aria-label="Xóa báo cáo và hủy hóa đơn" title="Xóa báo cáo và hủy hóa đơn" disabled={busy || loading} onClick={() => { setError(''); setContext({ item: invoice, mode: 'delete', revision: data.revision, identityKey }) }}><UiCustomText uiKey="u-fd737e2f6f78">Xóa</UiCustomText></button>}</UiToolbar>}</td></tr>
      })}</tbody></table></div>)}
      {!loading && !historyLoading && !rows.length && <p>Không có dữ liệu phù hợp bộ lọc.</p>}
    </section>
    {activeContext && <LiveTourPaidInvoiceDialog key={`${activeContext.item.id}:${activeContext.mode}`} context={activeContext} busy={busy} error={error} onAction={act} isAdmin={isAdmin} canEditDate={isAdmin || grants.invoice_date_edit} onClose={() => setContext(null)}/>}
    {activeReceipt && <LiveTourReceipt invoice={activeReceipt.invoice} paymentSettings={activeReceipt.paymentSettings} onClose={() => setReceipt(null)}/>}
  </div>
}
