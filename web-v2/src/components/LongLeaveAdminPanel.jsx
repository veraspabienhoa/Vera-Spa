import UiCustomText from './UiCustomText'
import { formatVeraDate } from '../lib/veraDate'
import { AlertTriangle, CalendarRange, CheckCircle2, Clock3, RefreshCw, XCircle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'
import VeraDateInput from './VeraDateInput'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

async function request(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${apiBase}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

const vnDate = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}-${month}-${year}` : '—'
}

const moneyLike = (value) => Number(value || 0).toLocaleString('vi-VN')
const isoToday = () => new Date().toISOString().slice(0, 10)
const addDays = (value, days) => { const date = new Date(`${value}T12:00:00`); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10) }

export default function LongLeaveAdminPanel({ user, onChanged }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [busyId, setBusyId] = useState('')
  const [rejectReasons, setRejectReasons] = useState({})
  const [notice, setNotice] = useState(null)
  const [overlap, setOverlap] = useState(null)
  const [overlapFilters, setOverlapFilters] = useState({ start: isoToday(), end: addDays(isoToday(), 14), department: '', threshold: 20 })

  const load = useCallback(async () => {
    if (!isAdmin) return
    setLoading(true)
    try {
      const result = await request('/v2/long-leave/admin/pending')
      setRows(result.requests || [])
    } catch (error) {
      setNotice({ status: 'error', message: error.message || 'Không tải được đơn chờ duyệt.' })
    } finally {
      setLoading(false)
    }
  }, [isAdmin])

  useEffect(() => { void load() }, [load])

  const loadOverlap = useCallback(async () => {
    if (!isAdmin) return
    try {
      const params = new URLSearchParams({ start: overlapFilters.start, end: overlapFilters.end, threshold: String(Number(overlapFilters.threshold || 20) / 100) })
      if (overlapFilters.department) params.set('department_id', overlapFilters.department)
      setOverlap(await request(`/v2/hr/leaves/overlap?${params}`))
    } catch (error) {
      setNotice({ status: 'error', message: error.message || 'Không tải được tổng quan trùng lịch nghỉ.' })
    }
  }, [isAdmin, overlapFilters])

  useEffect(() => { void loadOverlap() }, [loadOverlap])

  if (!isAdmin) return null

  const decide = async (item, decision) => {
    const approving = decision === 'approve'
    const reason = String(rejectReasons[item.id] || '').trim()
    if (!approving && !reason) {
      setNotice({ status: 'error', message: `Vui lòng nhập lý do không duyệt đơn ${item.id}.` })
      return
    }
    const actionText = approving ? 'duyệt' : 'không duyệt'
    if (!window.confirm(`${actionText === 'duyệt' ? 'Duyệt' : 'Không duyệt'} ${item.request_type} của ${item.employee_name}?`)) return
    setBusyId(item.id)
    setNotice(null)
    try {
      const result = await request(`/v2/long-leave/admin/requests/${encodeURIComponent(item.id)}/decision`, {
        method: 'POST',
        body: JSON.stringify({ decision, rejection_reason: approving ? '' : reason }),
      })
      setNotice({
        status: 'success',
        message: `${result.message}${result.annual_leave_rows_created ? ` Đã tạo ${result.annual_leave_rows_created} ngày Phép năm trong lịch nghỉ.` : ''}`,
      })
      setRejectReasons((current) => ({ ...current, [item.id]: '' }))
      await load()
      onChanged?.()
    } catch (error) {
      setNotice({ status: 'error', message: error.message || 'Không cập nhật được trạng thái đơn.' })
    } finally {
      setBusyId('')
    }
  }

  return <section data-ui-key="u-d0934921f18d" className="panel long-leave-admin-panel">
    <style>{`
      .long-leave-admin-panel{display:grid;gap:12px;margin-bottom:16px;border-color:#d8e4dd;background:#fbfdfc}
      .long-leave-admin-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
      .long-leave-admin-heading h2{margin:0;color:#10251e;font-size:20px}.long-leave-admin-heading p{margin:4px 0 0;color:#6c7771;font-size:11px}
      .long-leave-pending-list{display:grid;gap:10px}.long-leave-pending-card{display:grid;gap:10px;padding:13px;border:1px solid #dfe7e3;border-radius:14px;background:#fff}
      .long-leave-pending-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.long-leave-pending-head strong{display:block;color:#10251e;font-size:15px}.long-leave-pending-head small{display:block;margin-top:2px;color:#77827d;font-size:9px}
      .long-leave-request-type{flex:0 0 auto;padding:5px 8px;border-radius:999px;background:#edf5f0;color:#315d47;font-size:10px;font-weight:900}.long-leave-request-type.annual{background:#fff2d6;color:#795518}.long-leave-request-type.resignation{background:#fceaea;color:#873232}
      .long-leave-pending-meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.long-leave-pending-meta span{min-width:0;padding:8px;border-radius:9px;background:#f3f6f4}.long-leave-pending-meta small,.long-leave-pending-meta strong{display:block}.long-leave-pending-meta small{color:#7b8580;font-size:8px;text-transform:uppercase;letter-spacing:.04em}.long-leave-pending-meta strong{margin-top:2px;color:#263a31;font-size:10px;overflow-wrap:anywhere}
      .long-leave-pending-copy{display:grid;grid-template-columns:1fr 1fr;gap:8px}.long-leave-pending-copy div{padding:9px;border-radius:9px;background:#f8faf9;color:#536159;font-size:10px;white-space:pre-wrap;overflow-wrap:anywhere}.long-leave-pending-copy strong{display:block;margin-bottom:3px;color:#263a31}
      .long-leave-decision-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:end}.long-leave-decision-row label{display:grid;gap:4px;color:#536159;font-size:10px;font-weight:800}.long-leave-decision-row input{min-width:0;padding:9px 10px}.long-leave-decision-row button{white-space:nowrap}
      .long-leave-admin-empty{padding:14px;border-radius:11px;background:#edf8f2;color:#17603b;font-size:11px;text-align:center}
      .leave-overlap-panel{display:grid;gap:10px;padding:13px;border:1px solid #d8e4dd;border-radius:14px;background:#fff}.leave-overlap-head{display:flex;align-items:center;gap:8px}.leave-overlap-head h3{margin:0;font-size:15px}.leave-overlap-controls{display:grid;grid-template-columns:1fr 1fr 1fr 120px auto;gap:8px;align-items:end}.leave-overlap-controls label{display:grid;gap:4px;color:#536159;font-size:9px;font-weight:850}.leave-overlap-controls select,.leave-overlap-controls input{min-width:0;padding:8px}.leave-heatmap{display:grid;grid-template-columns:repeat(auto-fit,minmax(92px,1fr));gap:6px}.leave-heat-day{min-height:76px;padding:8px;border:1px solid #dfe8e2;border-radius:10px;background:#f5f8f6}.leave-heat-day.alert{border-color:#d99832;background:#fff5df}.leave-heat-day time,.leave-heat-day strong,.leave-heat-day small{display:block}.leave-heat-day time{font-size:9px;color:#6b786f}.leave-heat-day strong{margin-top:4px;font-size:13px}.leave-heat-day small{margin-top:3px;font-size:8px;color:#65746c}.leave-overlap-alert{display:flex;align-items:flex-start;gap:7px;padding:9px;border-radius:10px;background:#fff0d5;color:#7a5313;font-size:10px;font-weight:800}
      @media(max-width:820px){.long-leave-admin-panel{padding:12px 9px}.long-leave-admin-heading h2{font-size:16px}.long-leave-admin-heading p{font-size:9px}.long-leave-admin-heading button{padding:7px;font-size:9px}.long-leave-pending-card{padding:10px}.long-leave-pending-head strong{font-size:12px}.long-leave-request-type{font-size:8px}.long-leave-pending-meta{grid-template-columns:1fr 1fr;gap:5px}.long-leave-pending-copy{grid-template-columns:1fr}.long-leave-decision-row{grid-template-columns:1fr 1fr}.long-leave-decision-row label{grid-column:1/-1}.long-leave-decision-row button{width:100%;padding:8px 5px;font-size:9px}.leave-overlap-controls{grid-template-columns:1fr 1fr}.leave-overlap-controls button{grid-column:1/-1}}
    `}</style>
    <div data-ui-key="u-7fd1bacfe432" className="long-leave-admin-heading">
      <div>
        <h2>ADMIN · ĐƠN CHỜ DUYỆT</h2>
        <p>Phép năm / Nghỉ làm đẹp / Nghỉ việc · hiển thị đầy đủ thông tin trước khi quyết định.</p>
      </div>
      <button data-ui-key="u-bbacc6bc597e" data-ui-label-default="Làm mới" type="button" className="secondary-button compact" onClick={load} disabled={loading}><RefreshCw size={14} className={loading ? 'spin' : ''} /><UiCustomText uiKey="u-bbacc6bc597e"> Làm mới</UiCustomText></button>
    </div>
    {notice && <div className={notice.status === 'success' ? 'success-box' : 'error-box'}>{notice.message}</div>}
    <section data-ui-key="u-fc2038c8cf81" className="leave-overlap-panel">
      <div className="leave-overlap-head"><CalendarRange size={18}/><h3>TỔNG QUAN & KIỂM TRA XUNG ĐỘT NGHỈ PHÉP</h3></div>
      <div className="leave-overlap-controls"><label>Từ ngày<VeraDateInput value={overlapFilters.start} onChange={(event) => setOverlapFilters({ ...overlapFilters, start:event.target.value })}/></label><label>Đến ngày<VeraDateInput value={overlapFilters.end} min={overlapFilters.start} onChange={(event) => setOverlapFilters({ ...overlapFilters, end:event.target.value })}/></label><label>Bộ phận<select value={overlapFilters.department} onChange={(event) => setOverlapFilters({ ...overlapFilters, department:event.target.value })}><option value="">Tất cả</option><option value="nhanvien">Nhân viên</option><option value="letan">Lễ tân</option><option value="locker">Locker</option><option value="tapvu">Tạp vụ</option><option value="quanly">Quản lý</option></select></label><label>Ngưỡng cảnh báo (%)<input type="number" min="1" max="100" value={overlapFilters.threshold} onChange={(event) => setOverlapFilters({ ...overlapFilters, threshold:event.target.value })}/></label><button data-ui-key="u-9d31be5e1f85" data-ui-label-default="Kiểm tra" type="button" className="secondary-button compact" onClick={loadOverlap}><UiCustomText uiKey="u-9d31be5e1f85">Kiểm tra</UiCustomText></button></div>
      {overlap?.has_alert && <div className="leave-overlap-alert"><AlertTriangle size={16}/> Có ngày vượt ngưỡng {overlapFilters.threshold}% nhân sự của bộ phận cùng nghỉ.</div>}
      <div className="leave-heatmap">{overlap?.days?.map((day) => <article className={`leave-heat-day ${day.has_alert ? 'alert' : ''}`} key={day.date}><time>{vnDate(day.date)}</time><strong>{day.leave_count} người nghỉ</strong><small>{day.departments.map((dept) => `${dept.department_id}: ${dept.leave_count}/${dept.headcount}${dept.exceeds_threshold ? ' ⚠' : ''}`).join(' · ') || 'Không trùng lịch'}</small></article>)}</div>
    </section>
    {!loading && rows.length === 0 ? <div className="long-leave-admin-empty"><CheckCircle2 size={15} /> Không có đơn đang chờ Admin duyệt.</div> : null}
    <div className="long-leave-pending-list">
      {rows.map((item) => {
        const annual = item.request_type === 'Nghỉ Phép năm'
        const resignation = item.request_type === 'Nghỉ việc'
        const conflictDays = overlap?.days?.filter((day) => day.date >= item.start_date && day.date <= item.end_date && day.departments.some((dept) => dept.exceeds_threshold && dept.usernames.includes(item.employee_name))) || []
        return <article className="long-leave-pending-card" key={item.id}>
          <div className="long-leave-pending-head">
            <div><strong>{item.employee_name}</strong><small>{item.id} · gửi {formatVeraDate(item.submitted_date, '—')} {item.submitted_time || ''}</small></div>
            <span className={`long-leave-request-type ${annual ? 'annual' : ''} ${resignation ? 'resignation' : ''}`}>{item.request_type}</span>
          </div>
          <div className="long-leave-pending-meta">
            <span><small>Từ ngày</small><strong>{vnDate(item.start_date)}</strong></span>
            <span><small>Đến ngày</small><strong>{vnDate(item.end_date)}</strong></span>
            <span><small>Số ngày</small><strong>{item.days}</strong></span>
            <span><small>{annual ? 'Phép năm còn' : (resignation ? 'Ngày bắt đầu làm' : 'Email')}</small><strong>{annual ? `${moneyLike(item.annual_leave_balance)} ngày` : (resignation ? (item.employment_start_date || '—') : (item.email || '—'))}</strong></span>
          </div>
          <div className="long-leave-pending-copy">
            <div><strong>Nội dung / lý do</strong>{item.reason || '—'}</div>
            <div><strong>Chi tiết</strong>{item.detail || '—'}</div>
          </div>
          {!!conflictDays.length && <div className="leave-overlap-alert"><AlertTriangle size={16}/> Cảnh báo: {conflictDays.length} ngày trong đơn này vượt ngưỡng nghỉ đồng thời của bộ phận. Hãy kiểm tra heatmap trước khi duyệt.</div>}
          <div className="long-leave-decision-row">
            <label>Lý do không duyệt
              <input value={rejectReasons[item.id] || ''} onChange={(event) => setRejectReasons((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="Chỉ cần nhập khi không duyệt" />
            </label>
            <button data-ui-key="u-ce40dc821d5a" data-ui-label-default="Duyệt đơn" type="button" className="primary-button" onClick={() => decide(item, 'approve')} disabled={busyId === item.id}><CheckCircle2 size={15} /><UiCustomText uiKey="u-ce40dc821d5a"> Duyệt đơn</UiCustomText></button>
            <button data-ui-key="u-41b7049b7e71" data-ui-label-default="Không duyệt" type="button" className="danger-button" onClick={() => decide(item, 'reject')} disabled={busyId === item.id}><XCircle size={15} /><UiCustomText uiKey="u-41b7049b7e71"> Không duyệt</UiCustomText></button>
          </div>
          {busyId === item.id && <div className="setup-note"><Clock3 size={14} /> Đang cập nhật và đồng bộ hệ thống cũ…</div>}
        </article>
      })}
    </div>
  </section>
}
