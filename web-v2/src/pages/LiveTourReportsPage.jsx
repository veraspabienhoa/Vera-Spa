import { formatVeraDateTime } from '../lib/veraDate'
import { useCallback, useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import LiveTourFilters from '../components/LiveTourFilters'
import LiveTourRevenueSummary from '../components/LiveTourRevenueSummary'
import LiveTourPaidInvoiceDialog from '../components/LiveTourPaidInvoiceDialog'
import LiveTourReceipt from '../components/LiveTourReceipt'
import { defaultTourMonthFilters, filterTourRows } from '../lib/liveTourFilters'
import { invoiceMoneyValues } from '../lib/liveTourInvoiceMoney'
import './SpaManagementPage.css'
import './LiveTourReportsPage.css'

const money = v => `${Number(v || 0).toLocaleString('vi-VN')} đ`
export default function LiveTourReportsPage({ user }) {
  const allowed = user?.role === 'admin' || user?.permissions?.live_tour_reports_view === true
  const [data, setData] = useState({ invoices: [], reports: [], capabilities: {} })
  const [filters, setFilters] = useState(defaultTourMonthFilters)
  const [tab, setTab] = useState('invoices')
  const [context, setContext] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const running = useRef(false), keys = useRef(new Map())
  const load = useCallback(async () => { const result = await veraApi.liveTourReports(); setData(result) }, [])
  useEffect(() => { if (allowed) load().catch(e => setError(e.message)) }, [allowed, load])
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
  const rows = tab === 'invoices' ? invoices : reports.filter(r => tab !== 'combos' || r.combo_sale || r.combo_units || /combo/i.test(r.service || ''))
  const grants = data.capabilities
  const refresh = async () => { setBusy(true); setError(''); try { await load() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  if (!allowed) return <div className="panel">Tài khoản chưa có quyền Xem báo cáo.</div>
  return <div className="feature-page spa-page">
    <div className="page-heading"><div><span className="eyebrow">VERA SPA</span><h1>Báo cáo</h1><p>Hóa đơn, doanh thu, TIP và các giao dịch combo.</p></div><button className="secondary-button" disabled={busy} onClick={refresh}>Làm mới</button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
    <section className="panel spa-content">
      <div className="spa-tabs" role="tablist" aria-label="Loại báo cáo">{[['invoices', 'Hóa đơn'], ['revenue', 'Doanh thu'], ['tip', 'Tiền TIP'], ['combos', 'Combo']].map(([key,label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>)}</div>
      <LiveTourFilters value={filters} onChange={setFilters} rows={tab === 'invoices' ? data.invoices : tab === 'combos' ? data.reports.filter(r => r.combo_sale || r.combo_units || /combo/i.test(r.service || '')) : data.reports}/>
      <LiveTourRevenueSummary rows={rows}/>
      <p>{rows.length} dòng</p>
      {grants.export && <button className="secondary-button" onClick={() => veraApi.exportLiveTourExcel(tab === 'invoices' ? 'revenue' : tab === 'tip' ? 'tip' : 'reports', { ...filters, preset: '', ...(tab === 'combos' ? { report_kind: 'combos' } : {}) }).catch(e => setError(e.message))}>Xuất Excel theo bộ lọc</button>}
      {tab === 'invoices' && !grants.paid_invoice_view && <p>Cần quyền Xem hóa đơn đã thanh toán để mở báo cáo hóa đơn.</p>}
      <div className="responsive-data-table live-tour-report-table"><table><thead><tr><th>Ngày giờ hóa đơn</th><th>Hóa đơn / khách hàng</th><th>Nhân viên / dịch vụ / phòng</th><th className="report-money-column">Tiền dịch vụ</th><th className="report-money-column">Giảm giá</th><th className="report-money-column">Tiền Tip</th><th className="report-money-column">Tổng tiền</th><th className="report-actions-column">Thao tác</th></tr></thead><tbody>{rows.map(row => {
        const invoice = tab === 'invoices' ? row : data.invoices.find(i => i.id === row.invoice_id)
        const amounts = invoiceMoneyValues(invoice || row)
        return <tr key={row.id}><td data-label="Ngày giờ hóa đơn">{formatVeraDateTime(row.effective_at || row.business_date)}</td><td data-label="Hóa đơn / khách hàng">{row.bill_no}<br/>{row.customer_name || 'Khách lẻ'}</td><td data-label="Nhân viên / dịch vụ / phòng">{row.entries ? row.entries.map(e => [e.employee_name, e.service, e.room].filter(Boolean).join(' · ')).join('; ') : [row.employee_name, row.service, row.room].filter(Boolean).join(' · ')}</td><td className="report-money-cell" data-label="Tiền dịch vụ">{money(amounts.service)}</td><td className="report-money-cell" data-label="Giảm giá">{money(amounts.discount)}</td><td className="report-money-cell" data-label="Tiền Tip">{money(amounts.tip)}</td><td className="report-money-cell report-total-cell" data-label="Tổng tiền">{money(amounts.total)}</td><td className="report-actions-cell" data-label="Thao tác">{invoice && <div className="spa-actions report-invoice-actions"><button className="secondary-button" aria-label="Xem hóa đơn" title="Xem hóa đơn" onClick={() => setReceipt(invoice)}>Xem</button>{grants.reports_edit && <button className="secondary-button" aria-label="Sửa báo cáo hóa đơn" title="Sửa báo cáo hóa đơn" disabled={busy} onClick={() => { setError(''); setContext({ item: invoice, mode: 'edit', revision: data.revision }) }}>Sửa</button>}{grants.reports_delete && <button className="secondary-button danger-button" aria-label="Xóa báo cáo và hủy hóa đơn" title="Xóa báo cáo và hủy hóa đơn" disabled={busy} onClick={() => { setError(''); setContext({ item: invoice, mode: 'delete', revision: data.revision }) }}>Xóa</button>}</div>}</td></tr>
      })}</tbody></table></div>
      {!rows.length && <p>Không có dữ liệu phù hợp bộ lọc.</p>}
    </section>
    {context && <LiveTourPaidInvoiceDialog key={`${context.item.id}:${context.mode}`} context={context} busy={busy} error={error} onAction={act} canEditDate={grants.invoice_date_edit} onClose={() => setContext(null)}/>}
    {receipt && <LiveTourReceipt invoice={receipt} paymentSettings={data.payment_settings} onClose={() => setReceipt(null)}/>}
  </div>
}
