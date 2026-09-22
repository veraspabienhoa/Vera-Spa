import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'
import { useCallback, useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import LiveTourFilters from '../components/LiveTourFilters'
import LiveTourRevenueSummary from '../components/LiveTourRevenueSummary'
import LiveTourEmployeeRevenueBreakdown from '../components/LiveTourEmployeeRevenueBreakdown'
import LiveTourPaidInvoiceDialog from '../components/LiveTourPaidInvoiceDialog'
import LiveTourReceipt from '../components/LiveTourReceipt'
import { defaultTourYesterdayFilters, filterTourRows } from '../lib/liveTourFilters'
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
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const allowed = user?.role === 'admin' || user?.permissions?.live_tour_reports_view === true
  const [data, setData] = useState({ invoices: [], reports: [], performance: [], capabilities: {} })
  const [history, setHistory] = useState({ rows: [], columns: [] })
  const [filters, setFilters] = useState(defaultTourYesterdayFilters)
  const [tab, setTab] = useState('revenue')
  const [performanceTiming, setPerformanceTiming] = useState('all')
  const [context, setContext] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [busy, setBusy] = useState(false)
  const [historyRefresh, setHistoryRefresh] = useState(0)
  const [historyNotice, setHistoryNotice] = useState('')
  const [deletingHistory, setDeletingHistory] = useState(false)
  const [error, setError] = useState('')
  const historyDateFrom = filters.date_from
  const historyDateTo = filters.date_to
  const historyEmployee = filters.employee
  const running = useRef(false), keys = useRef(new Map())
  const load = useCallback(async () => { const result = await veraApi.liveTourReports(); setData(result) }, [])
  useEffect(() => { if (allowed) load().catch(e => setError(e.message)) }, [allowed, load])
  useEffect(() => {
    if (!allowed || tab !== 'history') return undefined
    let active = true
    setBusy(true); setError('')
    veraApi.liveTourBoardHistory({ date_from: historyDateFrom, date_to: historyDateTo, employee: historyEmployee }).then(result => { if (active) setHistory(result) }).catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [allowed, historyDateFrom, historyDateTo, historyEmployee, tab, historyRefresh])
  const cleanupHistory = async () => {
    if (deletingHistory) return
    setDeletingHistory(true); setError(''); setHistoryNotice('')
    const scope = { date_from: historyDateFrom || null, date_to: historyDateTo || null, employee: historyEmployee || '' }
    try {
      const preview = await veraApi.previewBoardHistoryCleanup(scope)
      if (!preview.count) { setHistoryNotice('Không có lịch sử khớp bộ lọc.'); return }
      const dates = `${scope.date_from ? formatVeraDate(scope.date_from) : 'Tất cả'} → ${scope.date_to ? formatVeraDate(scope.date_to) : 'Tất cả'}`
      if (!window.confirm(`Xóa vĩnh viễn ${preview.count} bản ghi lịch sử bảng tua?\n${dates}\nNhân viên: ${scope.employee || 'Tất cả'}\nKhông thể hoàn tác. Dữ liệu bảng tua hiện tại và hóa đơn vẫn được giữ nguyên.`)) return
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
      const result = await veraApi.liveTourAction({ action: mapped, payload, expected_revision: options.expectedRevision, idempotency_key: keys.current.get(signature) })
      keys.current.delete(signature);
      try { await load() } catch { setError('Đã lưu điều chỉnh. Bấm Làm mới để tải dữ liệu mới nhất.') }
      return result
    } catch (e) { setError(e.message); return null }
    finally { running.current = false; setBusy(false) }
  }
  const invoices = filterTourRows(data.invoices, filters)
  const reports = filterTourRows(data.reports, filters)
  const performance = filterTourRows(data.performance || [], filters)
  const performanceRows = performance.filter(row => {
    if (performanceTiming === 'all') return true
    const delta = Number(row.completion_delta_minutes)
    if (performanceTiming === 'early') return delta < 0
    if (performanceTiming === 'late') return delta > 0
    return delta === 0
  })
  const rows = tab === 'history' ? history.rows : tab === 'performance' ? performanceRows : tab === 'tip'
    ? reports.filter(row => Number(row.tip || 0) > 0)
    : tab === 'invoices' ? invoices
      : reports.filter(row => tab !== 'combos' || row.combo_sale || row.combo_units || /combo/i.test(row.service || ''))
  const reportInvoiceCount = new Set(rows.map(row => String(row?.invoice_id || row?.bill_no || '').trim()).filter(Boolean)).size
  const grants = data.capabilities
  const refresh = async () => { setBusy(true); setError(''); try { await load() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  if (!allowed) return <div data-ui-key="u-58587e19c2e9" className="panel">Tài khoản chưa có quyền Xem báo cáo.</div>
  return <div className="feature-page spa-page live-tour-reports-page">
    <div data-ui-key="u-9e11e35c221d" className="page-heading"><div><span className="eyebrow">VERA SPA</span><h1>Báo cáo</h1><p>Hóa đơn, doanh thu, TIP và các giao dịch combo.</p></div><button data-ui-key="u-801a859b2628" data-ui-label-default="Làm mới" className="secondary-button" disabled={busy} onClick={refresh}><UiCustomText uiKey="u-801a859b2628">Làm mới</UiCustomText></button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
    <section data-ui-key="u-cc5b99345633" className="panel spa-content">
      <UiToolbar data-ui-key="u-ad5f380e835e" className="spa-tabs" role="tablist" aria-label="Loại báo cáo">{[['revenue', 'Doanh thu'], ['employee', 'Theo nhân viên'], ...(isAdmin ? [['tip', 'Tiền Tip'], ['performance', 'Thời gian dịch vụ']] : []), ['combos', 'Combo'], ['history', 'Lịch sử Live Tour']].map(([key,label]) => <button data-ui-key="u-a7458184ac7f" key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}</UiToolbar>
      <div className={tab === 'history' ? 'history-filter-scope' : ''}><LiveTourFilters value={filters} onChange={setFilters} rows={tab === 'history' ? history.rows : tab === 'performance' ? data.performance || [] : tab === 'combos' ? data.reports.filter(r => r.combo_sale || r.combo_units || /combo/i.test(r.service || '')) : data.reports}/></div>
      {tab === 'performance' && <div className="performance-status-filter" role="group" aria-label="Lọc kết quả thời gian dịch vụ">{[['all', 'Tất cả'], ['ontime', 'Đúng giờ'], ['late', 'Trễ'], ['early', 'Sớm']].map(([key, label]) => <button data-ui-key="u-ee49af6dd36a" type="button" key={key} className="secondary-button" aria-pressed={performanceTiming === key} onClick={() => setPerformanceTiming(key)}>{label}</button>)}</div>}
      {tab === 'tip' && <div className="live-tour-report-metrics"><div className="live-tour-report-metric"><span>Nhân viên có Tip</span><strong>{new Set(rows.map(row => row.employee_id || row.employee_name)).size}</strong></div><div className="live-tour-report-metric"><span>Tổng tiền Tip</span><strong>{money(rows.reduce((sum, row) => sum + Number(row.tip || 0), 0))}</strong></div></div>}
      {tab === 'revenue' && <LiveTourRevenueSummary rows={rows} invoiceCount={reportInvoiceCount}/>}
      {tab === 'employee' && <LiveTourEmployeeRevenueBreakdown rows={reports}/>}
      {tab !== 'performance' && <p>{rows.length} dòng</p>}
      {grants.export && <button data-ui-key="u-7dae37cfbfcd" data-ui-label-default="Xuất Excel theo bộ lọc" className="secondary-button" onClick={() => (tab === 'history' ? veraApi.exportLiveTourBoardHistory(filters) : veraApi.exportLiveTourExcel(tab === 'tip' ? 'tip' : tab === 'performance' ? 'performance' : tab === 'employee' ? 'employee' : 'reports', { ...filters, preset: '', ...(tab === 'combos' ? { report_kind: 'combos' } : {}), ...(tab === 'performance' ? { performance_timing: performanceTiming } : {}) })).catch(e => setError(e.message))}><UiCustomText uiKey="u-7dae37cfbfcd">Xuất Excel theo bộ lọc</UiCustomText></button>}
      {tab === 'invoices' && !grants.paid_invoice_view && <p>Cần quyền Xem hóa đơn đã thanh toán để mở báo cáo hóa đơn.</p>}
      {tab === 'history' && isAdmin && <button data-ui-key="u-77eae750dea1" className="danger-button" disabled={busy || deletingHistory} onClick={cleanupHistory}>{deletingHistory ? 'Đang xử lý…' : 'Xóa lịch sử theo bộ lọc'}</button>}
      {tab === 'history' && historyNotice && <p role="status">{historyNotice}</p>}
      {tab === 'history' && <div className="responsive-data-table live-tour-history-table"><table data-ui-key="u-48afbbb5e074"><thead><tr><th data-ui-key="u-5e35ef2cfcb2" data-ui-label-default="Ngày"><UiCustomText uiKey="u-5e35ef2cfcb2">Ngày</UiCustomText></th><th data-ui-key="u-2f9a4ecbc2a7" data-ui-label-default="Giờ"><UiCustomText uiKey="u-2f9a4ecbc2a7">Giờ</UiCustomText></th><th data-ui-key="u-82554cd980ae" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-82554cd980ae">Nhân viên</UiCustomText></th><th data-ui-key="u-94e16131b619" data-ui-label-default="Người thao tác"><UiCustomText uiKey="u-94e16131b619">Người thao tác</UiCustomText></th><th data-ui-key="u-8769603feee2" data-ui-label-default="Hành động"><UiCustomText uiKey="u-8769603feee2">Hành động</UiCustomText></th><th data-ui-key="u-695833d58542" data-ui-label-default="Cột thay đổi"><UiCustomText uiKey="u-695833d58542">Cột thay đổi</UiCustomText></th>{history.columns.map(column => <th data-ui-key="u-382f396e1a6e" key={column}>{column}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.changed_date_label || row.changed_at_label?.split(' ')[0]}</td><td>{row.changed_time_label || row.changed_at_label?.split(' ')[1]}</td><td><strong>{row.employee_name}</strong></td><td>{row.actor || 'Hệ thống'}</td><td>{row.action}</td><td>{(row.changed_columns || []).join(', ') || '—'}</td>{history.columns.map(column => <td key={column}>{row.changed_columns?.includes(column) && row.before?.[column] !== undefined ? <><small>{String(row.before?.[column] ?? '—')}</small><br/><strong>{String(row.after?.[column] ?? '—')}</strong></> : String(row.after?.[column] ?? row.before?.[column] ?? '—')}</td>)}</tr>)}</tbody></table></div>}
      {tab !== 'employee' && tab !== 'history' && (tab === 'performance' ? <div className="responsive-data-table live-tour-report-table performance-report-table"><table data-ui-key="u-f2da963e5c35"><thead><tr><th data-ui-key="u-b3569a36e464" data-ui-label-default="Nhân viên / dịch vụ"><UiCustomText uiKey="u-b3569a36e464">Nhân viên / dịch vụ</UiCustomText></th><th data-ui-key="u-5b5eab3eb26f" data-ui-label-default="Booking"><UiCustomText uiKey="u-5b5eab3eb26f">Booking</UiCustomText></th><th data-ui-key="u-758efc84d79d" data-ui-label-default="TG bắt đầu thực hiện"><UiCustomText uiKey="u-758efc84d79d">TG bắt đầu thực hiện</UiCustomText></th><th data-ui-key="u-28590208a06b" data-ui-label-default="TG bắt đầu thực hiện YC"><UiCustomText uiKey="u-28590208a06b">TG bắt đầu thực hiện YC</UiCustomText></th><th data-ui-key="u-14a27c2fe79e" data-ui-label-default="Hoàn thành"><UiCustomText uiKey="u-14a27c2fe79e">Hoàn thành</UiCustomText></th><th data-ui-key="u-ad92fbd067f7" data-ui-label-default="Quy định"><UiCustomText uiKey="u-ad92fbd067f7">Quy định</UiCustomText></th><th data-ui-key="u-cba24e881324" data-ui-label-default="Thực tế"><UiCustomText uiKey="u-cba24e881324">Thực tế</UiCustomText></th><th data-ui-key="u-dbad5aa81df7" data-ui-label-default="Kết quả"><UiCustomText uiKey="u-dbad5aa81df7">Kết quả</UiCustomText></th><th data-ui-key="u-d8920956d970" data-ui-label-default="TG Xông Hơi"><UiCustomText uiKey="u-d8920956d970">TG Xông Hơi</UiCustomText></th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td data-label="Nhân viên / dịch vụ"><strong>{row.employee_name}</strong><br/>{[row.service, row.room].filter(Boolean).join(' · ')}</td><td data-label="Booking">{formatVeraDateTime(row.booked_at)}</td><td data-label="TG bắt đầu thực hiện">{formatVeraDateTime(performanceStart(row, false))}</td><td data-label="TG bắt đầu thực hiện YC">{formatVeraDateTime(performanceStart(row, true))}</td><td data-label="Hoàn thành">{formatVeraDateTime(row.completed_at)}</td><td data-label="Quy định">{row.duration == null ? '—' : `${row.duration} phút`}</td><td data-label="Thực tế">{row.actual_duration_minutes} phút</td><td data-label="Kết quả"><span className={Number(row.completion_delta_minutes) < 0 ? 'report-early' : Number(row.completion_delta_minutes) > 0 ? 'report-late' : 'report-ontime'}>{row.completion_result}</span></td><td data-label="TG Xông Hơi">{row.steam_minutes == null ? '—' : `${row.steam_minutes} phút`}</td></tr>)}</tbody></table></div> : <div className="responsive-data-table live-tour-report-table"><table data-ui-key="u-d03584ec2dff"><thead><tr><th data-ui-key="u-c511da5cd528" data-ui-label-default="Ngày giờ hóa đơn"><UiCustomText uiKey="u-c511da5cd528">Ngày giờ hóa đơn</UiCustomText></th><th data-ui-key="u-02c82b3dc8a3" data-ui-label-default="Hóa đơn / khách hàng"><UiCustomText uiKey="u-02c82b3dc8a3">Hóa đơn / khách hàng</UiCustomText></th><th data-ui-key="u-a79d19f13b4d" data-ui-label-default="Nhân viên / dịch vụ / phòng"><UiCustomText uiKey="u-a79d19f13b4d">Nhân viên / dịch vụ / phòng</UiCustomText></th>{tab !== 'tip' && <><th data-ui-key="u-3d09af303979" data-ui-label-default="Tiền dịch vụ" className="report-money-column"><UiCustomText uiKey="u-3d09af303979">Tiền dịch vụ</UiCustomText></th><th data-ui-key="u-7c39d2a9327f" data-ui-label-default="Giảm giá" className="report-money-column"><UiCustomText uiKey="u-7c39d2a9327f">Giảm giá</UiCustomText></th></>}<th data-ui-key="u-ae41b83fe0c2" data-ui-label-default="Tiền Tip" className="report-money-column"><UiCustomText uiKey="u-ae41b83fe0c2">Tiền Tip</UiCustomText></th>{tab !== 'tip' && <th data-ui-key="u-9d5d83332a57" data-ui-label-default="Tổng tiền" className="report-money-column"><UiCustomText uiKey="u-9d5d83332a57">Tổng tiền</UiCustomText></th>}<th data-ui-key="u-759cbaffd995" data-ui-label-default="Thao tác" className="report-actions-column"><UiCustomText uiKey="u-759cbaffd995">Thao tác</UiCustomText></th></tr></thead><tbody>{rows.map(row => {
        const invoice = tab === 'invoices' ? row : data.invoices.find(i => i.id === row.invoice_id)
        const amounts = invoiceMoneyValues(invoice || row)
        return <tr key={row.id}><td data-label="Ngày giờ hóa đơn">{formatVeraDateTime(row.effective_at || row.business_date)}</td><td data-label="Hóa đơn / khách hàng">{row.bill_no}<br/>{row.customer_name || 'Khách lẻ'}</td><td data-label="Nhân viên / dịch vụ / phòng">{row.entries ? row.entries.map(e => [e.employee_name, e.service, e.room].filter(Boolean).join(' · ')).join('; ') : [row.employee_name, row.service, row.room].filter(Boolean).join(' · ')}</td>{tab !== 'tip' && <><td className="report-money-cell" data-label="Tiền dịch vụ">{money(amounts.service)}</td><td className="report-money-cell" data-label="Giảm giá">{money(amounts.discount)}</td></>}<td className="report-money-cell" data-label="Tiền Tip">{money(row.tip ?? amounts.tip)}</td>{tab !== 'tip' && <td className="report-money-cell report-total-cell" data-label="Tổng tiền">{money(amounts.total)}</td>}<td className="report-actions-cell" data-label="Thao tác">{invoice && <UiToolbar data-ui-key="u-70ed053ad7b0" className="spa-actions report-invoice-actions"><button data-ui-key="u-4364fc470e5e" data-ui-label-default="Xem" className="secondary-button" aria-label="Xem hóa đơn" title="Xem hóa đơn" onClick={() => setReceipt(invoice)}><UiCustomText uiKey="u-4364fc470e5e">Xem</UiCustomText></button>{grants.reports_edit && <button data-ui-key="u-e6973c1a4bef" data-ui-label-default="Sửa" className="secondary-button" aria-label="Sửa báo cáo hóa đơn" title="Sửa báo cáo hóa đơn" disabled={busy} onClick={() => { setError(''); setContext({ item: invoice, mode: 'edit', revision: data.revision }) }}><UiCustomText uiKey="u-e6973c1a4bef">Sửa</UiCustomText></button>}{grants.reports_delete && <button data-ui-key="u-fd737e2f6f78" data-ui-label-default="Xóa" className="secondary-button danger-button" aria-label="Xóa báo cáo và hủy hóa đơn" title="Xóa báo cáo và hủy hóa đơn" disabled={busy} onClick={() => { setError(''); setContext({ item: invoice, mode: 'delete', revision: data.revision }) }}><UiCustomText uiKey="u-fd737e2f6f78">Xóa</UiCustomText></button>}</UiToolbar>}</td></tr>
      })}</tbody></table></div>)}
      {!rows.length && <p>Không có dữ liệu phù hợp bộ lọc.</p>}
    </section>
    {context && <LiveTourPaidInvoiceDialog key={`${context.item.id}:${context.mode}`} context={context} busy={busy} error={error} onAction={act} canEditDate={grants.invoice_date_edit} onClose={() => setContext(null)}/>}
    {receipt && <LiveTourReceipt invoice={receipt} paymentSettings={data.payment_settings} onClose={() => setReceipt(null)}/>}
  </div>
}
