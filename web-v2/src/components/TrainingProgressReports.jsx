import { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import EmployeeProfileModal from './EmployeeProfileModal'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import VeraDateInput from './VeraDateInput'
import TrainingDailyReport from './TrainingDailyReport'
import TrainingReportFiles from './TrainingReportFiles'
import { TrainingCriteriaChart, TrainingProgressChart, TrainingRadar } from './TrainingReportCharts'
import { veraApi } from '../lib/api'
import usePageRefresh from '../lib/usePageRefresh'
import { vietnamToday } from '../lib/useVietnamToday'
import { searchTextMatches } from '../lib/searchText'
import { formatVeraDate } from '../lib/veraDate'
import { evaluationCriteria, readCompleteTrainingReport, trainingDateRange, trainingIdentityKey, trainingRangeLabel, validTrainingScore } from '../lib/trainingReport'

function TrainingEmployeeReport({ scope, onClose, onDenied }) {
  const [state, setState] = useState(null), [retry, setRetry] = useState(0), [prepareFiles, setPrepareFiles] = useState(false), [sharing, setSharing] = useState(false)
  useEffect(() => {
    const controller = new AbortController(); let active = true
    readCompleteTrainingReport(veraApi.trainingReport, scope.employee, scope.filters, controller.signal).then(report => {
      if (active) setState({ report })
    }).catch(error => { if (active && !controller.signal.aborted) setState({ error }) })
    return () => { active = false; controller.abort() }
  }, [scope, retry])
  const report = state?.report
  const denied = error => { setPrepareFiles(false); setState({ error }); onDenied(error) }
  return <EmployeeProfileModal className="training-report-modal" labelledBy="training-report-title" onClose={onClose} busy={sharing}>
    <div className="training-page training-report-body">
      <header className="training-report-heading"><div><p className="eyebrow">VERA SPA · BÁO CÁO TIẾN ĐỘ</p><h2 id="training-report-title">{scope.name}</h2><p>{trainingRangeLabel(scope.filters)}</p></div><button type="button" className="secondary-button" aria-label="Đóng báo cáo đào tạo" disabled={sharing} onClick={onClose}><X size={20}/></button></header>
      {!state && <p role="status" className="training-empty">Đang tải toàn bộ báo cáo…</p>}
      {state?.error && <div><p role="alert" className="error-box">{state.error.message}</p>{![401,403].includes(state.error.status) && <button type="button" className="secondary-button" onClick={() => { setState(null); setRetry(n => n+1) }}>Thử tải lại báo cáo</button>}</div>}
      {report && <>
        <div className="training-report-export-control"><button type="button" className="secondary-button" onClick={() => setPrepareFiles(true)} disabled={prepareFiles}>Xem / tải / chia sẻ PNG và PDF</button></div>
        {prepareFiles && <TrainingReportFiles scope={scope} onDenied={denied} onSharingChange={setSharing}/>}
        <TrainingDailyReport report={report}/>
        <div className="training-grid"><section className="training-card"><h2>Tiến độ kỹ năng</h2><TrainingProgressChart points={report.progress}/></section><section className="training-card"><h2>Năng lực kỳ gần nhất</h2><TrainingRadar values={report.latest_radar}/></section></div>
        <section className="training-card"><h2>Biểu đồ đánh giá</h2><TrainingCriteriaChart history={report.history}/></section>
        <section className="training-card"><h2>Lịch sử Đào tạo & Đánh giá <small>({report.history.length})</small></h2><div className="timeline">
          {report.history.map(item => <article className={`training-history-item ${item.type}`} key={`${item.type}-${item.id}`}><time>{formatVeraDate(item.date)}</time><div><span className={`history-kind ${item.type}`}>{item.type === 'daily' ? 'Đào tạo hằng ngày' : 'Đánh giá tổng hợp'}</span><strong>{item.title}</strong><p>Người thực hiện: {item.evaluator_name || '—'} · Xếp loại: {item.rating_label || 'Chưa có'}</p>
            {item.type === 'daily' ? <p>Kỹ năng: {item.detail?.skill_grade || 'Chưa có'} · Tinh thần: {item.detail?.learning_attitude || 'Chưa có'}</p> : <p>{evaluationCriteria.map(([key,label]) => `${label}: ${validTrainingScore(item.detail?.[key]) ? `${item.detail[key]}/5` : 'Chưa có điểm'}`).join(' · ')}</p>}
            <p>Điểm mạnh: {item.detail?.strengths || '—'}</p><p>Cần cải thiện: {item.detail?.improvements || '—'}</p><p>Nhận xét: {item.detail?.notes || item.detail?.comments || '—'}</p>
          </div></article>)}
          {!report.history.length && <p className="training-empty">Chưa có dữ liệu trong khoảng đã chọn.</p>}
        </div></section>
      </>}
    </div>
  </EmployeeProfileModal>
}

export default function TrainingProgressReports({ user }) {
  const [mode, setMode] = useState('all'), [day, setDay] = useState(vietnamToday), [month, setMonth] = useState(() => vietnamToday().slice(0,7))
  const [start, setStart] = useState(vietnamToday), [end, setEnd] = useState(vietnamToday), [draftValid, setDraftValid] = useState({ day: true, start: true, end: true })
  const [search, setSearch] = useState(''), [employee, setEmployee] = useState(''), [selected, setSelected] = useState(null)
  const [result, setResult] = useState(null), [reload, setReload] = useState(0)
  const identity = trainingIdentityKey(user)
  const filters = useMemo(() => trainingDateRange({mode,day,month,start,end}), [mode,day,month,start,end])
  const valid = Boolean(filters && (mode !== 'day' || draftValid.day) && (mode !== 'custom' || (draftValid.start && draftValid.end)))
  const queryKey = JSON.stringify([identity, filters, valid, reload])
  usePageRefresh(() => { setSelected(null); setReload(n => n+1) })
  useEffect(() => {
    if (!valid) return
    const controller = new AbortController(); let active = true
    veraApi.trainingReportEmployees(filters, { signal: controller.signal }).then(data => {
      if (active) setResult({ queryKey, employees: data.employees || [] })
    }).catch(error => { if (active && !controller.signal.aborted) setResult({ queryKey, error }) })
    return () => { active = false; controller.abort() }
  }, [queryKey, filters, valid])
  const active = valid && result?.queryKey === queryKey ? result : null
  const employees = active?.employees || []
  const rows = employees.filter(item => employee ? item.username === employee : searchTextMatches([item.username, item.full_name], search))
  const scope = selected?.queryKey === queryKey && employees.some(item => item.username === selected.employee) ? selected : null
  const updateMode = value => { setMode(value); setDraftValid({ day:true, start:true, end:true }); setEmployee(''); setSearch(''); setSelected(null) }
  const validity = key => value => setDraftValid(old => old[key] === value ? old : { ...old, [key]:value })
  const changeDate = (setter, key) => event => { setter(event.target.value); setDraftValid(old => ({ ...old, [key]: Boolean(event.target.value) })); setEmployee(''); setSearch(''); setSelected(null) }
  return <section className="training-card training-employee-roster" aria-label="Báo cáo tiến độ">
    <h2>Nhân viên đã được đào tạo / đánh giá</h2>
    <div className="training-progress-filters">
      <LiveTourSearchSelect label="Nhân viên" value={employee} options={employees.map(item => ({ value:item.username, label:item.full_name || item.username, detail:item.username }))} placeholder="Nhập tên hoặc chọn nhân viên…" emptyLabel="Tất cả nhân viên" disabled={!active || Boolean(active.error)} searchValue={search} onSearch={value => { setSearch(value); setEmployee('') }} onChange={value => { setEmployee(value); setSearch(employees.find(item => item.username === value)?.full_name || value) }}/>
      <label>Thời gian đào tạo<select aria-label="Thời gian đào tạo" value={mode} onChange={event => updateMode(event.target.value)}><option value="all">Tất cả thời gian</option><option value="day">Ngày đào tạo</option><option value="month">Tháng đào tạo</option><option value="custom">Khoảng ngày tùy chọn</option></select></label>
      {mode === 'day' && <label>Ngày đào tạo<VeraDateInput aria-label="Ngày đào tạo" value={day} onChange={changeDate(setDay,'day')} onDraftValidity={validity('day')}/></label>}
      {mode === 'month' && <label>Tháng đào tạo<input type="month" aria-label="Tháng đào tạo" value={month} onChange={event => { setMonth(event.target.value); setEmployee(''); setSearch(''); setSelected(null) }}/></label>}
      {mode === 'custom' && <><label>Từ ngày<VeraDateInput aria-label="Đào tạo từ ngày" value={start} onChange={changeDate(setStart,'start')} onDraftValidity={validity('start')}/></label><label>Đến ngày<VeraDateInput aria-label="Đào tạo đến ngày" min={start} value={end} onChange={changeDate(setEnd,'end')} onDraftValidity={validity('end')}/></label></>}
    </div>
    {!valid && <p role="status">Nhập đầy đủ ngày hợp lệ; ngày kết thúc không được trước ngày bắt đầu.</p>}
    {valid && !active && <p role="status">Đang tải nhân viên theo khoảng ngày…</p>}
    {active?.error && <div><p role="alert" className="error-box">{active.error.message}</p><button type="button" className="secondary-button" onClick={() => setReload(n => n+1)}>Thử tải lại danh sách</button></div>}
    {active?.employees && <><p className="muted">{trainingRangeLabel(filters)} · {rows.length} nhân viên. Chọn tên để xem báo cáo.</p><p className="muted">Nhật ký theo ngày đào tạo; đánh giá theo ngày kết thúc kỳ.</p><table><thead><tr><th>Nhân viên</th><th>Bộ phận</th></tr></thead><tbody>{rows.map(item => <tr key={item.username}><td><button type="button" className="text-button" aria-haspopup="dialog" onClick={() => setSelected({ queryKey, employee:item.username, name:item.full_name || item.username, filters })}>{item.full_name || item.username}</button></td><td>{item.department || item.role}</td></tr>)}</tbody></table>{!rows.length && <p>Không có nhân viên đã đào tạo / đánh giá phù hợp bộ lọc.</p>}</>}
    {scope && <TrainingEmployeeReport key={`${scope.queryKey}:${scope.employee}`} scope={scope} onClose={() => setSelected(null)} onDenied={() => { setSelected(null); setReload(n => n+1) }}/>}
  </section>
}
