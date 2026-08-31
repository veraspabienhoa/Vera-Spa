import { Activity, Archive, BellRing, CalendarDays, Download, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'
import { disablePushNotifications, enablePushNotifications, readPushState, syncExistingPushSubscription } from '../lib/pushNotifications'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const formatTime = (value) => value ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value)) : '—'
const labels = { insert: 'Đăng ký mới', update: 'Sửa lịch nghỉ', delete: 'Xóa lịch nghỉ' }
const snapshotFields = [
  ['employee_name', 'Nhân viên'], ['leave_date', 'Ngày'], ['leave_reason', 'Lý do nghỉ'],
  ['leave_type', 'Loại nghỉ'], ['detail', 'Chi tiết'], ['calculated_days', 'Số ngày tính'],
  ['accumulated_leave', 'Phép cộng dồn'], ['penalty', 'Phạt vi phạm'], ['updated_by', 'Người cập nhật'],
]
const showValue = (value) => value === null || value === undefined || value === '' ? '—' : String(value)

const dateText = (value) => {
  const date = new Date(value)
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}
const today = () => dateText(new Date())
const addDays = (value, days) => { const next = new Date(value); next.setDate(next.getDate() + days); return next }
const FILTERS = ['Hôm Qua', 'Hôm nay', 'Tuần Trước', 'Tuần này', 'Tháng trước', 'Tháng này', 'Tùy chỉnh']
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

function FieldChanges({ item }) {
  const changes = item.field_changes || []
  if (!changes.length) return null
  return <div className="audit-field-grid">
    {changes.map((change) => <div className="audit-field-change" key={`${item.id}-${change.field}`}>
      <strong>{change.label || change.field}</strong>
      {item.event_type === 'insert' && <span>{showValue(change.after)}</span>}
      {item.event_type === 'delete' && <span>{showValue(change.before)}</span>}
      {item.event_type === 'update' && <span><del>{showValue(change.before)}</del><b> → </b><ins>{showValue(change.after)}</ins></span>}
    </div>)}
  </div>
}

function Snapshot({ item }) {
  const data = item.old_data || {}
  return <div className="audit-snapshot-grid">
    {snapshotFields.map(([key, label]) => <div key={`${item.id}-${key}`}><span>{label}</span><strong>{showValue(data[key])}</strong></div>)}
  </div>
}

export default function AdminChangesPage() {
  const initial = useMemo(() => rangeFor('Hôm nay'), [])
  const [period, setPeriod] = useState('Hôm nay')
  const [start, setStart] = useState(initial[0])
  const [end, setEnd] = useState(initial[1])
  const [actorSearch, setActorSearch] = useState('')
  const [actor, setActor] = useState('')
  const [data, setData] = useState({ changes: [], archive: [] })
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')
  const [push, setPush] = useState({ loading: true, supported: false, subscribed: false })
  const [pushBusy, setPushBusy] = useState(false)
  const [pushNotice, setPushNotice] = useState('')

  const params = useCallback(() => {
    const query = new URLSearchParams({ start, end })
    if (actor.trim()) query.set('actor', actor.trim())
    return query.toString()
  }, [actor, end, start])

  const load = useCallback(async () => {
    setBusy(true); setError('')
    try { setData(await requestJson(`/v2/admin/changes-v41?${params()}`)) }
    catch (e) { setError(e.message || 'Không tải được Thay đổi hệ thống.') }
    finally { setBusy(false) }
  }, [params])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const timer = window.setTimeout(() => setActor(actorSearch.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [actorSearch])
  useEffect(() => {
    let active = true
    syncExistingPushSubscription().then((state) => { if (active) setPush({ ...state, loading: false }) })
      .catch(() => readPushState().then((state) => { if (active) setPush({ ...state, loading: false }) })
        .catch((pushError) => { if (active) setPush({ loading: false, supported: false, subscribed: false, reason: pushError.message }) }))
    return () => { active = false }
  }, [])

  const choosePeriod = (next) => {
    setPeriod(next)
    if (next === 'Tùy chỉnh') return
    const [nextStart, nextEnd] = rangeFor(next)
    setStart(nextStart); setEnd(nextEnd)
  }

  const actors = useMemo(() => Array.from(new Set([
    ...(data.changes || []).map((item) => item.actor),
    ...(data.archive || []).map((item) => item.actor),
  ].filter(Boolean))).sort((a, b) => a.localeCompare(b, 'vi')), [data])

  const exportExcel = async () => {
    setExporting(true); setError('')
    try { await downloadExcel(`/v2/admin/changes-v41/export.xlsx?${params()}`, 'VERA_ThayDoiHeThong.xlsx') }
    catch (e) { setError(e.message || 'Không export được Thay đổi hệ thống.') }
    finally { setExporting(false) }
  }

  const togglePush = async () => {
    setPushBusy(true); setPushNotice(''); setError('')
    try {
      const state = push.subscribed ? await disablePushNotifications() : await enablePushNotifications()
      setPush({ ...state, loading: false })
      setPushNotice(state.subscribed
        ? 'Đã bật thông báo cập nhật tức thời cho Admin trên thiết bị này.'
        : 'Đã tắt thông báo cập nhật trên thiết bị này.')
    } catch (pushError) {
      setError(pushError.message || 'Không thay đổi được trạng thái thông báo.')
    } finally {
      setPushBusy(false)
    }
  }

  return <div className="feature-page">
    <style>{`
      .audit-detailed article{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:14px;align-items:start}
      .audit-detailed article>div{min-width:0}.audit-detailed p{margin:4px 0 8px}
      .audit-field-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:6px 10px;margin-top:8px}
      .audit-field-change{border:1px solid #e2e8e4;border-radius:9px;padding:7px 9px;background:#fbfcfb;display:flex;flex-direction:column;gap:3px}
      .audit-field-change strong{font-size:11px;text-transform:uppercase;color:#66756d}.audit-field-change span{font-size:13px;overflow-wrap:anywhere}
      .audit-field-change del{color:#9b3b3b}.audit-field-change ins{color:#176342;text-decoration:none;font-weight:700}
      .audit-archive{margin-top:18px}.audit-archive-list{display:grid;gap:10px}.audit-archive-item{border:1px solid #eadfce;border-radius:12px;padding:12px;background:#fffdf9}
      .audit-archive-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.audit-archive-head small{color:#786d62}
      .audit-snapshot-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:7px}.audit-snapshot-grid div{display:flex;flex-direction:column;gap:2px}.audit-snapshot-grid span{font-size:11px;color:#778179;text-transform:uppercase}.audit-snapshot-grid strong{font-size:13px;overflow-wrap:anywhere}
      .audit-filter-buttons{display:flex;flex-wrap:wrap;gap:7px;width:100%}.audit-filter-buttons button{padding:8px 11px}.audit-toolbar-content{display:grid;gap:10px;width:100%}.audit-search-line{display:flex;gap:8px;align-items:end;flex-wrap:wrap}.audit-search-line label{display:flex;flex:1;min-width:240px;flex-direction:column;gap:5px;font-size:12px;font-weight:800}.audit-custom-range{display:flex;gap:10px;flex-wrap:wrap}
      .admin-change-push{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:14px}.admin-change-push>div{min-width:0}.admin-change-push h3{margin:2px 0 4px;font-size:14px}.admin-change-push p{margin:0;color:#68736f;font-size:12px;line-height:1.45}.admin-change-push small{display:block;margin-top:5px;color:#176342;font-weight:800}
      @media(max-width:640px){.audit-detailed article{grid-template-columns:1fr}.audit-detailed time{font-size:11px}.audit-field-grid{grid-template-columns:1fr}.audit-snapshot-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.audit-filter-buttons{display:grid;grid-template-columns:repeat(2,1fr)}.audit-filter-buttons button:last-child{grid-column:1/-1}.audit-search-line label{min-width:100%}.admin-change-push{align-items:stretch;flex-direction:column}.admin-change-push button{width:100%}}
    `}</style>
    <div className="page-heading"><div><span className="eyebrow"><Activity size={14} /> Admin</span><h1>THAY ĐỔI HỆ THỐNG</h1><p>Tự động lọc theo người thực hiện khi gõ tên, lọc thời gian, xem chi tiết trước/sau và export Excel.</p></div><div style={{display:'flex',gap:8,flexWrap:'wrap'}}><button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button><button className="secondary-button" onClick={exportExcel} disabled={exporting}><Download size={16} /> {exporting ? 'Đang xuất…' : 'Export Excel'}</button></div></div>
    {error && <div className="error-box">{error}</div>}

    <section className="panel admin-change-push">
      <div><span className="eyebrow"><BellRing size={14} /> Màn hình khóa</span><h3>THÔNG BÁO CẬP NHẬT TỨC THỜI</h3><p>Mỗi Đăng ký mới, Sửa hoặc Xóa trong Thay đổi hệ thống sẽ gửi chi tiết tới thiết bị Admin đã bật thông báo. Trên điện thoại có thể vuốt để xóa; nếu hệ điều hành hiển thị action, có nút Xóa ngay trên thông báo.</p>{pushNotice && <small>{pushNotice}</small>}{!push.loading && !push.supported && <small>{push.reason || 'Thiết bị này chưa hỗ trợ Web Push.'}</small>}</div>
      <button type="button" className={push.subscribed ? 'danger-button' : 'primary-button'} onClick={togglePush} disabled={push.loading || pushBusy || !push.supported}><BellRing size={16} /> {pushBusy ? 'Đang xử lý…' : (push.subscribed ? 'Tắt thông báo thiết bị này' : 'Bật thông báo Admin')}</button>
    </section>

    <section className="panel data-toolbar"><div className="audit-toolbar-content">
      <div className="audit-filter-buttons" role="group" aria-label="Lọc thời gian thay đổi hệ thống">{FILTERS.map((item) => <button type="button" key={item} className={period === item ? 'primary-button' : 'secondary-button'} onClick={() => choosePeriod(item)}>{item}</button>)}</div>
      {period === 'Tùy chỉnh' && <div className="audit-custom-range"><label><CalendarDays size={15}/> Từ ngày<input type="date" value={start} onChange={(e) => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value) }}/></label><label><CalendarDays size={15}/> Đến ngày<input type="date" min={start} value={end} onChange={(e) => setEnd(e.target.value)}/></label></div>}
      <div className="audit-search-line"><label>Người thực hiện<input type="search" value={actorSearch} onChange={(e) => setActorSearch(e.target.value)} placeholder="Tìm tên người thực hiện" list="audit-actors"/></label><datalist id="audit-actors">{actors.map((value) => <option key={value} value={value}/>)}</datalist><div className="audit-total">{data.changes?.length || 0} thay đổi</div></div>
    </div></section>

    <section className="panel audit-list audit-detailed">{(data.changes || []).map((item) => <article key={item.id}><span className={`audit-operation ${item.event_type}`}>{labels[item.event_type] || item.event_type}</span><div><strong>{item.employee_name || 'Lịch nghỉ'}</strong><p>{item.detail || 'Thay đổi lịch nghỉ'}</p><FieldChanges item={item} />{item.actor && <small>Người thực hiện: <b>{item.actor}</b></small>}</div><time>{formatTime(item.created_at)}</time></article>)}{!data.changes?.length && <div className="setup-note">Không có thay đổi phù hợp bộ lọc.</div>}</section>

    <section className="panel audit-archive"><div className="panel-title-row"><div><span className="eyebrow"><Archive size={14} /> Chỉ Admin</span><h2>BẢN LỊCH NGHỈ TRƯỚC KHI SỬA / XÓA · LƯU 30 NGÀY</h2><p>Bản dữ liệu trước thao tác được giữ độc lập trong 30 ngày và áp dụng cùng bộ lọc thời gian/người thực hiện phía trên.</p></div><div className="audit-total">{data.archive?.length || 0} bản lưu</div></div><div className="audit-archive-list">{(data.archive || []).map((item) => <article className="audit-archive-item" key={`archive-${item.id}`}><div className="audit-archive-head"><div><span className={`audit-operation ${item.event_type}`}>{item.event_type === 'delete' ? 'BẢN ĐÃ XÓA' : 'BẢN TRƯỚC KHI SỬA'}</span> <strong>{item.employee_name || item.old_data?.employee_name || 'Lịch nghỉ'}</strong></div><small>Lưu đến {formatTime(item.expires_at)}</small></div><Snapshot item={item}/><div style={{marginTop:8}}><small>Thao tác lúc {formatTime(item.created_at)}{item.actor ? ` · ${item.actor}` : ''}</small></div></article>)}{!data.archive?.length && <div className="setup-note">Không có bản lưu phù hợp bộ lọc.</div>}</div></section>
  </div>
}
