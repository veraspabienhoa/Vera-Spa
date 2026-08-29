import { CalendarDays, Download, RefreshCw, ScanLine, Search, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

const dateText = (value) => {
  const date = new Date(value)
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}
const today = () => dateText(new Date())
const addDays = (value, days) => { const next = new Date(value); next.setDate(next.getDate() + days); return next }
const rangeFor = (filter) => {
  const now = new Date()
  const monday = addDays(now, -((now.getDay() + 6) % 7))
  if (filter === 'Hôm Qua') { const d = addDays(now, -1); return [dateText(d), dateText(d)] }
  if (filter === 'Hôm nay') return [today(), today()]
  if (filter === 'Tuần Trước') { const start = addDays(monday, -7); return [dateText(start), dateText(addDays(start, 6))] }
  if (filter === 'Tuần này') return [dateText(monday), dateText(addDays(monday, 6))]
  if (filter === 'Tháng trước') return [dateText(new Date(now.getFullYear(), now.getMonth() - 1, 1)), dateText(new Date(now.getFullYear(), now.getMonth(), 0))]
  if (filter === 'Tháng này') return [dateText(new Date(now.getFullYear(), now.getMonth(), 1)), dateText(new Date(now.getFullYear(), now.getMonth() + 1, 0))]
  return [today(), today()]
}
const FILTERS = ['Hôm Qua', 'Hôm nay', 'Tuần Trước', 'Tuần này', 'Tháng trước', 'Tháng này', 'Tùy chỉnh']
const emptyFilters = { employee: '', department: '', shift: '' }

const breakLabel = (item) => {
  if (!item.break_enabled) return 'Không áp dụng'
  if (item.break_detail) return item.break_detail
  return 'Chưa ghi nhận FaceID nghỉ'
}

async function authHeaders() {
  const session = await getCurrentSession()
  return session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}
}

async function requestJson(path) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}${path}`, { headers: await authHeaders() })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

async function downloadExcel(path, fallbackName) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}${path}`, { headers: await authHeaders() })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  let filename = fallbackName
  if (encoded) { try { filename = decodeURIComponent(encoded.replace(/^"|"$/g, '')) } catch { /* keep fallback */ } }
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function SnapshotPage({ user }) {
  const initial = useMemo(() => rangeFor('Hôm nay'), [])
  const [period, setPeriod] = useState('Hôm nay')
  const [start, setStart] = useState(initial[0])
  const [end, setEnd] = useState(initial[1])
  const [filters, setFilters] = useState(emptyFilters)
  const [applied, setApplied] = useState(emptyFilters)
  const [records, setRecords] = useState([])
  const [options, setOptions] = useState({ employees: [], departments: [], shifts: [] })
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')

  const queryString = useCallback((extra = applied) => {
    const params = new URLSearchParams({ start, end })
    if (extra.employee.trim()) params.set('employee', extra.employee.trim())
    if (extra.department.trim()) params.set('department', extra.department.trim())
    if (extra.shift.trim()) params.set('shift', extra.shift.trim())
    return params.toString()
  }, [applied, end, start])

  const load = useCallback(async () => {
    setBusy(true); setError('')
    try {
      const result = await requestJson(`/v2/snapshot?${queryString()}`)
      setRecords(result.records || [])
      setOptions(result.filters || { employees: [], departments: [], shifts: [] })
    } catch (e) { setError(e.message || 'Không tải được dữ liệu chấm công.') }
    finally { setBusy(false) }
  }, [queryString])

  useEffect(() => { void load() }, [load])

  const choosePeriod = (next) => {
    setPeriod(next)
    if (next === 'Tùy chỉnh') return
    const [nextStart, nextEnd] = rangeFor(next)
    setStart(nextStart); setEnd(nextEnd)
  }

  const applyFilters = () => setApplied({
    employee: filters.employee.trim(),
    department: filters.department.trim(),
    shift: filters.shift.trim(),
  })
  const clearFilters = () => { setFilters(emptyFilters); setApplied(emptyFilters) }

  const exportExcel = async () => {
    setExporting(true); setError('')
    try { await downloadExcel(`/v2/snapshot/export.xlsx?${queryString()}`, 'VERA_ChamCong.xlsx') }
    catch (e) { setError(e.message || 'Không export được Chấm công.') }
    finally { setExporting(false) }
  }

  return <div className="feature-page attendance-page">
    <style>{`
      .attendance-filter-buttons{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}.attendance-filter-buttons button{padding:8px 11px}
      .attendance-search-grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr)) auto;gap:10px;align-items:end;width:100%}
      .attendance-search-grid label{display:flex;flex-direction:column;gap:5px;font-size:12px;font-weight:800}.attendance-search-grid input{width:100%}
      .attendance-search-actions{display:flex;gap:7px}.attendance-date-custom{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
      @media(max-width:820px){.attendance-search-grid{grid-template-columns:1fr}.attendance-search-actions{width:100%}.attendance-search-actions button{flex:1}.attendance-filter-buttons{display:grid;grid-template-columns:repeat(2,1fr)}.attendance-filter-buttons button:last-child{grid-column:1/-1}}
    `}</style>
    <div className="page-heading"><div><span className="eyebrow"><ScanLine size={14} /> TimeSoft</span><h1>CHẤM CÔNG</h1><p>Dữ liệu chấm công, nghỉ giữa ca và FaceID được đồng bộ vào PostgreSQL. Trang này không hiển thị doanh thu.</p></div><button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button></div>
    {error && <div className="error-box">{error}</div>}

    <section className="panel data-toolbar attendance-toolbar">
      <div style={{width:'100%'}}>
        <div className="attendance-filter-buttons" role="group" aria-label="Lọc thời gian chấm công">
          {FILTERS.map((item) => <button type="button" key={item} className={period === item ? 'primary-button' : 'secondary-button'} onClick={() => choosePeriod(item)}>{item}</button>)}
        </div>
        {period === 'Tùy chỉnh' && <div className="attendance-date-custom"><label><CalendarDays size={15} /> Từ ngày<input type="date" value={start} onChange={(e) => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value) }} /></label><label><CalendarDays size={15} /> Đến ngày<input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></label></div>}
        <div className="attendance-search-grid">
          <label>Tên nhân viên<input type="search" value={filters.employee} onChange={(e) => setFilters({...filters, employee:e.target.value})} placeholder="Tìm tên nhân viên" list="attendance-employees" /></label>
          <label>Bộ phận<input type="search" value={filters.department} onChange={(e) => setFilters({...filters, department:e.target.value})} placeholder="Tìm bộ phận" list="attendance-departments" /></label>
          <label>Ca làm việc<input type="search" value={filters.shift} onChange={(e) => setFilters({...filters, shift:e.target.value})} placeholder="Tìm ca làm việc" list="attendance-shifts" /></label>
          <div className="attendance-search-actions"><button className="primary-button" type="button" onClick={applyFilters}><Search size={16}/> Tìm</button>{Object.values(applied).some(Boolean) && <button className="secondary-button" type="button" onClick={clearFilters}><X size={16}/> Bỏ lọc</button>}</div>
          <datalist id="attendance-employees">{(options.employees || []).map((value) => <option key={value} value={value}/>)}</datalist>
          <datalist id="attendance-departments">{(options.departments || []).map((value) => <option key={value} value={value}/>)}</datalist>
          <datalist id="attendance-shifts">{(options.shifts || []).map((value) => <option key={value} value={value}/>)}</datalist>
        </div>
      </div>
      {user?.permissions?.snapshot_export && <button className="secondary-button" onClick={exportExcel} disabled={exporting}><Download size={16} /> {exporting ? 'Đang xuất…' : 'Export Excel'}</button>}
    </section>

    <section className="panel"><div className="panel-title-row"><div><h2>CHẤM CÔNG NHÂN VIÊN</h2><p>{records.length} bản ghi · {start} → {end}{applied.employee ? ` · ${applied.employee}` : ''}{applied.department ? ` · ${applied.department}` : ''}{applied.shift ? ` · ${applied.shift}` : ''}.</p></div></div><div className="responsive-data-table"><table><thead><tr><th>Ngày</th><th>Nhân viên</th><th>Bộ phận</th><th>Ca</th><th>Giờ vào</th><th>Giờ ra</th><th>Nghỉ giữa ca</th><th>Trạng thái</th><th>Trễ</th><th>Về sớm</th></tr></thead><tbody>{records.map((item, index) => <tr key={`${item.date}-${item.employee_code}-${item.check_in}-${index}`}><td>{item.date}</td><td><strong>{item.employee_name}</strong><small>{item.employee_code}</small></td><td>{item.break_department || '—'}</td><td>{item.shift}<small>{item.shift_start} – {item.shift_end}</small></td><td>{item.check_in || '—'}</td><td>{item.check_out || '—'}</td><td><strong>{item.break_enabled ? `${item.break_planned_minutes || 0} phút` : '—'}</strong><small>{breakLabel(item)}</small>{item.break_detail && <small>Thực tế: {item.break_actual_minutes || 0} phút · {item.break_status}</small>}</td><td>{item.arrival_status}<small>{item.departure_status}</small></td><td>{item.late_minutes} phút</td><td>{item.early_minutes} phút</td></tr>)}</tbody></table></div>{!records.length && <div className="setup-note">Không có dữ liệu phù hợp bộ lọc.</div>}</section>
  </div>
}
