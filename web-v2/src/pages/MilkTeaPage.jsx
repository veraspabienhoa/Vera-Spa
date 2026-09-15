import { useCallback, useEffect, useMemo, useState } from 'react'
import VeraDateInput from '../components/VeraDateInput'
import { veraApi } from '../lib/api'
import { filterTourRows, TOUR_DATE_PRESETS, tourDateRange } from '../lib/liveTourFilters'
import { formatVeraDateTime } from '../lib/veraDate'

const money = value => `${Number(value || 0).toLocaleString('vi-VN')} đ`
const initialFilters = () => ({ preset: 'today', ...tourDateRange('today'), employee: '', customer: '', service: '', bill_no: '' })

export default function MilkTeaPage({ user }) {
  const allowed = ['leader', 'nhanvien'].includes(String(user?.role || '').toLowerCase())
  const [data, setData] = useState({ rows: [] })
  const [filters, setFilters] = useState(initialFilters)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    setBusy(true); setError('')
    try { setData(await veraApi.liveTourMyTips()) }
    catch (err) { setError(err.message || 'Không tải được tiền Tip.') }
    finally { setBusy(false) }
  }, [])
  useEffect(() => { if (allowed) void load() }, [allowed, load])
  const rows = useMemo(() => filterTourRows(data.rows || [], filters), [data.rows, filters])
  const total = rows.reduce((sum, row) => sum + Number(row.tip || 0), 0)
  const changePreset = preset => setFilters(current => ({ ...current, preset, ...tourDateRange(preset) }))
  if (!allowed) return <div className="panel">Chỉ tài khoản Leader và Nhân viên được xem Trà sữa của chính mình.</div>
  return <div className="feature-page spa-page milk-tea-page">
    <div className="page-heading"><div><span className="eyebrow">VERA SPA</span><h1>Trà sữa</h1><p>Tiền Tip của riêng tài khoản {user?.employee_username || ''}; không hiển thị tiền dịch vụ.</p></div><button className="secondary-button" disabled={busy} onClick={load}>{busy ? 'Đang tải…' : 'Làm mới'}</button></div>
    {error && <div className="error-box" role="alert">{error}</div>}
    <section className="panel spa-content">
      <div className="milk-tea-filters">
        <label><span>Thời gian</span><select value={filters.preset} onChange={event => changePreset(event.target.value)}>{TOUR_DATE_PRESETS.filter(([id]) => id !== 'all').map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        <label><span>Từ ngày</span><VeraDateInput value={filters.date_from} max={filters.date_to || undefined} onChange={event => setFilters(current => ({ ...current, date_from: event.target.value, preset: 'custom' }))}/></label>
        <label><span>Đến ngày</span><VeraDateInput value={filters.date_to} min={filters.date_from || undefined} onChange={event => setFilters(current => ({ ...current, date_to: event.target.value, preset: 'custom' }))}/></label>
      </div>
      <div className="milk-tea-summary"><span>Số hóa đơn<strong>{rows.length}</strong></span><span>Tiền Tip<strong>{money(total)}</strong></span></div>
      <div className="responsive-data-table milk-tea-table"><table><thead><tr><th>Ngày giờ hóa đơn</th><th>Số hóa đơn</th><th>Dịch vụ</th><th>Phòng</th><th>Tiền Tip</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td data-label="Ngày giờ hóa đơn">{formatVeraDateTime(row.effective_at || row.business_date)}</td><td data-label="Số hóa đơn">{row.bill_no || '—'}</td><td data-label="Dịch vụ">{(row.services || []).join(', ') || '—'}</td><td data-label="Phòng">{(row.rooms || []).join(', ') || '—'}</td><td data-label="Tiền Tip"><strong>{money(row.tip)}</strong></td></tr>)}</tbody></table></div>
      {!rows.length && !busy && <p>Không có tiền Tip trong khoảng thời gian đã chọn.</p>}
    </section>
    <style>{`.milk-tea-filters{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:10px;margin-bottom:14px}.milk-tea-filters label{display:grid;gap:5px}.milk-tea-summary{display:grid;grid-template-columns:repeat(2,minmax(150px,1fr));gap:10px;margin:12px 0}.milk-tea-summary span{display:grid;gap:4px;padding:14px;border:1px solid #eadfc8;border-radius:12px;background:#fffaf0}.milk-tea-summary strong{font-size:22px;color:#72551c}.milk-tea-table th:last-child,.milk-tea-table td:last-child{text-align:right}@media(max-width:700px){.milk-tea-filters,.milk-tea-summary{grid-template-columns:1fr}}`}</style>
  </div>
}
