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
  const employeeName = String(data.rows?.[0]?.employee_name || user?.employee_username || '').trim()
  const changePreset = preset => setFilters(current => ({ ...current, preset, ...tourDateRange(preset) }))
  if (!allowed) return <div className="panel">Chỉ tài khoản Leader và Nhân viên được xem Trà sữa của chính mình.</div>
  return <div className="feature-page spa-page milk-tea-page">
    <div className="page-heading milk-tea-heading">
      <div className="milk-tea-heading-copy">
        <span className="eyebrow">VERA SPA</span>
        <div className="milk-tea-title-row">
          <h1>Trà sữa</h1>
          <div className="milk-tea-employee"><span>Tên nhân viên</span><strong>{employeeName || '—'}</strong></div>
        </div>
        <p>Tiền Tip của riêng tài khoản {user?.employee_username || ''}; không hiển thị tiền dịch vụ.</p>
      </div>
      <button className="secondary-button" disabled={busy} onClick={load}>{busy ? 'Đang tải…' : 'Làm mới'}</button>
    </div>
    {error && <div className="error-box" role="alert">{error}</div>}
    <section className="panel spa-content">
      <div className="milk-tea-filters">
        <label><span>Thời gian</span><select value={filters.preset} onChange={event => changePreset(event.target.value)}>{TOUR_DATE_PRESETS.filter(([id]) => id !== 'all').map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        <label><span>Từ ngày</span><VeraDateInput value={filters.date_from} max={filters.date_to || undefined} onChange={event => setFilters(current => ({ ...current, date_from: event.target.value, preset: 'custom' }))}/></label>
        <label><span>Đến ngày</span><VeraDateInput value={filters.date_to} min={filters.date_from || undefined} onChange={event => setFilters(current => ({ ...current, date_to: event.target.value, preset: 'custom' }))}/></label>
      </div>
      <div className="milk-tea-summary"><span>Số hóa đơn<strong>{rows.length}</strong></span><span>Tiền Tip<strong>{money(total)}</strong></span></div>

      <div className="responsive-data-table milk-tea-table milk-tea-table-desktop"><table><thead><tr><th>Ngày giờ hóa đơn</th><th>Số hóa đơn</th><th>Dịch vụ</th><th>Phòng</th><th>Tiền Tip</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td data-label="Ngày giờ hóa đơn">{formatVeraDateTime(row.effective_at || row.business_date)}</td><td data-label="Số hóa đơn">{row.bill_no || '—'}</td><td data-label="Dịch vụ">{(row.services || []).join(', ') || '—'}</td><td data-label="Phòng">{(row.rooms || []).join(', ') || '—'}</td><td data-label="Tiền Tip"><strong>{money(row.tip)}</strong></td></tr>)}</tbody></table></div>

      <div className="milk-tea-table-mobile" aria-label="Danh sách tiền Tip trên mobile"><table><colgroup><col className="milk-col-date"/><col className="milk-col-service"/><col className="milk-col-room"/><col className="milk-col-tip"/><col className="milk-col-bill"/></colgroup><thead><tr><th>Ngày giờ hóa đơn</th><th>Dịch vụ</th><th>Phòng</th><th>Tiền Tip</th><th>Số hóa đơn</th></tr></thead><tbody>{rows.map(row => <tr key={`mobile-${row.id}`}><td>{formatVeraDateTime(row.effective_at || row.business_date)}</td><td>{(row.services || []).join(', ') || '—'}</td><td>{(row.rooms || []).join(', ') || '—'}</td><td><strong>{money(row.tip)}</strong></td><td>{row.bill_no || '—'}</td></tr>)}</tbody></table></div>

      {!rows.length && !busy && <p>Không có tiền Tip trong khoảng thời gian đã chọn.</p>}
    </section>
    <style>{`
      .milk-tea-heading-copy{min-width:0;flex:1 1 auto}
      .milk-tea-title-row{display:flex;align-items:flex-end;gap:24px;min-width:0}
      .milk-tea-title-row h1{margin-bottom:0}
      .milk-tea-employee{display:grid;gap:2px;padding-left:18px;border-left:1px solid #9eb2a8;min-width:0}
      .milk-tea-employee span{font-size:12px;color:#557064}
      .milk-tea-employee strong{font-size:17px;color:#153f31;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .milk-tea-filters{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:10px;margin-bottom:14px}
      .milk-tea-filters label{display:grid;gap:5px}
      .milk-tea-summary{display:grid;grid-template-columns:repeat(2,minmax(150px,1fr));gap:10px;margin:12px 0}
      .milk-tea-summary span{display:grid;gap:4px;padding:14px;border:1px solid #eadfc8;border-radius:12px;background:#fffaf0}
      .milk-tea-summary strong{font-size:22px;color:#72551c}
      .milk-tea-table th:last-child,.milk-tea-table td:last-child{text-align:right}
      .milk-tea-table-mobile{display:none}

      @media(max-width:700px){
        .milk-tea-heading{align-items:flex-start}
        .milk-tea-title-row{align-items:center;gap:10px}
        .milk-tea-title-row h1{flex:0 0 auto}
        .milk-tea-employee{margin-left:auto;padding-left:10px;max-width:48%}
        .milk-tea-employee span{font-size:9px}
        .milk-tea-employee strong{font-size:12px}
        .milk-tea-heading-copy>p{display:none}
        .milk-tea-filters,.milk-tea-summary{grid-template-columns:1fr}

        .milk-tea-table-desktop{display:none!important}
        .milk-tea-table-mobile{display:block;width:100%;max-width:100%;overflow:hidden;border:2px solid #37634f;box-sizing:border-box}
        .milk-tea-table-mobile table{width:100%!important;max-width:100%!important;min-width:0!important;table-layout:fixed;border-collapse:collapse;margin:0}
        .milk-tea-table-mobile col.milk-col-date{width:23%}
        .milk-tea-table-mobile col.milk-col-service{width:19%}
        .milk-tea-table-mobile col.milk-col-room{width:11%}
        .milk-tea-table-mobile col.milk-col-tip{width:18%}
        .milk-tea-table-mobile col.milk-col-bill{width:29%}
        .milk-tea-table-mobile th,.milk-tea-table-mobile td{box-sizing:border-box;min-width:0;max-width:100%;padding:4px 3px;border:1px solid #557967;vertical-align:top;white-space:normal!important;overflow-wrap:anywhere;word-break:break-word;line-height:1.18}
        .milk-tea-table-mobile th{font-size:8px;letter-spacing:.04em;text-transform:uppercase}
        .milk-tea-table-mobile td{font-size:9px}
        .milk-tea-table-mobile td:nth-child(4){text-align:right}
        .milk-tea-table-mobile td:nth-child(5),.milk-tea-table-mobile th:nth-child(5){text-align:left}
        .milk-tea-table-mobile strong{font-size:9px;white-space:normal}
      }
    `}</style>
  </div>
}
