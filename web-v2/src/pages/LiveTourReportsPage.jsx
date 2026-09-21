import { formatVeraDateTime } from '../lib/veraDate'
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
  }, [allowed, historyDateFrom, historyDateTo, historyEmployee, tab])
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
  if (!allowed) return <div className="panel">Tài khoản chưa có quyền Xem báo cáo.</div>
  return <div className="feature-page spa-page live-tour-reports-page">
    <div className="page-heading"><div><span className="eyebrow">VERA SPA</span><h1>Báo cáo</h1><p>Hóa đơn, doanh thu, TIP và các giao dịch combo.</p></div><button className="secondary-button" disabled={busy} onClick={refresh}>Làm mới</button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
    <section className="panel spa-content">
      <div className="spa-tabs" role="tablist" aria-label="Loại báo cáo">{[['revenue', 'Doanh thu'], ['employee', 'Theo nhân viên'], ...(isAdmin ? [['tip', 'Tiền Tip'], ['performance', 'Thời gian dịch vụ']] : []), ['combos', 'Combo'], ['history', 'Lịch sử Live Tour']].map(([key,label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}</div>
      <div className={tab === 'history' ? 'history-filter-scope' : ''}><LiveTourFilters value={filters} onChange={setFilters} rows={tab === 'history' ? history.rows : tab === 'performance' ? data.performance || [] : tab === 'combos' ? data.reports.filter(r => r.combo_sale || r.combo_units || /combo/i.test(r.service || '')) : data.reports}/></div>
      {tab === 'performance' && <div className="performance-status-filter" role="group" aria-label="Lọc kết quả thời gian dịch vụ">{[['all', 'Tất cả'], ['ontime', 'Đúng giờ'], ['late', 'Trễ'], ['early', 'Sớm']].map(([key, label]) => <button type="button" key={key} className="secondary-button" aria-pressed={performanceTiming === key} onClick={() => setPerformanceTiming(key)}>{label}</button>)}</div>}
      {tab === 'tip' && <div className="live-tour-report-metrics"><div className="live-tour-report-metric"><span>Nhân viên có Tip</span><strong>{new Set(rows.map(row => row.employee_id || row.employee_name)).size}</strong></div><div className="live-tour-report-metric"><span>Tổng tiền Tip</span><strong>{money(rows.reduce((sum, row) => sum + Number(row.tip || 0), 0))}</strong></div></div>}
      {tab === 'performance' && <div className="live-tour-report-metrics"><div className="live-tour-report-metric"><span>Sớm</span><strong>{performance.filter(row => Number(row.completion_delta_minutes) < 0).length}</strong></div><div className="live-tour-report-metric"><span>Đúng giờ</span><strong>{performance.filter(row => Number(row.completion_delta_minutes) === 0).length}</strong></div><div className="live-tour-report-metric"><span>Trễ</span><strong>{performance.filter(row => Number(row.completion_delta_minutes) > 0).length}</strong></div></div>}
      {tab === 'revenue' && <LiveTourRevenueSummary rows={rows} invoiceCount={reportInvoiceCount}/>}
      {tab === 'employee' && <LiveTourEmployeeRevenueBreakdown rows={reports}/>}
      <p>{rows.length} dòng</p>
      {grants.export && tab !== 'performance' && <button className="secondary-button" onClick={() => (tab === 'history' ? veraApi.exportLiveTourBoardHistory(filters) : veraApi.exportLiveTourExcel(tab === 'tip' ? 'tip' : 'reports', { ...filters, preset: '', ...(tab === 'combos' ? { report_kind: 'combos' } : {}) })).catch(e => setError(e.message))}>Xuất Excel theo bộ lọc</button>}
      {tab === 'invoices' && !grants.paid_invoice_view && <p>Cần quyền Xem hóa đơn đã thanh toán để mở báo cáo hóa đơn.</p>}
      {tab === 'history' && <div className="responsive-data-table live-tour-history-table"><table><thead><tr><th>Ngày giờ</th><th>Nhân viên</th><th>Người thao tác</th><th>Hành động</th><th>Cột thay đổi</th>{history.columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.changed_at_label}</td><td><strong>{row.employee_name}</strong></td><td>{row.actor || 'Hệ thống'}</td><td>{row.action}</td><td>{(row.changed_columns || []).join(', ') || '—'}</td>{history.columns.map(column => <td key={column}>{row.changed_columns?.includes(column) && row.before?.[column] !== undefined ? <><small>{String(row.before?.[column] ?? '—')}</small><br/><strong>{String(row.after?.[column] ?? '—')}</strong></> : String(row.after?.[column] ?? row.before?.[column] ?? '—')}</td>)}</tr>)}</tbody></table></div>}
      {tab !== 'employee' && tab !== 'history' && (tab === 'performance' ? <div className="responsive-data-table live-tour-report-table performance-report-table"><table><thead><tr><th>Nhân viên / dịch vụ</th><th>Booking</th><th>TG bắt đầu thực hiện</th><th>TG bắt đầu thực hiện YC</th><th>Hoàn thành</th><th>Quy định</th><th>Thực tế</th><th>Kết quả</th><th>TG Xông Hơi</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td data-label="Nhân viên / dịch vụ"><strong>{row.employee_name}</strong><br/>{[row.service, row.room].filter(Boolean).join(' · ')}</td><td data-label="Booking">{formatVeraDateTime(row.booked_at)}</td><td data-label="TG bắt đầu thực hiện">{formatVeraDateTime(row.board_started_at || (row.request ? '' : row.started_at))}</td><td data-label="TG bắt đầu thực hiện YC">{formatVeraDateTime(row.board_yc_started_at || (row.request ? row.started_at : ''))}</td><td data-label="Hoàn thành">{formatVeraDateTime(row.completed_at)}</td><td data-label="Quy định">{row.duration == null ? '—' : `${row.duration} phút`}</td><td data-label="Thực tế">{row.actual_duration_minutes} phút</td><td data-label="Kết quả"><span className={Number(row.completion_delta_minutes) < 0 ? 'report-early' : Number(row.completion_delta_minutes) > 0 ? 'report-late' : 'report-ontime'}>{row.completion_result}</span></td><td data-label="TG Xông Hơi">{row.steam_minutes == null ? '—' : `${row.steam_minutes} phút`}</td></tr>)}</tbody></table></div> : <div className="responsive-data-table live-tour-report-table"><table><thead><tr><th>Ngày giờ hóa đơn</th><th>Hóa đơn / khách hàng</th><th>Nhân viên / dịch vụ / phòng</th>{tab !== 'tip' && <><th className="report-money-column">Tiền dịch vụ</th><th className="report-money-column">Giảm giá</th></>}<th className="report-money-column">Tiền Tip</th>{tab !== 'tip' && <th className="report-money-column">Tổng tiền</th>}<th className="report-actions-column">Thao tác</th></tr></thead><tbody>{rows.map(row => {
        const invoice = tab === 'invoices' ? row : data.invoices.find(i => i.id === row.invoice_id)
        const amounts = invoiceMoneyValues(invoice || row)
        return <tr key={row.id}><td data-label="Ngày giờ hóa đơn">{formatVeraDateTime(row.effective_at || row.business_date)}</td><td data-label="Hóa đơn / khách hàng">{row.bill_no}<br/>{row.customer_name || 'Khách lẻ'}</td><td data-label="Nhân viên / dịch vụ / phòng">{row.entries ? row.entries.map(e => [e.employee_name, e.service, e.room].filter(Boolean).join(' · ')).join('; ') : [row.employee_name, row.service, row.room].filter(Boolean).join(' · ')}</td>{tab !== 'tip' && <><td className="report-money-cell" data-label="Tiền dịch vụ">{money(amounts.service)}</td><td className="report-money-cell" data-label="Giảm giá">{money(amounts.discount)}</td></>}<td className="report-money-cell" data-label="Tiền Tip">{money(row.tip ?? amounts.tip)}</td>{tab !== 'tip' && <td className="report-money-cell report-total-cell" data-label="Tổng tiền">{money(amounts.total)}</td>}<td className="report-actions-cell" data-label="Thao tác">{invoice && <div className="spa-actions report-invoice-actions"><button className="secondary-button" aria-label="Xem hóa đơn" title="Xem hóa đơn" onClick={() => setReceipt(invoice)}>Xem</button>{grants.reports_edit && <button className="secondary-button" aria-label="Sửa báo cáo hóa đơn" title="Sửa báo cáo hóa đơn" disabled={busy} onClick={() => { setError(''); setContext({ item: invoice, mode: 'edit', revision: data.revision }) }}>Sửa</button>}{grants.reports_delete && <button className="secondary-button danger-button" aria-label="Xóa báo cáo và hủy hóa đơn" title="Xóa báo cáo và hủy hóa đơn" disabled={busy} onClick={() => { setError(''); setContext({ item: invoice, mode: 'delete', revision: data.revision }) }}>Xóa</button>}</div>}</td></tr>
      })}</tbody></table></div>)}
      {!rows.length && <p>Không có dữ liệu phù hợp bộ lọc.</p>}
    </section>
    {context && <LiveTourPaidInvoiceDialog key={`${context.item.id}:${context.mode}`} context={context} busy={busy} error={error} onAction={act} canEditDate={grants.invoice_date_edit} onClose={() => setContext(null)}/>}
    {receipt && <LiveTourReceipt invoice={receipt} paymentSettings={data.payment_settings} onClose={() => setReceipt(null)}/>}
  </div>
}
