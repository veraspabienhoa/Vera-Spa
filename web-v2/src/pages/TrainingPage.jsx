import StableFeedback from '../components/StableFeedback'
import usePageRefresh from '../lib/usePageRefresh'
import TrainingNoticeDetail from '../components/TrainingNoticeDetail'
import TrainingProgressReports from '../components/TrainingProgressReports'
import { trainingIdentityKey } from '../lib/trainingReport'
import { vietnamToday } from '../lib/useVietnamToday'
import { formatVeraDate } from '../lib/veraDate'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { useEffect, useMemo, useRef, useState } from 'react'
import { BarChart3, BellRing, BookOpenCheck, ClipboardCheck, Settings2, X } from 'lucide-react'
import VeraDateInput from '../components/VeraDateInput'
import UsernameAutocomplete from '../components/UsernameAutocomplete'
import { veraApi } from '../lib/api'
import './TrainingPage.css'

const today = vietnamToday
const emptySession = { employee_username: '', training_date: today(), start_time: '09:00', end_time: '10:00', topic: '', learning_attitude: 'Tốt', skill_grade: 'C', strengths: '', improvements: '', notes: '' }
const emptyEvaluation = { craft_score: 3, communication_score: 3, attitude_score: 3, discipline_score: 3, appearance_score: 3, hygiene_score: 3, attendance_score: 3, strengths: '', improvements: '', comments: '' }
const formatDate = value => formatVeraDate(value, '—')

function Notice({ value }) { return <StableFeedback>{value && <p className={`training-notice ${value.type}`}>{value.text}</p>}</StableFeedback> }


export default function TrainingPage({ user }) {
  if (!user || (user.role !== 'admin' && user.permissions?.training_view !== true)) return null
  return <TrainingPageContent key={trainingIdentityKey(user)} user={user}/>
}

function TrainingPageContent({ user }) {
  usePageRefresh(() => load(), () => Boolean(busy || JSON.stringify(notificationRecipients) !== JSON.stringify((data?.notification_recipients || []).map(x => x.username))))
  const permissions = user?.permissions || {}
  const [data, setData] = useState(null); const [tab, setTab] = useState('sessions')
  const [busy, setBusy] = useState(false); const [notice, setNotice] = useState(null)
  const [session, setSession] = useState(emptySession)
  const [editingSessionId, setEditingSessionId] = useState('')
  const [evaluatorPickerRole, setEvaluatorPickerRole] = useState('all')
  const [evaluationDrafts, setEvaluationDrafts] = useState({})
  const [notificationRecipients, setNotificationRecipients] = useState([])
  const [settingsEmployeeFilter, setSettingsEmployeeFilter] = useState('')
  const [settingsDepartmentFilter, setSettingsDepartmentFilter] = useState('all')
  const [notificationDetail, setNotificationDetail] = useState(null)
  const [cycle, setCycle] = useState({ name: '', start_date: today(), end_date: today(), employee_usernames: [], evaluator_usernames: [], instructions: '' })

  const loadRequest = useRef(null)
  const mounted = useRef(true)
  const load = async () => {
    loadRequest.current?.abort()
    const controller = new AbortController(); loadRequest.current = controller
    setBusy(true)
    try {
      const result = await veraApi.trainingBootstrap({ signal: controller.signal })
      if (!mounted.current || controller.signal.aborted) return
      setData(result); setNotificationRecipients((result.notification_recipients || []).map(x => x.username))
    } catch (error) {
      if (mounted.current && !controller.signal.aborted) {
        if ([401, 403].includes(error.status)) setData(null)
        setNotice({ type: 'error', text: error.message })
      }
    } finally { if (mounted.current && !controller.signal.aborted) setBusy(false) }
  }
  useEffect(() => { mounted.current = true; load(); return () => { mounted.current = false; loadRequest.current?.abort() } }, [])
  const activeAssignments = useMemo(() => (data?.assignments || []).filter(item => item.cycle_status === 'active'), [data])

  const saveSession = async (event) => { event.preventDefault(); setBusy(true); try { if (editingSessionId) await veraApi.updateTrainingSession(editingSessionId, session); else await veraApi.createTrainingSession(session); setEditingSessionId(''); setSession(current => ({ ...emptySession, employee_username: current.employee_username })); setNotice({ type: 'success', text: editingSessionId ? 'Đã cập nhật nhật ký đào tạo.' : 'Đã lưu nhật ký đào tạo.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const saveEvaluation = async (assignment, submit) => { setBusy(true); try { await veraApi.saveTrainingEvaluation(assignment.id, { ...emptyEvaluation, ...assignment, ...(evaluationDrafts[assignment.id] || {}), submit }); setNotice({ type: 'success', text: submit ? 'Đã gửi phiếu đánh giá.' : 'Đã lưu bản nháp.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
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
  const departments = [...new Set([...(data?.departments || []), ...(data?.people || []).map(item => item.department).filter(Boolean)])].sort((a,b) => a.localeCompare(b,'vi'))
  const filteredNotificationPeople = (data?.people || []).filter(item => item.role !== 'admin' && (settingsDepartmentFilter === 'all' || item.department === settingsDepartmentFilter) && (!settingsEmployeeFilter || `${item.full_name} ${item.username}`.toLocaleLowerCase('vi').includes(settingsEmployeeFilter.toLocaleLowerCase('vi'))))
  const unreadNotifications = (data?.notifications || []).filter(item => !item.is_read).length

  return <main className="training-page">
    <header><div><p className="eyebrow">NHÂN SỰ VERA SPA</p><h1>Đào tạo & đánh giá nhân viên</h1></div></header>
    <Notice value={notice} />
    <nav className="training-tabs" aria-label="Chức năng đào tạo">
      <button data-ui-key="u-ca9d59496505" data-ui-label-default="Đào tạo hằng ngày" className={tab === 'sessions' ? 'active' : ''} onClick={() => setTab('sessions')}><BookOpenCheck size={18}/><UiCustomText uiKey="u-ca9d59496505">Đào tạo hằng ngày</UiCustomText></button>
      {permissions.training_evaluate && <button data-ui-key="u-37980f92c82d" data-ui-label-default="Phiếu đánh giá" className={tab === 'evaluate' ? 'active' : ''} onClick={() => setTab('evaluate')}><ClipboardCheck size={18}/><UiCustomText uiKey="u-37980f92c82d">Phiếu đánh giá </UiCustomText><span>{activeAssignments.filter(x => x.status !== 'submitted').length}</span></button>}
      <button data-ui-key="u-9cdf9644cc15" data-ui-label-default="Báo cáo tiến độ" className={tab === 'report' ? 'active' : ''} onClick={() => setTab('report')}><BarChart3 size={18}/><UiCustomText uiKey="u-9cdf9644cc15">Báo cáo tiến độ</UiCustomText></button>
      <button data-ui-key="u-dae3b92d8775" className={tab === 'notifications' ? 'active' : ''} onClick={() => setTab('notifications')}><BellRing size={18}/>Thông báo {unreadNotifications > 0 && <span>{unreadNotifications}</span>}</button>
      {data?.is_admin && <button data-ui-key="u-50030f1f58e7" data-ui-label-default="Thiết lập" className={tab === 'admin' ? 'active' : ''} onClick={() => setTab('admin')}><Settings2 size={18}/><UiCustomText uiKey="u-50030f1f58e7">Thiết lập</UiCustomText></button>}
    </nav>

    {tab === 'sessions' && <section data-ui-key="u-1c578ddfc776" className="training-grid">
      {permissions.training_session_create && <form className="training-card" onSubmit={saveSession}><h2>Ghi nhận buổi đào tạo</h2>
        <div className="training-form-grid"><label>Học viên được đào tạo<select required value={session.employee_username} onChange={e => setSession({ ...session, employee_username: e.target.value })}><option value="">Chọn học viên</option>{data?.training_students?.map(x => <option key={x.username} value={x.username}>{x.full_name}</option>)}</select></label>
        <label>Ngày đào tạo<VeraDateInput required value={session.training_date} onChange={e => setSession({ ...session, training_date: e.target.value })}/></label>
        <label>Từ giờ<input required type="time" value={session.start_time} onChange={e => setSession({ ...session, start_time: e.target.value })}/></label><label>Đến giờ<input required type="time" value={session.end_time} onChange={e => setSession({ ...session, end_time: e.target.value })}/></label>
        <label className="wide">Nội dung/kỹ năng đào tạo<input value={session.topic} onChange={e => setSession({ ...session, topic: e.target.value })} placeholder="Ví dụ: Massage cổ vai gáy"/></label>
        <label>Tinh thần học tập<select value={session.learning_attitude} onChange={e => setSession({ ...session, learning_attitude: e.target.value })}>{['Tốt','Khá','Trung bình','Kém'].map(x => <option key={x}>{x}</option>)}</select></label>
        <label>Điểm kỹ năng<select value={session.skill_grade} onChange={e => setSession({ ...session, skill_grade: e.target.value })}>{['A+','A','B','C','D','E'].map(x => <option key={x}>{x}</option>)}</select></label>
        <label className="wide">Điểm mạnh<textarea value={session.strengths} onChange={e => setSession({ ...session, strengths: e.target.value })}/></label><label className="wide">Điểm cần khắc phục<textarea value={session.improvements} onChange={e => setSession({ ...session, improvements: e.target.value })}/></label><label className="wide">Ghi chú<textarea value={session.notes} onChange={e => setSession({ ...session, notes: e.target.value })}/></label></div>
        <div className="button-row">{editingSessionId && <button data-ui-key="u-2483d27b7189" data-ui-label-default="Hủy sửa" type="button" className="secondary-button" onClick={() => { setEditingSessionId(''); setSession(emptySession) }}><UiCustomText uiKey="u-2483d27b7189">Hủy sửa</UiCustomText></button>}<button data-ui-key="u-6daeda8754cf" className="primary-button" disabled={busy}>{editingSessionId ? 'Cập nhật buổi đào tạo' : 'Lưu buổi đào tạo'}</button></div></form>}
    </section>}

    {tab === 'evaluate' && <section data-ui-key="u-d90e52851520" className="training-card"><h2>Phiếu đánh giá được phân công</h2>{!activeAssignments.length && <div className="training-empty">Hiện chưa có đợt đánh giá đang mở.</div>}{activeAssignments.map(item => { const draft = { ...emptyEvaluation, ...item, ...(evaluationDrafts[item.id] || {}) }; return <article className="evaluation-form" key={item.id}><h3>{item.employee_name} <small>· {item.cycle_name}</small></h3><div className="score-grid">{[['craft_score','Kỹ năng tay nghề'],['communication_score','Giao tiếp'],['attitude_score','Thái độ'],['discipline_score','Kỷ luật'],['appearance_score','Trang phục/ngoại hình'],['hygiene_score','Vệ sinh cá nhân'],['attendance_score','Chuyên cần']].map(([key,label]) => <label key={key}>{label}<select value={draft[key]} onChange={e => setEvaluationDrafts(current => ({ ...current, [item.id]: { ...(current[item.id] || {}), [key]: Number(e.target.value) } }))}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n}/5</option>)}</select></label>)}</div>{[['strengths','Điểm mạnh'],['improvements','Điểm cần cải thiện'],['comments','Nhận xét']].map(([key,label]) => <label key={key}>{label}<textarea value={draft[key] || ''} onChange={e => setEvaluationDrafts(current => ({ ...current, [item.id]: { ...(current[item.id] || {}), [key]: e.target.value } }))}/></label>)}<div className="button-row"><button data-ui-key="u-fd2a5bd89507" data-ui-label-default="Lưu nháp" type="button" className="secondary-button" onClick={() => saveEvaluation(item, false)}><UiCustomText uiKey="u-fd2a5bd89507">Lưu nháp</UiCustomText></button><button data-ui-key="u-56879fc53c27" data-ui-label-default="Gửi đánh giá" type="button" className="primary-button" onClick={() => saveEvaluation(item, true)}><UiCustomText uiKey="u-56879fc53c27">Gửi đánh giá</UiCustomText></button></div></article>})}</section>}

    {tab === 'report' && data && <TrainingProgressReports user={user}/>}

    {tab === 'notifications' && <section data-ui-key="u-e79111e45030" className="training-card"><h2>Thông báo Đào tạo & Đánh giá</h2><div className="training-notification-list">{data?.notifications?.map(item => <button data-ui-key="u-939063515fac" type="button" className={item.is_read ? '' : 'unread'} key={item.id} onClick={() => openNotification(item)}><BellRing size={18}/><span><strong>{item.title}</strong><small>{item.body}</small></span><time>{new Date(item.created_at).toLocaleString('vi-VN')}</time></button>)}{!data?.notifications?.length && <div className="training-empty">Chưa có thông báo.</div>}</div></section>}

    {tab === 'admin' && <section data-ui-key="u-c15b8959f611" className="training-grid"><div data-ui-key="u-3d8e6f9de626" className="training-card"><h2>Tài khoản nhận thông báo</h2><p className="muted">Admin và nhân viên được đánh giá luôn nhận thông báo. Chọn thêm các tài khoản cần nhận mọi kết quả hoàn thành.</p><UiToolbar data-ui-key="u-c6ede79957c8" className="settings-filters"><label>Tên nhân viên<input value={settingsEmployeeFilter} onChange={e => setSettingsEmployeeFilter(e.target.value)} placeholder="Tìm theo tên…"/></label><label>Bộ phận<select value={settingsDepartmentFilter} onChange={e => setSettingsDepartmentFilter(e.target.value)}><option value="all">Tất cả bộ phận</option>{departments.map(item => <option key={item} value={item}>{item}</option>)}</select></label></UiToolbar><div className="check-list">{filteredNotificationPeople.map(x => <label key={x.username}><input type="checkbox" checked={notificationRecipients.includes(x.username)} onChange={() => setNotificationRecipients(current => current.includes(x.username) ? current.filter(v => v !== x.username) : [...current,x.username])}/>{x.full_name} · {x.department || x.role}</label>)}</div><button data-ui-key="u-dac96cd358f9" data-ui-label-default="Lưu người nhận thông báo" className="primary-button" disabled={busy} onClick={saveNotificationRecipients}><UiCustomText uiKey="u-dac96cd358f9">Lưu người nhận thông báo</UiCustomText></button></div>
      <form className="training-card" onSubmit={createCycle}><h2>Tạo đợt đánh giá tổng hợp</h2><label>Tên đợt<input required value={cycle.name} onChange={e => setCycle({ ...cycle, name:e.target.value })} placeholder="Ví dụ: Đánh giá quý III/2026"/></label><div className="training-form-grid"><label>Từ ngày<VeraDateInput required value={cycle.start_date} onChange={e => setCycle({ ...cycle, start_date:e.target.value })}/></label><label>Đến ngày<VeraDateInput required min={cycle.start_date} value={cycle.end_date} onChange={e => setCycle({ ...cycle, end_date:e.target.value })}/></label></div><label>Hướng dẫn<textarea value={cycle.instructions} onChange={e => setCycle({ ...cycle, instructions:e.target.value })}/></label><UsernameAutocomplete label="Nhân viên được đánh giá" multiple options={data?.people?.filter(x => ['nhanvien','letan','locker','tapvu'].includes(x.role)) || []} values={cycle.employee_usernames} onToggle={toggleCycleEmployee}/><label>Loại người đánh giá<select value={evaluatorPickerRole} onChange={e => setEvaluatorPickerRole(e.target.value)}><option value="all">Tất cả</option><option value="leader">Chỉ hiển thị Leader</option><option value="quanly">Chỉ hiển thị Quản lý</option></select></label><small className="muted">Hệ thống tự gợi ý Leader khi chọn Nhân viên; Quản lý khi chọn Lễ tân/Locker/Tạp vụ.</small><UsernameAutocomplete label="Người đánh giá" multiple options={evaluatorCandidates} values={cycle.evaluator_usernames} onToggle={(username) => toggleList('evaluator_usernames',username)}/><button data-ui-key="u-4ad75892a784" data-ui-label-default="Tạo đợt nháp" className="primary-button" disabled={busy || !cycle.employee_usernames.length || !cycle.evaluator_usernames.length}><UiCustomText uiKey="u-4ad75892a784">Tạo đợt nháp</UiCustomText></button></form>
      <div data-ui-key="u-0bf743988c4f" className="training-card wide-card"><h2>Các đợt đánh giá</h2><div className="cycle-list">{data?.cycles?.map(item => <article key={item.id}><div><strong>{item.name}</strong><small>{formatDate(item.start_date)} – {formatDate(item.end_date)} · {item.submitted_count}/{item.assignment_count} phiếu đã gửi</small></div><span className={`status ${item.status}`}>{item.status}</span>{item.status === 'draft' && <button data-ui-key="u-30d8666e0816" data-ui-label-default="Kích hoạt" onClick={async()=>{await veraApi.changeEvaluationCycle(item.id,'activate'); await load()}}><UiCustomText uiKey="u-30d8666e0816">Kích hoạt</UiCustomText></button>}{item.status === 'active' && <button data-ui-key="u-783091ce828f" data-ui-label-default="Đóng đợt" onClick={async()=>{await veraApi.changeEvaluationCycle(item.id,'close'); await load()}}><UiCustomText uiKey="u-783091ce828f">Đóng đợt</UiCustomText></button>}</article>)}</div></div></section>}
    {notificationDetail && <TrainingNoticeDetail notice={notificationDetail} onClose={() => setNotificationDetail(null)} />}
    {busy && !data && <div className="training-empty">Đang tải dữ liệu…</div>}
  </main>
}
