import { useEffect, useMemo, useState } from 'react'
import { BarChart3, BookOpenCheck, ClipboardCheck, Settings2 } from 'lucide-react'
import VeraDateInput from '../components/VeraDateInput'
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

export default function TrainingPage({ user }) {
  const permissions = user?.permissions || {}
  const [data, setData] = useState(null); const [tab, setTab] = useState('sessions')
  const [busy, setBusy] = useState(false); const [notice, setNotice] = useState(null)
  const [session, setSession] = useState(emptySession)
  const [editingSessionId, setEditingSessionId] = useState('')
  const [reportEmployee, setReportEmployee] = useState(''); const [report, setReport] = useState(null)
  const [evaluationDrafts, setEvaluationDrafts] = useState({})
  const [scopeTrainer, setScopeTrainer] = useState(''); const [scopeEmployees, setScopeEmployees] = useState([])
  const [cycle, setCycle] = useState({ name: '', start_date: today(), end_date: today(), employee_usernames: [], evaluator_usernames: [], instructions: '' })

  const load = async () => { setBusy(true); try { const result = await veraApi.trainingBootstrap(); setData(result); if (!session.employee_username && result.training_students?.[0]) setSession(current => ({ ...current, employee_username: result.training_students[0].username })); if (!reportEmployee && result.employees?.[0]) setReportEmployee(result.employees[0].username) } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const activeAssignments = useMemo(() => (data?.assignments || []).filter(item => item.cycle_status === 'active'), [data])

  const saveSession = async (event) => { event.preventDefault(); setBusy(true); try { if (editingSessionId) await veraApi.updateTrainingSession(editingSessionId, session); else await veraApi.createTrainingSession(session); setEditingSessionId(''); setSession(current => ({ ...emptySession, employee_username: current.employee_username })); setNotice({ type: 'success', text: editingSessionId ? 'Đã cập nhật nhật ký đào tạo.' : 'Đã lưu nhật ký đào tạo.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const saveEvaluation = async (assignment, submit) => { setBusy(true); try { await veraApi.saveTrainingEvaluation(assignment.id, { ...emptyEvaluation, ...assignment, ...(evaluationDrafts[assignment.id] || {}), submit }); setNotice({ type: 'success', text: submit ? 'Đã gửi phiếu đánh giá.' : 'Đã lưu bản nháp.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const openReport = async () => { if (!reportEmployee) return; setBusy(true); try { setReport(await veraApi.trainingReport(reportEmployee)); setTab('report') } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const saveScope = async () => { setBusy(true); try { await veraApi.saveTrainingScope({ trainer_username: scopeTrainer, employee_usernames: scopeEmployees }); setNotice({ type: 'success', text: 'Đã cập nhật phạm vi quản lý.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const createCycle = async (event) => { event.preventDefault(); setBusy(true); try { await veraApi.createEvaluationCycle(cycle); setNotice({ type: 'success', text: 'Đã tạo đợt đánh giá ở trạng thái nháp.' }); await load() } catch (error) { setNotice({ type: 'error', text: error.message }) } finally { setBusy(false) } }
  const toggleList = (key, value) => setCycle(current => ({ ...current, [key]: current[key].includes(value) ? current[key].filter(item => item !== value) : [...current[key], value] }))

  return <main className="training-page">
    <header><div><p className="eyebrow">NHÂN SỰ VERA SPA</p><h1>Đào tạo & đánh giá nhân viên</h1><p>Nhật ký từng buổi học, đánh giá định kỳ và tiến độ năng lực xuyên suốt.</p></div></header>
    <Notice value={notice} />
    <nav className="training-tabs" aria-label="Chức năng đào tạo">
      <button className={tab === 'sessions' ? 'active' : ''} onClick={() => setTab('sessions')}><BookOpenCheck size={18}/>Đào tạo hằng ngày</button>
      {permissions.training_evaluate && <button className={tab === 'evaluate' ? 'active' : ''} onClick={() => setTab('evaluate')}><ClipboardCheck size={18}/>Phiếu đánh giá <span>{activeAssignments.filter(x => x.status !== 'submitted').length}</span></button>}
      <button className={tab === 'report' ? 'active' : ''} onClick={() => setTab('report')}><BarChart3 size={18}/>Báo cáo tiến độ</button>
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
      <div className="training-card"><h2>Lịch sử gần đây</h2><div className="training-list">{data?.sessions?.map(item => <article key={item.id}><div><strong>{item.employee_name}</strong><small>{formatDate(item.training_date)} · {String(item.start_time).slice(0,5)}–{String(item.end_time).slice(0,5)} · {item.trainer_name}</small></div><b className={`grade grade-${item.skill_grade.replace('+','plus')}`}>{item.skill_grade}</b><p>{item.topic || 'Buổi đào tạo'}</p><p className="muted">Tinh thần: {item.learning_attitude}{item.improvements ? ` · Cần cải thiện: ${item.improvements}` : ''}</p>{permissions.training_session_update && (data?.is_admin || item.trainer_username?.toLowerCase() === user?.employee_username?.toLowerCase()) && <button type="button" className="text-button" onClick={() => { setEditingSessionId(item.id); setSession({ employee_username:item.employee_username, training_date:String(item.training_date).slice(0,10), start_time:String(item.start_time).slice(0,5), end_time:String(item.end_time).slice(0,5), topic:item.topic, learning_attitude:item.learning_attitude, skill_grade:item.skill_grade, strengths:item.strengths, improvements:item.improvements, notes:item.notes }); window.scrollTo({ top:0, behavior:'smooth' }) }}>Sửa nhật ký</button>}</article>)}</div></div>
    </section>}

    {tab === 'evaluate' && <section className="training-card"><h2>Phiếu đánh giá được phân công</h2>{!activeAssignments.length && <div className="training-empty">Hiện chưa có đợt đánh giá đang mở.</div>}{activeAssignments.map(item => { const draft = { ...emptyEvaluation, ...item, ...(evaluationDrafts[item.id] || {}) }; return <article className="evaluation-form" key={item.id}><h3>{item.employee_name} <small>· {item.cycle_name}</small></h3><div className="score-grid">{[['craft_score','Kỹ năng tay nghề'],['communication_score','Giao tiếp'],['attitude_score','Thái độ'],['discipline_score','Kỷ luật'],['appearance_score','Trang phục/ngoại hình'],['hygiene_score','Vệ sinh cá nhân'],['attendance_score','Chuyên cần']].map(([key,label]) => <label key={key}>{label}<select value={draft[key]} onChange={e => setEvaluationDrafts(current => ({ ...current, [item.id]: { ...(current[item.id] || {}), [key]: Number(e.target.value) } }))}>{[1,2,3,4,5].map(n => <option key={n} value={n}>{n}/5</option>)}</select></label>)}</div>{[['strengths','Điểm mạnh'],['improvements','Điểm cần cải thiện'],['comments','Nhận xét']].map(([key,label]) => <label key={key}>{label}<textarea value={draft[key] || ''} onChange={e => setEvaluationDrafts(current => ({ ...current, [item.id]: { ...(current[item.id] || {}), [key]: e.target.value } }))}/></label>)}<div className="button-row"><button type="button" className="secondary-button" onClick={() => saveEvaluation(item, false)}>Lưu nháp</button><button type="button" className="primary-button" onClick={() => saveEvaluation(item, true)}>Gửi đánh giá</button></div></article>})}</section>}

    {tab === 'report' && <section><div className="training-report-filter"><select value={reportEmployee} onChange={e => setReportEmployee(e.target.value)}>{data?.employees?.map(x => <option key={x.username} value={x.username}>{x.full_name}</option>)}</select><button className="primary-button" onClick={openReport}>Xem báo cáo</button></div>{report && <div className="training-grid"><div className="training-card"><h2>Tiến độ kỹ năng</h2><ProgressChart points={report.progress}/></div><div className="training-card"><h2>Năng lực kỳ gần nhất</h2><Radar values={report.latest_radar}/>{report.latest_radar && <p className="center muted">{report.latest_radar.cycle_name}</p>}</div><div className="training-card wide-card"><h2>Timeline đào tạo</h2><div className="timeline">{[...report.progress].reverse().map(item => <article key={item.id}><time>{formatDate(item.training_date)}</time><div><strong>{item.topic || 'Buổi đào tạo'} · {item.skill_grade}</strong><p>{item.strengths || item.notes || 'Không có ghi chú.'}</p>{item.improvements && <p className="muted">Cần cải thiện: {item.improvements}</p>}</div></article>)}</div></div></div>}</section>}

    {tab === 'admin' && <section className="training-grid"><div className="training-card"><h2>Phân công phạm vi</h2><label>Trainer/Supervisor<select value={scopeTrainer} onChange={e => { const value=e.target.value; setScopeTrainer(value); setScopeEmployees((data?.scopes || []).filter(x => x.trainer_username === value).map(x => x.employee_username)) }}><option value="">Chọn tài khoản</option>{data?.people?.map(x => <option key={x.username} value={x.username}>{x.full_name} · {x.role}</option>)}</select></label><div className="check-list">{data?.people?.map(x => <label key={x.username}><input type="checkbox" checked={scopeEmployees.includes(x.username)} onChange={() => setScopeEmployees(current => current.includes(x.username) ? current.filter(v => v !== x.username) : [...current,x.username])}/>{x.full_name}</label>)}</div><button className="primary-button" disabled={!scopeTrainer || busy} onClick={saveScope}>Lưu phạm vi</button></div>
      <form className="training-card" onSubmit={createCycle}><h2>Tạo đợt đánh giá tổng hợp</h2><label>Tên đợt<input required value={cycle.name} onChange={e => setCycle({ ...cycle, name:e.target.value })} placeholder="Ví dụ: Đánh giá quý III/2026"/></label><div className="training-form-grid"><label>Từ ngày<VeraDateInput required value={cycle.start_date} onChange={e => setCycle({ ...cycle, start_date:e.target.value })}/></label><label>Đến ngày<VeraDateInput required min={cycle.start_date} value={cycle.end_date} onChange={e => setCycle({ ...cycle, end_date:e.target.value })}/></label></div><label>Hướng dẫn<textarea value={cycle.instructions} onChange={e => setCycle({ ...cycle, instructions:e.target.value })}/></label><h3>Nhân viên được đánh giá</h3><div className="check-list compact">{data?.people?.map(x => <label key={x.username}><input type="checkbox" checked={cycle.employee_usernames.includes(x.username)} onChange={() => toggleList('employee_usernames',x.username)}/>{x.full_name}</label>)}</div><h3>Người đánh giá</h3><div className="check-list compact">{data?.people?.map(x => <label key={x.username}><input type="checkbox" checked={cycle.evaluator_usernames.includes(x.username)} onChange={() => toggleList('evaluator_usernames',x.username)}/>{x.full_name}</label>)}</div><button className="primary-button" disabled={busy}>Tạo đợt nháp</button></form>
      <div className="training-card wide-card"><h2>Các đợt đánh giá</h2><div className="cycle-list">{data?.cycles?.map(item => <article key={item.id}><div><strong>{item.name}</strong><small>{formatDate(item.start_date)} – {formatDate(item.end_date)} · {item.submitted_count}/{item.assignment_count} phiếu đã gửi</small></div><span className={`status ${item.status}`}>{item.status}</span>{item.status === 'draft' && <button onClick={async()=>{await veraApi.changeEvaluationCycle(item.id,'activate'); await load()}}>Kích hoạt</button>}{item.status === 'active' && <button onClick={async()=>{await veraApi.changeEvaluationCycle(item.id,'close'); await load()}}>Đóng đợt</button>}</article>)}</div></div></section>}
    {busy && !data && <div className="training-empty">Đang tải dữ liệu…</div>}
  </main>
}
