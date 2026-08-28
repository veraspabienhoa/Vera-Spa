import { Activity, Archive, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

const formatTime = (value) => value ? new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value)) : '—'
const labels = { insert: 'Đăng ký mới', update: 'Sửa lịch nghỉ', delete: 'Xóa lịch nghỉ' }
const snapshotFields = [
  ['employee_name', 'Nhân viên'], ['leave_date', 'Ngày'], ['leave_reason', 'Lý do nghỉ'],
  ['leave_type', 'Loại nghỉ'], ['detail', 'Chi tiết'], ['calculated_days', 'Số ngày tính'],
  ['accumulated_leave', 'Phép cộng dồn'], ['penalty', 'Phạt vi phạm'], ['updated_by', 'Người cập nhật'],
]
const showValue = (value) => value === null || value === undefined || value === '' ? '—' : String(value)

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
  const [days, setDays] = useState(7)
  const [data, setData] = useState({ changes: [], archive: [] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = async () => { setBusy(true); setError(''); try { setData(await veraApi.adminChanges(days)) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  useEffect(() => { void load() }, [days]) // eslint-disable-line react-hooks/exhaustive-deps
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
      @media(max-width:640px){.audit-detailed article{grid-template-columns:1fr}.audit-detailed time{font-size:11px}.audit-field-grid{grid-template-columns:1fr}.audit-snapshot-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    `}</style>
    <div className="page-heading"><div><span className="eyebrow"><Activity size={14} /> Admin</span><h1>THAY ĐỔI HỆ THỐNG</h1><p>Hiển thị chi tiết nội dung đăng ký mới, trường đã sửa, giá trị trước/sau và lịch nghỉ đã xóa.</p></div><button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button></div>
    {error && <div className="error-box">{error}</div>}
    <section className="panel data-toolbar"><label>Khoảng xem<select value={days} onChange={(e) => setDays(Number(e.target.value))}><option value="1">24 giờ</option><option value="7">7 ngày</option><option value="14">14 ngày</option><option value="31">31 ngày</option></select></label><div className="audit-total">{data.changes?.length || 0} thay đổi</div></section>
    <section className="panel audit-list audit-detailed">{(data.changes || []).map((item) => <article key={item.id}><span className={`audit-operation ${item.event_type}`}>{labels[item.event_type] || item.event_type}</span><div><strong>{item.employee_name || 'Lịch nghỉ'}</strong><p>{item.detail || 'Thay đổi lịch nghỉ'}</p><FieldChanges item={item} />{item.actor && <small>Người thực hiện: <b>{item.actor}</b></small>}</div><time>{formatTime(item.created_at)}</time></article>)}{!data.changes?.length && <div className="setup-note">Không có thay đổi lịch nghỉ trong khoảng đã chọn.</div>}</section>

    <section className="panel audit-archive">
      <div className="panel-title-row"><div><span className="eyebrow"><Archive size={14} /> Chỉ Admin</span><h2>BẢN LỊCH NGHỈ TRƯỚC KHI SỬA / XÓA · LƯU 30 NGÀY</h2><p>Mỗi lần sửa hoặc xóa, bản dữ liệu trước thao tác được giữ độc lập trong 30 ngày rồi tự hết hạn.</p></div><div className="audit-total">{data.archive?.length || 0} bản lưu</div></div>
      <div className="audit-archive-list">{(data.archive || []).map((item) => <article className="audit-archive-item" key={`archive-${item.id}`}><div className="audit-archive-head"><div><span className={`audit-operation ${item.event_type}`}>{item.event_type === 'delete' ? 'BẢN ĐÃ XÓA' : 'BẢN TRƯỚC KHI SỬA'}</span> <strong>{item.employee_name || item.old_data?.employee_name || 'Lịch nghỉ'}</strong></div><small>Lưu đến {formatTime(item.expires_at)}</small></div><Snapshot item={item} /><div style={{marginTop:8}}><small>Thao tác lúc {formatTime(item.created_at)}{item.actor ? ` · ${item.actor}` : ''}</small></div></article>)}{!data.archive?.length && <div className="setup-note">Chưa có bản lịch nghỉ đã sửa/xóa trong 30 ngày gần đây.</div>}</div>
    </section>
  </div>
}
