import { useEffect, useMemo, useState } from 'react'
import { BarChart3, BellRing, BookOpenCheck, ClipboardCheck, FileDown, History, ImageDown, Settings2, X } from 'lucide-react'
import VeraDateInput from '../components/VeraDateInput'
import UsernameAutocomplete from '../components/UsernameAutocomplete'
import { veraApi } from '../lib/api'
import './TrainingPage.css'

const today = () => new Date().toISOString().slice(0, 10)
const emptySession = { employee_username: '', training_date: today(), start_time: '09:00', end_time: '10:00', topic: '', learning_attitude: 'Tốt', skill_grade: 'C', strengths: '', improvements: '', notes: '' }
const emptyEvaluation = { craft_score: 3, communication_score: 3, attitude_score: 3, discipline_score: 3, appearance_score: 3, hygiene_score: 3, attendance_score: 3, strengths: '', improvements: '', comments: '' }
const formatDate = (value) => value ? String(value).slice(0, 10).split('-').reverse().join('/') : '—'

function Notice({ value }) { return value ? <p className={`training-notice ${value.type}`}>{value.text}</p> : null }

function Radar({ values }) {
  const scores = [values?.craft || 0, values?.communication || 0, values?.attitude || 0, values?.conduct || 0]
  const center = 90; const radius = 64
  const point = (index, score = 5) => {
    const angle = -Math.PI / 2 + index * Math.PI / 2
    const r = radius * Number(score || 0) / 5
    return `${center + Math.cos(angle) * r},${center + Math.sin(angle) * r}`
  }
  return <div className="training-radar"><svg viewBox="0 0 180 180" role="img" aria-label="Biểu đồ radar năng lực">
    {[1, 2, 3, 4, 5].map(level => <polygon key={level} points={[0, 1, 2, 3].map(i => point(i, level)).join(' ')} className="radar-grid" />)}
    <polygon points={scores.map((score, i) => point(i, score)).join(' ')} className="radar-score" />
    <text x="90" y="13">Tay nghề</text><text x="144" y="94">Giao tiếp</text><text x="90" y="176">Thái độ</text><text x="4" y="94">Tác phong</text>
  </svg></div>
}

function ProgressChart({ points }) {
  if (!points?.length) return <div className="training-empty">Chưa có dữ liệu kỹ năng.</div>
  const width = 520; const height = 170; const pad = 28
  const xy = points.map((item, index) => ({ ...item, x: points.length === 1 ? width / 2 : pad + index * (width - pad * 2) / (points.length - 1), y: height - pad - (Number(item.skill_score) - 1) * (height - pad * 2) / 5 }))
  return <div className="training-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Tiến độ điểm kỹ năng">
    {[1, 2, 3, 4, 5, 6].map(n => <g key={n}><line x1={pad} y1={height - pad - (n - 1) * (height - pad * 2) / 5} x2={width - pad} y2={height - pad - (n - 1) * (height - pad * 2) / 5} /><text x="3" y={height - pad + 4 - (n - 1) * (height - pad * 2) / 5}>{['E','D','C','B','A','A+'][n - 1]}</text></g>)}
    <polyline points={xy.map(p => `${p.x},${p.y}`).join(' ')} />
    {xy.map(p => <circle key={p.id} cx={p.x} cy={p.y} r="5"><title>{formatDate(p.training_date)} · {p.skill_grade}</title></circle>)}
  </svg></div>
}

const evaluationCriteria = [['craft_score','Tay nghề'],['communication_score','Giao tiếp'],['attitude_score','Thái độ'],['discipline_score','Kỷ luật'],['appearance_score','Ngoại hình'],['hygiene_score','Vệ sinh'],['attendance_score','Chuyên cần']]
function CriteriaHistoryChart({ history }) {
  const evaluations = (history || []).filter(item => item.type === 'comprehensive')
  if (!evaluations.length) return <div className="training-empty">Chưa có đợt đánh giá tổng hợp hoặc xếp loại Xuất sắc.</div>
  const width = 720; const height = 250; const left = 42; const top = 20; const bottom = 42
  const colors = ['#1f6149','#c99425','#3568a8','#a64f45','#7452a3','#31898a','#8a6b31']
  const x = index => evaluations.length === 1 ? width / 2 : left + index * (width - left * 2) / (evaluations.length - 1)
  const y = score => top + (5 - Number(score || 0)) * (height - top - bottom) / 4
  return <div className="criteria-history-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Tất cả tiêu chí qua các đợt đánh giá">
    {[1,2,3,4,5].map(score => <g key={score}><line x1={left} y1={y(score)} x2={width-left} y2={y(score)}/><text x="15" y={y(score)+4}>{score}/5</text></g>)}
    {evaluationCriteria.map(([key], criterionIndex) => <polyline key={key} style={{ stroke: colors[criterionIndex] }} points={evaluations.map((item,index) => `${x(index)},${y(item.detail?.[key])}`).join(' ')}/>) }
    {evaluations.map((item,index) => <text key={item.id} x={x(index)} y={height-12}>{formatDate(item.date)}</text>)}
  </svg><div className="criteria-legend">{evaluationCriteria.map(([key,label],index) => <span key={key}><i style={{ background:colors[index] }}/>{label}</span>)}</div></div>
}

export default function TrainingPage({ user }) {
  const permissions = user?.permissions || {}
  const [data, setData] = useState(null); const [tab, setTab] = useState('sessions')
  const [busy, setBusy] = useState(false); const [notice, setNotice] = useState(null)
  const [session, setSession] = useState(emptySession)
  const [editingSessionId, setEditingSessionId] = useState('')
  const [reportEmployee, setReportEmployee] = useState(''); const [report, setReport] = useState(null)
  const [historyDate, setHistoryDate] = useState('')
  const [evaluatorPickerRole, setEvaluatorPickerRole] = useState('all')
  const [evaluationDrafts, setEvaluationDrafts] = useState({})
  const [notificationRecipients, setNotificationRecipients] = useState([])
  const [settingsEmployeeFilter, setSettingsEmployeeFilter] = useState('')
  const [settingsDepartmentFilter, setSettingsDepartmentFilter] = useState('all')
  const [notificationDetail, setNotificationDetail] = useState(null)
  const [cycle, setCycle] = useState({ name: '', start_date: today(), end_date: today(), employee_usernames: [], evaluator_usernames: [], instructions: '' })

  const load = async () => { setBusy(true); try { const result = await veraApi.trainingBootstrap(); setData(result); setNotificationRecipients((result.notification_recipients || []).map(x => x.username)) } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  useEffect(() => { load() }, [])
  const activeAssignments = useMemo(() => (data?.assignments || []).filter(item => item.cycle_status === 'active'), [data])

  const saveSession = async (event) => { event.preventDefault(); setBusy(true); try { if (editingSessionId) await veraApi.updateTrainingSession(editingSessionId, session); else await veraApi.createTrainingSession(session); setEditingSessionId(''); setSession(current => ({ ...emptySession, employee_username: current.employee_username })); setNotice({ type: 'success', text: editingSessionId ? 'Đã cập nhật nhật ký đào tạo.' : 'Đã lưu nhật ký đào tạo.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const saveEvaluation = async (assignment, submit) => { setBusy(true); try { await veraApi.saveTrainingEvaluation(assignment.id, { ...emptyEvaluation, ...assignment, ...(evaluationDrafts[assignment.id] || {}), submit }); setNotice({ type: 'success', text: submit ? 'Đã gửi phiếu đánh giá.' : 'Đã lưu bản nháp.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const openReport = async (targetTab = 'report') => { if (!reportEmployee) { setNotice({ type:'error', text:'Hãy chọn nhân viên.' }); return } setBusy(true); try { const dateFilters = targetTab === 'history' && historyDate ? { date_from:historyDate, date_to:historyDate } : {}; setReport(await veraApi.trainingReport(reportEmployee, { q:'', rating:'all', ...dateFilters, evaluator_role:'all' })); setTab(targetTab) } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const exportEvaluation = async (id, format) => { setBusy(true); try { await veraApi.exportTrainingEvaluation(id, format); setNotice({ type: 'success', text: `Đã xuất kết quả ${format.toUpperCase()}.` }) } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const createCycle = async (event) => { event.preventDefault(); setBusy(true); try { await veraApi.createEvaluationCycle(cycle); setNotice({ type: 'success', text: 'Đã tạo đợt đánh giá ở trạng thái nháp.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const toggleList = (key, value) => setCycle(current => ({ ...current, [key]: current[key].includes(value) ? current[key].filter(item => item !== value) : [...current[key], value] }))
  const toggleCycleEmployee = (username) => setCycle(current => {
    const employee_usernames = current.employee_usernames.includes(username) ? current.employee_usernames.filter(item => item !== username) : [...current.employee_usernames, username]
    const roles = new Set(employee_usernames.map(name => data?.people?.find(item => item.username === name)?.role))
    if (roles.size && [...roles].every(role => role === 'nhanvien')) setEvaluatorPickerRole('leader')
    else if (roles.size && [...roles].every(role => ['letan','locker','tapvu'].includes(role))) setEvaluatorPickerRole('quanly')
    else setEvaluatorPickerRole('all')
    return { ...current, employee_usernames }
  })
  const saveNotificationRecipients = async () => { setBusy(true); try { await veraApi.saveTrainingNotificationRecipients(notificationRecipients); setNotice({ type: 'success', text: 'Đã lưu danh sách nhận thông báo đánh giá.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const openNotification = async (item) => { try { setNotificationDetail(await veraApi.trainingNotificationDetail(item.id)); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } }
  const evaluatorCandidates = (data?.evaluators || []).filter(item => evaluatorPickerRole === 'all' || item.role === evaluatorPickerRole)
  const departments = [...new Set((data?.people || []).map(item => item.department).filter(Boolean))].sort((a,b) => a.localeCompare(b,'vi'))
  const filteredNotificationPeople = (data?.people || []).filter(item => item.role !== 'admin' && (settingsDepartmentFilter === 'all' || item.department === settingsDepartmentFilter) && (!settingsEmployeeFilter || `${item.full_name} ${item.username}`.toLocaleLowerCase('vi').includes(settingsEmployeeFilter.toLocaleLowerCase('vi'))))
  const unreadNotifications = (data?.notifications || []).filter(item => !item.is_read).length

  return <main className="training-page">
    <header><div><p className="eyebrow">NHÂN SỰ VERA SPA</p><h1>Đào tạo & đánh giá nhân viên</h1></div></header>
    <Notice value={notice} />
    <nav className="training-tabs" aria-label="Chức năng đào tạo">
      <button className={tab === 'sessions' ? 'active' : ''} onClick={() => setTab('sessions')}><BookOpenCheck size={18}/>Đào tạo hằng ngày</button>
      {permissions.training_evaluate && <button className={tab === 'evaluate' ? 'active' : ''} onClick={() => setTab('evaluate')}><ClipboardCheck size={18}/>Phiếu đánh giá <span>{activeAssignments.filter(x => x.status !== 'submitted').length}</span></button>}
      <button className={tab === 'report' ? 'active' : ''} onClick={() => setTab('report')}><BarChart3 size={18}/>Báo cáo tiến độ</button>
      <button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}><History size={18}/>Lịch sử</button>
      <button className={tab === 'notifications' ? 'active' : ''} onClick={() => setTab('notifications')}><BellRing size={18}/>Thông báo {unreadNotifications > 0 && <span>{unreadNotifications}</span>}</button>
      {data?.is_admin && <button className={tab === 'admin' ? 'active' : ''} onClick={() => setTab('admin')}><Settings2 size={18}/>Thiết lập</button>}
    </nav>

    {tab === 'sessions' && <section className="training-grid">
      {permissions.training_session_create && <form className="training-card" onSubmit={saveSession}><h2>Ghi nhận buổi đào tạo</h2>
        <div className="training-form-grid"><label>Học viên được đào tạo<select required value={session.employee_username} onChange={e => setSession({ ...session, employee_username: e.target.value })}><option value="">Chọn học viên</option>{data?.training_students?.map(x => <option key={x.username} value={x.username}>{x.full_name}</option>)}</select></label>
        <label>Ngày đào tạo<VeraDateInput required value={session.training_date} onChange={e => setSession({ ...session, training_date: e.target.value })}/></label>
        <label>Từ giờ<input required type="time" value={session.start_time} onChange={e => setSession({ ...session, start_time: e.target.value })}/></label><label>Đến giờ<input required type="time" value={session.end_time} onChange={e => setSession({ ...session, end_time: e.target.value })}/></label>
        <label className="wide">Nội dung/kỹ năng đào tạo<input value={session.topic} onChange={e => setSession({ ...session, topic: e.target.value })} placeholder="Ví dụ: Massage cổ vai gáy"/></label>
        <label>Tinh thần học tập<select value={session.learning_attitude} onChange={e => setSession({ ...session, learning_attitude: e.target.value })}>{['Tốt','Khá','Trung bình','Kém'].map(x => <option key={x}>{x}</option>)}</select></label>
        <label>Điểm kỹ năng<select value={session.skill_grade} onChange={e => setSession({ ...session, skill_grade: e.target.value })}>{['A+','A','B','C','D','E'].map(x => <option key={x}>{x}</option>)}</select></label>
        <label className="wide">Điểm mạnh<textarea value={session.strengths} onChange={e => setSession({ ...session, strengths: e.target.value })}/></label><label className="wide">Điểm cần khắc phục<textarea value={session.improvements} onChange={e => setSession({ ...session, improvements: e.target.value })}/></label><label className="wide">Ghi chú<textarea value={session.notes} onChange={e => setSession({ ...session, notes: e.target.value })}/></label></div>
        <div className="button-row">{editingSessionId && <button type="button" className="secondary-button" onClick={() => { setEditingSessionId(''); setSession(emptySession) }}>Hủy sửa</button>}<button className="primary-button" disabled={busy}>{editingSessionId ? 'Cập nhật buổi đào tạo' : 'Lưu buổi đào tạo'}</button></div></form>}
    </section>}

    {tab === 'evaluate' && <section className="training-card"><h2>Phiếu đánh giá được phân công</h2>{!activeAssignments.length && <div className="training-empty">Hiện chưa có đợt đánh giá đang mở.</div>}{activeAssignments.map(item => { const draft = { ...emptyEvaluation, ...item, ...(evaluationDrafts[item.id] || {}) }; return <article className="evaluation-form" key={item.id}><h3>{item.employee_name} <small>· {item.cycle_name}</small></h3><div className="score-grid">{[['craft_score','Kỹ năng tay nghề'],['communication_score','Giao tiếp'],['attitude_score','Thái độ'],['discipline_score','Kỷ luật'],['appearance_score','Trang phục/ngoại hình'],['hygiene_score','Vệ sinh cá nhân'],['attendance_score','Chuyên cần']].map(([key,label]) => <label key={key}>{label}<select value={draft[key]} onChange={e => setEvaluationDrafts(current => ({ ...current, [item.id]: { ...(current[item.id] || {}), [key]: Number(e.target.value) } }))}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n}/5</option>)}</select></label>)}</div>{[['strengths','Điểm mạnh'],['improvements','Điểm cần cải thiện'],['comments','Nhận xét']].map(([key,label]) => <label key={key}>{label}<textarea value={draft[key] || ''} onChange={e => setEvaluationDrafts(current => ({ ...current, [item.id]: { ...(current[item.id] || {}), [key]: e.target.value } }))}/></label>)}<div className="button-row"><button type="button" className="secondary-button" onClick={() => saveEvaluation(item, false)}>Lưu nháp</button><button type="button" className="primary-button" onClick={() => saveEvaluation(item, true)}>Gửi đánh giá</button></div></article>})}</section>}

    {tab === 'report' && <section><div className="training-report-filter compact-filter"><UsernameAutocomplete label="Nhân viên" searchOnly placeholder="Tìm tên hoặc username nhân viên…" options={data?.employees || []} value={reportEmployee} onChange={setReportEmployee}/><button className="primary-button" onClick={() => openReport('report')}>Xem tiến độ</button></div>{report && <div className="training-grid"><div className="training-card"><h2>Tiến độ kỹ năng</h2><ProgressChart points={report.progress}/></div><div className="training-card"><h2>Năng lực kỳ gần nhất</h2><Radar values={report.latest_radar}/>{report.latest_radar && <p className="center muted">{report.latest_radar.cycle_name}</p>}</div></div>}</section>}

    {tab === 'history' && <section><div className="training-report-filter history-filter"><UsernameAutocomplete label="Tên nhân viên" searchOnly placeholder="Tìm tên hoặc username nhân viên…" options={data?.employees || []} value={reportEmployee} onChange={setReportEmployee}/><label>Ngày đào tạo<VeraDateInput value={historyDate} onChange={e => setHistoryDate(e.target.value)}/></label><button className="primary-button" onClick={() => openReport('history')}>Tổng hợp lịch sử</button></div>{report && <div className="training-grid"><div className="training-card wide-card"><h2>Tất cả tiêu chí qua các đợt đánh giá</h2><CriteriaHistoryChart history={report.history}/></div><div className="training-card wide-card"><h2>Lịch sử Đào tạo & Đánh giá <small>({report.history_total})</small></h2><div className="timeline">{report.history?.map(item => <article className={`training-history-item ${item.type}`} key={`${item.type}-${item.id}`}><time>{formatDate(item.date)}</time><div><span className={`history-kind ${item.type}`}>{item.type === 'daily' ? 'Đào tạo hằng ngày' : 'Đánh giá tổng hợp'}</span><strong>{item.title}</strong><p>Người thực hiện: {item.evaluator_name} · Xếp loại: {item.rating_label}</p>{item.type === 'daily' ? <p className="muted">Kỹ năng: {item.detail.skill_grade} · Tinh thần: {item.detail.learning_attitude}{item.detail.improvements ? ` · Cần cải thiện: ${item.detail.improvements}` : ''}</p> : <><p className="muted">{evaluationCriteria.map(([key,label]) => `${label} ${item.detail[key]}/5`).join(' · ')}</p><div className="history-export"><button type="button" onClick={() => exportEvaluation(item.id,'pdf')}><FileDown size={14}/> PDF</button><button type="button" onClick={() => exportEvaluation(item.id,'png')}><ImageDown size={14}/> Ảnh PNG</button></div></>}</div></article>)}{!report.history?.length && <div className="training-empty">Chưa có lịch sử phù hợp bộ lọc.</div>}</div></div></div>}</section>}

    {tab === 'notifications' && <section className="training-card"><h2>Thông báo Đào tạo & Đánh giá</h2><div className="training-notification-list">{data?.notifications?.map(item => <button type="button" className={item.is_read ? '' : 'unread'} key={item.id} onClick={() => openNotification(item)}><BellRing size={18}/><span><strong>{item.title}</strong><small>{item.body}</small></span><time>{new Date(item.created_at).toLocaleString('vi-VN')}</time></button>)}{!data?.notifications?.length && <div className="training-empty">Chưa có thông báo.</div>}</div></section>}

    {tab === 'admin' && <section className="training-grid"><div className="training-card"><h2>Tài khoản nhận thông báo</h2><p className="muted">Admin và nhân viên được đánh giá luôn nhận thông báo. Chọn thêm các tài khoản cần nhận mọi kết quả hoàn thành.</p><div className="settings-filters"><label>Tên nhân viên<input value={settingsEmployeeFilter} onChange={e => setSettingsEmployeeFilter(e.target.value)} placeholder="Tìm theo tên…"/></label><label>Bộ phận<select value={settingsDepartmentFilter} onChange={e => setSettingsDepartmentFilter(e.target.value)}><option value="all">Tất cả bộ phận</option>{departments.map(item => <option key={item} value={item}>{item}</option>)}</select></label></div><div className="check-list">{filteredNotificationPeople.map(x => <label key={x.username}><input type="checkbox" checked={notificationRecipients.includes(x.username)} onChange={() => setNotificationRecipients(current => current.includes(x.username) ? current.filter(v => v !== x.username) : [...current,x.username])}/>{x.full_name} · {x.department || x.role}</label>)}</div><button className="primary-button" disabled={busy} onClick={saveNotificationRecipients}>Lưu người nhận thông báo</button></div>
      <form className="training-card" onSubmit={createCycle}><h2>Tạo đợt đánh giá tổng hợp</h2><label>Tên đợt<input required value={cycle.name} onChange={e => setCycle({ ...cycle, name:e.target.value })} placeholder="Ví dụ: Đánh giá quý III/2026"/></label><div className="training-form-grid"><label>Từ ngày<VeraDateInput required value={cycle.start_date} onChange={e => setCycle({ ...cycle, start_date:e.target.value })}/></label><label>Đến ngày<VeraDateInput required min={cycle.start_date} value={cycle.end_date} onChange={e => setCycle({ ...cycle, end_date:e.target.value })}/></label></div><label>Hướng dẫn<textarea value={cycle.instructions} onChange={e => setCycle({ ...cycle, instructions:e.target.value })}/></label><UsernameAutocomplete label="Nhân viên được đánh giá" multiple options={data?.people?.filter(x => ['nhanvien','letan','locker','tapvu'].includes(x.role)) || []} values={cycle.employee_usernames} onToggle={toggleCycleEmployee}/><label>Loại người đánh giá<select value={evaluatorPickerRole} onChange={e => setEvaluatorPickerRole(e.target.value)}><option value="all">Tất cả</option><option value="leader">Chỉ hiển thị Leader</option><option value="quanly">Chỉ hiển thị Quản lý</option></select></label><small className="muted">Hệ thống tự gợi ý Leader khi chọn Nhân viên; Quản lý khi chọn Lễ tân/Locker/Tạp vụ.</small><UsernameAutocomplete label="Người đánh giá" multiple options={evaluatorCandidates} values={cycle.evaluator_usernames} onToggle={(username) => toggleList('evaluator_usernames',username)}/><button className="primary-button" disabled={busy || !cycle.employee_usernames.length || !cycle.evaluator_usernames.length}>Tạo đợt nháp</button></form>
      <div className="training-card wide-card"><h2>Các đợt đánh giá</h2><div className="cycle-list">{data?.cycles?.map(item => <article key={item.id}><div><strong>{item.name}</strong><small>{formatDate(item.start_date)} – {formatDate(item.end_date)} · {item.submitted_count}/{item.assignment_count} phiếu đã gửi</small></div><span className={`status ${item.status}`}>{item.status}</span>{item.status === 'draft' && <button onClick={async()=>{await veraApi.changeEvaluationCycle(item.id,'activate'); await load()}}>Kích hoạt</button>}{item.status === 'active' && <button onClick={async()=>{await veraApi.changeEvaluationCycle(item.id,'close'); await load()}}>Đóng đợt</button>}</article>)}</div></div></section>}
    {notificationDetail && <div className="training-notification-modal" role="dialog" aria-modal="true" aria-label="Chi tiết đánh giá"><div className="training-notification-dialog"><header><div><small>ĐÀO TẠO & ĐÁNH GIÁ</small><h2>{notificationDetail.notification?.title}</h2></div><button type="button" aria-label="Đóng" onClick={() => setNotificationDetail(null)}><X size={20}/></button></header><p>{notificationDetail.notification?.body}</p><dl><div><dt>Nhân viên</dt><dd>{notificationDetail.detail?.employee_name}</dd></div><div><dt>Người thực hiện</dt><dd>{notificationDetail.detail?.evaluator_name}</dd></div>{notificationDetail.detail?.topic && <div><dt>Nội dung đào tạo</dt><dd>{notificationDetail.detail.topic}</dd></div>}{notificationDetail.detail?.skill_grade && <div><dt>Kỹ năng / Tinh thần</dt><dd>{notificationDetail.detail.skill_grade} · {notificationDetail.detail.learning_attitude}</dd></div>}{notificationDetail.detail?.cycle_name && <div><dt>Đợt đánh giá</dt><dd>{notificationDetail.detail.cycle_name}</dd></div>}{notificationDetail.detail?.craft_score && <div><dt>Tay nghề / Giao tiếp / Thái độ</dt><dd>{notificationDetail.detail.craft_score}/5 · {notificationDetail.detail.communication_score}/5 · {notificationDetail.detail.attitude_score}/5</dd></div>}{(notificationDetail.detail?.comments || notificationDetail.detail?.notes) && <div><dt>Nhận xét</dt><dd>{notificationDetail.detail.comments || notificationDetail.detail.notes}</dd></div>}</dl><button type="button" className="primary-button" onClick={() => setNotificationDetail(null)}>Đóng</button></div></div>}
    {busy && !data && <div className="training-empty">Đang tải dữ liệu…</div>}
  </main>
}
