import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Pencil, Plus, RefreshCw, Search, Trash2, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => `${Number(value || 0).toLocaleString('vi-VN')}đ`
const trackedRoles = new Set(['leader', 'nhanvien'])

function searchKey(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
    .trim()
}

function roleLabel(value) {
  return String(value || '').toLowerCase() === 'leader' ? 'Leader' : 'Nhân viên'
}

async function authHeaders() {
  const session = await getCurrentSession()
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  return headers
}

async function loadTracking() {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const headers = await authHeaders()
  const response = await fetch(`${apiBase}/v2/payroll/personal-tracking`, { headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

async function changeAccumulation(method, path, body) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const headers = await authHeaders()
  const response = await fetch(`${apiBase}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

function PeriodTable({ periods }) {
  return <div className="responsive-data-table payroll-personal-table">
    <table>
      <thead><tr><th>Kỳ lương</th><th>Từ ngày</th><th>Đến ngày</th><th>Tích lũy đã đóng</th><th>Hoàn trả tích lũy</th><th>Ngày lưu</th></tr></thead>
      <tbody>{(periods || []).map((item, index) => <tr key={`${item.batch}-${item.start}-${index}`}>
        <td><strong>{item.batch}</strong></td>
        <td>{item.start || '—'}</td>
        <td>{item.end || '—'}</td>
        <td className="money-cell"><strong>{money(item.contribution)}</strong></td>
        <td className="money-cell">{money(item.refund)}</td>
        <td>{item.saved_date || '—'}</td>
      </tr>)}</tbody>
    </table>
    {!(periods || []).length && <div className="setup-note">Chưa có kỳ lương ghi nhận Tích lũy.</div>}
  </div>
}

function ObligationList({ obligations }) {
  if (!(obligations || []).length) return <div className="payroll-personal-clear"><CheckCircle2 size={18} /> Không có Nghĩa vụ Vi phạm chưa hoàn thành.</div>
  return <div className="responsive-data-table payroll-personal-table">
    <table>
      <thead><tr><th>Số tiền</th><th>Bắt đầu trừ</th><th>Kỳ phát sinh</th><th>Nội dung</th><th>Trạng thái</th></tr></thead>
      <tbody>{obligations.map((item, index) => <tr key={`${item.employee_name}-${item.due_from}-${index}`}>
        <td className="money-cell"><strong>{money(item.amount)}</strong></td>
        <td>{item.due_from || '—'}</td>
        <td>{item.period_start || item.period_end ? `${item.period_start || '—'} – ${item.period_end || '—'}` : '—'}</td>
        <td>{item.content || 'Chưa hoàn thành nghĩa vụ Vi phạm'}</td>
        <td><span className="payroll-personal-open"><AlertTriangle size={14} /> {item.status || 'Chưa hoàn thành'}</span></td>
      </tr>)}</tbody>
    </table>
  </div>
}

function AdminTrackingTable({ rows, emptyText, editable = false, onAdd, onEdit, onDelete, busyEmployee }) {
  return <div className="responsive-data-table payroll-personal-admin-table">
    <table>
      <thead><tr><th>Nhân viên</th><th>Chức vụ</th><th>Mục tiêu</th><th>Đã đóng</th><th>Còn lại</th><th>Số kỳ đã đóng</th><th>Nghĩa vụ chưa hoàn thành</th>{editable && <th>Điều chỉnh</th>}<th>Chi tiết</th></tr></thead>
      <tbody>{rows.map((item) => <tr key={item.employee_name}>
        <td><strong>{item.employee_name}</strong><small>{item.full_name || '—'}</small></td>
        <td>{roleLabel(item.role)}</td>
        <td className="money-cell">{money(item.target)}</td>
        <td className="money-cell"><strong>{money(item.paid_total)}</strong>{Number(item.manual_adjustment_total || 0) !== 0 && <small>Admin điều chỉnh: {money(item.manual_adjustment_total)}</small>}</td>
        <td className="money-cell"><strong>{money(item.remaining)}</strong></td>
        <td className="center">{Number(item.period_count || 0).toLocaleString('vi-VN')}</td>
        <td className="money-cell">{money(item.obligation_total)}</td>
        {editable && <td><div className="payroll-personal-adjust-actions">
          <button type="button" className="secondary-button compact" disabled={busyEmployee === item.employee_name} onClick={() => onAdd(item)}><Plus size={14}/> Thêm</button>
          <button type="button" className="secondary-button compact" disabled={busyEmployee === item.employee_name} onClick={() => onEdit(item)}><Pencil size={14}/> Sửa</button>
          <button type="button" className="danger-button compact" disabled={busyEmployee === item.employee_name} onClick={() => onDelete(item)}><Trash2 size={14}/> Xóa</button>
        </div></td>}
        <td><details className="payroll-personal-row-details"><summary>Xem</summary><h4>TÍCH LŨY THEO TỪNG KỲ LƯƠNG</h4><PeriodTable periods={item.periods} /><h4>NGHĨA VỤ VI PHẠM CHƯA HOÀN THÀNH</h4><ObligationList obligations={item.obligations} /></details></td>
      </tr>)}</tbody>
    </table>
    {!rows.length && <div className="setup-note">{emptyText}</div>}
  </div>
}

export default function PayrollPersonalTracking({ user, standalone = false }) {
  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'
  const canUsePersonalTracking = isAdmin || trackedRoles.has(role)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [busyEmployee, setBusyEmployee] = useState('')
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [sectionOpen, setSectionOpen] = useState(!isAdmin)
  const [completedOpen, setCompletedOpen] = useState(false)

  const load = async () => {
    if (!canUsePersonalTracking) return
    setBusy(true); setError('')
    try { setData(await loadTracking()) }
    catch (err) { setError(err.message || 'Không tải được thông tin Tích lũy/Nghĩa vụ Vi phạm.') }
    finally { setBusy(false) }
  }

  const runAdjustment = async (employeeName, request) => {
    setBusyEmployee(employeeName); setError('')
    try {
      await request()
      await load()
    } catch (err) {
      setError(err.message || 'Không cập nhật được tiền Tích lũy.')
    } finally {
      setBusyEmployee('')
    }
  }

  const addAccumulation = (item) => {
    const raw = window.prompt(`Cộng thêm tiền Tích lũy cho ${item.employee_name}:`, '500000')
    if (raw === null) return
    const amount = Number(String(raw).replace(/[^0-9.-]/g, ''))
    if (!Number.isFinite(amount) || amount <= 0) { setError('Số tiền cộng thêm phải lớn hơn 0.'); return }
    void runAdjustment(item.employee_name, () => changeAccumulation('POST', '/v2/payroll/accumulation-adjustments/add', { employee_name: item.employee_name, amount }))
  }

  const editAccumulation = (item) => {
    const raw = window.prompt(`Sửa tổng tiền Tích lũy đã đóng của ${item.employee_name}:`, String(Number(item.paid_total || 0)))
    if (raw === null) return
    const paidTotal = Number(String(raw).replace(/[^0-9.-]/g, ''))
    if (!Number.isFinite(paidTotal) || paidTotal < 0) { setError('Tổng tiền Tích lũy không được âm.'); return }
    void runAdjustment(item.employee_name, () => changeAccumulation('PUT', '/v2/payroll/accumulation-adjustments/set', { employee_name: item.employee_name, paid_total: paidTotal }))
  }

  const deleteAccumulation = (item) => {
    if (!window.confirm(`Xóa số tiền Tích lũy đã đóng của ${item.employee_name} về 0đ?`)) return
    const path = `/v2/payroll/accumulation-adjustments?employee_name=${encodeURIComponent(item.employee_name)}`
    void runAdjustment(item.employee_name, () => changeAccumulation('DELETE', path))
  }

  useEffect(() => {
    if (!canUsePersonalTracking) return
    if (!isAdmin || sectionOpen) void load()
  }, [canUsePersonalTracking, isAdmin, sectionOpen]) // eslint-disable-line react-hooks/exhaustive-deps

  const visible = useMemo(() => {
    const rows = (data?.employees || []).filter((item) => trackedRoles.has(String(item.role || '').toLowerCase()))
    const needle = searchKey(search)
    if (!needle) return rows
    return rows.filter((item) => searchKey(`${item.employee_name} ${item.full_name} ${item.role}`).includes(needle))
  }, [data, search])

  const activeRows = useMemo(() => visible.filter((item) => !item.completed && Number(item.remaining || 0) > 0), [visible])
  const completedRows = useMemo(() => visible.filter((item) => item.completed || Number(item.remaining || 0) <= 0), [visible])
  const mine = (data?.employees || [])[0] || null
  const totals = useMemo(() => {
    const rows = (data?.employees || []).filter((item) => trackedRoles.has(String(item.role || '').toLowerCase()))
    return {
      employee_count: rows.length,
      paid_total: rows.reduce((sum, item) => sum + Number(item.paid_total || 0), 0),
      remaining_total: rows.reduce((sum, item) => sum + Number(item.remaining || 0), 0),
      obligation_total: rows.reduce((sum, item) => sum + Number(item.obligation_total || 0), 0),
    }
  }, [data])

  if (!canUsePersonalTracking) return null

  return <div className={`feature-page payroll-page payroll-personal-tracking${standalone ? ' standalone' : ''}`}>
    <style>{`
      .payroll-personal-tracking{margin-top:${standalone ? '0' : '16px'}}
      .payroll-personal-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.payroll-personal-heading h1,.payroll-personal-heading h2{margin:4px 0}.payroll-personal-heading p{margin:0;color:#69766f}.payroll-personal-heading-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      .payroll-personal-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}.payroll-personal-metric{padding:14px;border:1px solid #dfe7e2;border-radius:14px;background:#fff}.payroll-personal-metric span{display:block;font-size:11px;font-weight:900;color:#68736f}.payroll-personal-metric strong{display:block;margin-top:5px;font-size:22px;color:#173329}.payroll-personal-metric.warning strong{color:#a13c2f}
      .payroll-personal-table table{min-width:760px}.payroll-personal-admin-table table{min-width:1120px}.payroll-personal-admin-table td small{display:block;margin-top:3px;color:#6b7771}.payroll-personal-open{display:inline-flex;align-items:center;gap:5px;color:#a13c2f;font-weight:900}.payroll-personal-clear{display:flex;align-items:center;gap:7px;padding:12px;border:1px solid #cde0d4;border-radius:12px;background:#f1f9f4;color:#286443;font-weight:800}.payroll-personal-search{display:flex;align-items:center;gap:7px;max-width:420px}.payroll-personal-search input{width:100%}.payroll-personal-section-title{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:18px 0 8px}.payroll-personal-section-title h3{margin:0;color:#24473a}.payroll-personal-row-details summary{cursor:pointer;font-weight:900;color:#315a49}.payroll-personal-row-details h4{margin:13px 0 7px}.payroll-personal-collapsed-note{margin-top:8px;color:#6b7771;font-size:12px}.payroll-personal-adjust-actions{display:flex;gap:5px;flex-wrap:wrap}.payroll-personal-adjust-actions button{padding:6px 8px;font-size:12px}
      @media(max-width:760px){.payroll-personal-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.payroll-personal-heading{display:grid}.payroll-personal-heading-actions{width:100%}.payroll-personal-heading-actions button{flex:1}.payroll-personal-search{max-width:none;width:100%}.payroll-personal-section-title{align-items:flex-start}.payroll-personal-section-title button{white-space:nowrap}}
    `}</style>

    {standalone && <div className="page-heading payroll-personal-heading"><div><span className="eyebrow"><WalletCards size={14} /> Cá nhân</span><h1>BẢNG LƯƠNG</h1><p>Theo dõi Tích lũy đã đóng và Nghĩa vụ Vi phạm chưa hoàn thành của bạn.</p></div>{!isAdmin && <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''}/> Làm mới</button>}</div>}

    <section className="panel payroll-personal-section">
      <div className="payroll-personal-heading">
        <div><h2>{isAdmin ? 'THEO DÕI TÍCH LŨY NHÂN VIÊN' : 'TÍCH LŨY & NGHĨA VỤ VI PHẠM CỦA TÔI'}</h2><p>{isAdmin ? 'Chỉ theo dõi Leader và Nhân viên. Admin có thể thêm, sửa hoặc xóa số tiền Tích lũy ở nhóm đang còn đóng.' : 'Hiển thị số tiền Tích lũy hiện tại và Nghĩa vụ Vi phạm đang mở.'}</p></div>
        <div className="payroll-personal-heading-actions">
          {isAdmin && <button className="secondary-button" type="button" onClick={() => setSectionOpen((value) => !value)}>{sectionOpen ? <ChevronDown size={16}/> : <ChevronRight size={16}/>} {sectionOpen ? 'Ẩn' : 'Hiện'}</button>}
          {sectionOpen && !standalone && <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''}/> Làm mới</button>}
        </div>
      </div>

      {isAdmin && !sectionOpen && <div className="payroll-personal-collapsed-note">Khu vực này mặc định được ẩn để giao diện Bảng lương gọn hơn.</div>}

      {sectionOpen && <>
        {error && <div className="error-box">{error}</div>}
        {busy && !data && <div className="setup-note">Đang tải số liệu Tích lũy…</div>}

        {isAdmin ? <>
          <div className="payroll-personal-metrics">
            <div className="payroll-personal-metric"><span>LEADER / NHÂN VIÊN</span><strong>{Number(totals.employee_count || 0).toLocaleString('vi-VN')}</strong></div>
            <div className="payroll-personal-metric"><span>TỔNG ĐÃ ĐÓNG TÍCH LŨY</span><strong>{money(totals.paid_total)}</strong></div>
            <div className="payroll-personal-metric"><span>TỔNG CÒN LẠI</span><strong>{money(totals.remaining_total)}</strong></div>
            <div className="payroll-personal-metric warning"><span>NGHĨA VỤ CHƯA HOÀN THÀNH</span><strong>{money(totals.obligation_total)}</strong></div>
          </div>
          <label className="payroll-personal-search"><Search size={16}/><input type="search" value={search} placeholder="Tìm Leader / Nhân viên" onChange={(event) => setSearch(event.target.value)} /></label>

          <div className="payroll-personal-section-title"><h3>ĐANG CÒN ĐÓNG TIỀN TÍCH LŨY ({activeRows.length})</h3></div>
          <AdminTrackingTable rows={activeRows} editable onAdd={addAccumulation} onEdit={editAccumulation} onDelete={deleteAccumulation} busyEmployee={busyEmployee} emptyText="Không có Leader/Nhân viên đang còn đóng tiền tích lũy." />

          <div className="payroll-personal-section-title">
            <h3>ĐÃ HOÀN THÀNH ĐÓNG TIỀN TÍCH LŨY ({completedRows.length})</h3>
            <button className="secondary-button compact" type="button" onClick={() => setCompletedOpen((value) => !value)}>{completedOpen ? <ChevronDown size={15}/> : <ChevronRight size={15}/>} {completedOpen ? 'Ẩn' : 'Hiện'}</button>
          </div>
          {completedOpen && <AdminTrackingTable rows={completedRows} emptyText="Chưa có Leader/Nhân viên hoàn thành đóng tiền tích lũy." />}
        </> : mine && <>
          <div className="payroll-personal-metrics">
            <div className="payroll-personal-metric"><span>MỤC TIÊU TÍCH LŨY</span><strong>{money(mine.target)}</strong></div>
            <div className="payroll-personal-metric"><span>ĐÃ ĐÓNG</span><strong>{money(mine.paid_total)}</strong></div>
            <div className="payroll-personal-metric"><span>CÒN LẠI</span><strong>{money(mine.remaining)}</strong></div>
            <div className="payroll-personal-metric warning"><span>NGHĨA VỤ CHƯA HOÀN THÀNH</span><strong>{money(mine.obligation_total)}</strong></div>
          </div>
          <h3>TÍCH LŨY ĐÃ ĐÓNG THEO TỪNG KỲ LƯƠNG</h3>
          <PeriodTable periods={mine.periods} />
          <h3 style={{ marginTop: 18 }}>NGHĨA VỤ VI PHẠM CHƯA HOÀN THÀNH</h3>
          <ObligationList obligations={mine.obligations} />
        </>}
      </>}
    </section>
  </div>
}