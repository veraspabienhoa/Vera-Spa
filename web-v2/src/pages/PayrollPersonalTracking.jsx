import { AlertTriangle, CheckCircle2, RefreshCw, Search, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => `${Number(value || 0).toLocaleString('vi-VN')}đ`

function searchKey(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
    .trim()
}

async function loadTracking() {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers()
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${apiBase}/v2/payroll/personal-tracking`, { headers })
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

function EmployeeTrackingCard({ item, admin }) {
  return <article className="payroll-personal-employee-card">
    <header>
      <div><strong>{item.employee_name}</strong><small>{item.full_name || '—'}{item.role ? ` · ${item.role}` : ''}</small></div>
      <span className={item.completed ? 'done' : 'open'}>{item.completed ? 'ĐÃ ĐỦ TÍCH LŨY' : `CÒN ${money(item.remaining)}`}</span>
    </header>
    <div className="payroll-personal-mini-grid">
      <span>Mục tiêu<strong>{money(item.target)}</strong></span>
      <span>Đã đóng<strong>{money(item.paid_total)}</strong></span>
      <span>Còn lại<strong>{money(item.remaining)}</strong></span>
      <span>Nghĩa vụ mở<strong>{money(item.obligation_total)}</strong></span>
    </div>
    {admin && <details>
      <summary>Chi tiết {item.period_count} kỳ có đóng tích lũy · {item.obligation_count} nghĩa vụ chưa hoàn thành</summary>
      <h4>TÍCH LŨY THEO TỪNG KỲ LƯƠNG</h4>
      <PeriodTable periods={item.periods} />
      <h4>NGHĨA VỤ VI PHẠM CHƯA HOÀN THÀNH</h4>
      <ObligationList obligations={item.obligations} />
    </details>}
  </article>
}

export default function PayrollPersonalTracking({ user, standalone = false }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const load = async () => {
    setBusy(true); setError('')
    try { setData(await loadTracking()) }
    catch (err) { setError(err.message || 'Không tải được thông tin Tích lũy/Nghĩa vụ Vi phạm.') }
    finally { setBusy(false) }
  }

  useEffect(() => { void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const visible = useMemo(() => {
    const rows = data?.employees || []
    const needle = searchKey(search)
    if (!needle) return rows
    return rows.filter((item) => searchKey(`${item.employee_name} ${item.full_name} ${item.role}`).includes(needle))
  }, [data, search])

  const mine = (data?.employees || [])[0] || null
  const totals = data?.totals || {}

  return <div className={`feature-page payroll-page payroll-personal-tracking${standalone ? ' standalone' : ''}`}>
    <style>{`
      .payroll-personal-tracking{margin-top:${standalone ? '0' : '16px'}}
      .payroll-personal-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.payroll-personal-heading h1,.payroll-personal-heading h2{margin:4px 0}.payroll-personal-heading p{margin:0;color:#69766f}
      .payroll-personal-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}.payroll-personal-metric{padding:14px;border:1px solid #dfe7e2;border-radius:14px;background:#fff}.payroll-personal-metric span{display:block;font-size:11px;font-weight:900;color:#68736f}.payroll-personal-metric strong{display:block;margin-top:5px;font-size:22px;color:#173329}.payroll-personal-metric.warning strong{color:#a13c2f}
      .payroll-personal-employee-list{display:grid;gap:10px}.payroll-personal-employee-card{padding:14px;border:1px solid #e0e7e3;border-radius:15px;background:#fff}.payroll-personal-employee-card>header{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.payroll-personal-employee-card header strong{font-size:17px;color:#173329}.payroll-personal-employee-card header small{display:block;margin-top:3px;color:#6b7771}.payroll-personal-employee-card header>span{font-size:11px;font-weight:900;border-radius:999px;padding:6px 9px}.payroll-personal-employee-card header>span.done{background:#edf8f1;color:#23623b}.payroll-personal-employee-card header>span.open{background:#fff8e7;color:#805f00}
      .payroll-personal-mini-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px}.payroll-personal-mini-grid span{padding:9px 10px;border-radius:10px;background:#f7faf8;color:#68736f;font-size:10px;font-weight:800}.payroll-personal-mini-grid strong{display:block;margin-top:4px;color:#173329;font-size:15px}.payroll-personal-employee-card details{margin-top:12px}.payroll-personal-employee-card summary{cursor:pointer;font-weight:900;color:#315a49}.payroll-personal-employee-card h4{margin:15px 0 7px;color:#405c50}
      .payroll-personal-table table{min-width:760px}.payroll-personal-open{display:inline-flex;align-items:center;gap:5px;color:#a13c2f;font-weight:900}.payroll-personal-clear{display:flex;align-items:center;gap:7px;padding:12px;border:1px solid #cde0d4;border-radius:12px;background:#f1f9f4;color:#286443;font-weight:800}.payroll-personal-search{display:flex;align-items:center;gap:7px;max-width:420px}.payroll-personal-search input{width:100%}
      @media(max-width:760px){.payroll-personal-metrics,.payroll-personal-mini-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.payroll-personal-heading{display:grid}.payroll-personal-search{max-width:none;width:100%}.payroll-personal-employee-card>header{display:grid}.payroll-personal-employee-card header>span{justify-self:start}}
    `}</style>

    {standalone && <div className="page-heading payroll-personal-heading"><div><span className="eyebrow"><WalletCards size={14} /> Cá nhân</span><h1>BẢNG LƯƠNG</h1><p>Theo dõi Tích lũy đã đóng và Nghĩa vụ Vi phạm chưa hoàn thành của bạn.</p></div><button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''}/> Làm mới</button></div>}

    <section className="panel">
      <div className="payroll-personal-heading">
        <div><h2>{isAdmin ? 'THEO DÕI TÍCH LŨY NHÂN VIÊN' : 'TÍCH LŨY & NGHĨA VỤ VI PHẠM CỦA TÔI'}</h2><p>{isAdmin ? 'Admin xem số tiền đã đóng theo từng kỳ lương, số còn lại và nghĩa vụ chưa hoàn thành của từng nhân viên.' : 'Số liệu lấy từ các kỳ lương đã lưu và danh sách Nghĩa vụ Vi phạm đang mở.'}</p></div>
        {!standalone && <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''}/> Làm mới</button>}
      </div>
      {error && <div className="error-box">{error}</div>}
      {busy && !data && <div className="setup-note">Đang tải số liệu Tích lũy…</div>}

      {isAdmin ? <>
        <div className="payroll-personal-metrics">
          <div className="payroll-personal-metric"><span>NHÂN VIÊN ĐANG THEO DÕI</span><strong>{Number(totals.employee_count || 0).toLocaleString('vi-VN')}</strong></div>
          <div className="payroll-personal-metric"><span>TỔNG ĐÃ ĐÓNG TÍCH LŨY</span><strong>{money(totals.paid_total)}</strong></div>
          <div className="payroll-personal-metric"><span>TỔNG CÒN LẠI</span><strong>{money(totals.remaining_total)}</strong></div>
          <div className="payroll-personal-metric warning"><span>NGHĨA VỤ CHƯA HOÀN THÀNH</span><strong>{money(totals.obligation_total)}</strong></div>
        </div>
        <label className="payroll-personal-search"><Search size={16}/><input type="search" value={search} placeholder="Tìm nhân viên" onChange={(event) => setSearch(event.target.value)} /></label>
        <div className="payroll-personal-employee-list" style={{ marginTop: 12 }}>{visible.map((item) => <EmployeeTrackingCard key={item.employee_name} item={item} admin />)}</div>
        {!visible.length && data && <div className="setup-note">Không có nhân viên phù hợp.</div>}
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
    </section>
  </div>
}
