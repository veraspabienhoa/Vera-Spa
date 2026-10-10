import { alertDialog } from '../lib/systemDialogs'
import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, CalendarDays, Download, Pause, Play, RefreshCw, ShieldCheck } from 'lucide-react'
import { veraApi } from '../lib/api'
import VeraDateInput from '../components/VeraDateInput'
import EmployeeProfileModal from '../components/EmployeeProfileModal'
import { onVeraAuthStateChange } from '../lib/supabase'

const FILTER_OPTIONS = ['Hôm qua', 'Hôm nay', 'Tuần trước', 'Tháng trước', 'Tùy chỉnh']
const EVIDENCE_REASONS = {
  invalid_timestamp: 'Thời gian quét không hợp lệ',
  future_or_invalid_event_timestamp: 'Lượt quét có thời gian tương lai hoặc không hợp lệ',
  conflicting_duplicate: 'Lượt quét trùng nhưng khác dữ liệu',
  unmapped_reference: 'Danh tính chưa xác nhận',
  unverified_status_type: 'Trạng thái lượt quét chưa xác minh',
  device_address_changed: 'Lượt quét khác thiết bị',
  overlapping_shifts: 'Khung ca chồng lấn',
  no_vera_shift: 'Lượt quét ngoài khung ca VERA',
  reviewed_checkout_invalid: 'Đối chiếu giờ ra cần kiểm tra lại',
  reviewed_identity_invalid: 'Đối chiếu danh tính cần kiểm tra lại',
  reviewed_test_scans_invalid: 'Đối chiếu lượt quét thử cần kiểm tra lại',
}

function EvidenceStatus({ report, loading, failed, detailsOpen, onDetailsToggle }) {
  if (loading) return <div className="auto-check-evidence" role="status">Đang kiểm tra bằng chứng chấm công…</div>
  if (failed || !report) return <div className="auto-check-evidence auto-check-paused" role="status">Chưa đọc được tình trạng bằng chứng chấm công. Bấm Làm mới để thử lại.</div>
  const evidence = report.evidence
  const days = evidence?.days || []
  const warning = !report.cache_fresh || (report.source === 'facegate' && (!evidence || !days.length
    || evidence.global_issue_count > 0 || evidence.scoped_issue_count > 0 || days.some(day => !day.archive_complete || !day.archive_fresh)))
  return <div className="auto-check-evidence" role="status" aria-label="Tình trạng bằng chứng chấm công">
    <b className={warning ? 'auto-check-paused' : ''}>Nguồn {report.source === 'facegate' ? 'FaceGate' : 'TimeSoft'}: {warning ? 'Cần kiểm tra bằng chứng' : 'Chưa thấy lỗi nguồn trong phạm vi kiểm tra'}</b>
    <span>Cache nguồn: {report.cache_fresh ? 'Còn mới' : 'Cũ hoặc chưa có'} · Đồng bộ: {formatVeraDateTime(report.last_sync_at)}</span>
    {evidence && <>
      <span>Phạm vi gần nhất: {formatVeraDate(report.start)} – {formatVeraDate(report.end)} (giờ Việt Nam), độc lập bộ lọc lịch sử.</span>
      <span>Chặn toàn cục: {evidence.global_issue_count || 0} · Chặn theo nhân viên/ngày: {evidence.scoped_issue_count || 0} · Thông tin: {evidence.informational_issue_count || 0}</span>
      <details open={detailsOpen}><summary tabIndex={0} onClick={event => { event.preventDefault(); onDetailsToggle(!detailsOpen) }}>Chi tiết nguồn đã lưu</summary>
        {days.map(day => <span key={day.date}>{formatVeraDate(day.date)}: {day.archive_complete ? 'Đủ bản lưu' : 'Thiếu bản lưu'}; {day.archive_fresh ? 'còn mới' : 'cũ hoặc chưa có'}; đồng bộ {formatVeraDateTime(day.last_sync_at)}; chặn toàn cục {day.global_issue_count || 0}, theo nhân viên/ngày {day.scoped_issue_count || 0}</span>)}
        {Object.entries(evidence.reason_counts || {}).map(([reason, count]) => <span key={reason}>{EVIDENCE_REASONS[reason] || 'Bằng chứng cần kiểm tra'}: {count}</span>)}
      </details>
    </>}
    {report.source !== 'facegate' && <span>Chẩn đoán phạm vi bằng chứng chỉ áp dụng cho nguồn FaceGate.</span>}
    <span>Chỉ đọc nguồn đã lưu; chưa xác minh kết nối trực tiếp thiết bị. Cấu hình đã bật không đảm bảo đã ghi phạt; từng trường hợp vẫn phải đủ điều kiện.</span>
  </div>
}

const formatDateInput = (value) => {
  const date = new Date(value)
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const addDays = (value, days) => {
  const date = new Date(value)
  date.setDate(date.getDate() + days)
  return date
}

const rangeForFilter = (filter) => {
  const now = new Date()
  if (filter === 'Hôm qua') {
    const yesterday = addDays(now, -1)
    return [formatDateInput(yesterday), formatDateInput(yesterday)]
  }
  if (filter === 'Tuần trước') {
    const thisMonday = addDays(now, -((now.getDay() + 6) % 7))
    const previousMonday = addDays(thisMonday, -7)
    return [formatDateInput(previousMonday), formatDateInput(addDays(previousMonday, 6))]
  }
  if (filter === 'Tháng trước') {
    return [
      formatDateInput(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      formatDateInput(new Date(now.getFullYear(), now.getMonth(), 0)),
    ]
  }
  return [formatDateInput(now), formatDateInput(now)]
}

const displayDate = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}-${month}-${year}` : value || '—'
}

export default function AutoCheckPage({ user }) {
  const [authRevision, setAuthRevision] = useState(0)
  useEffect(() => onVeraAuthStateChange(() => setAuthRevision(value => value + 1)), [])
  // A second Admin and a replacement session must never inherit the previous
  // account's report, open dialog, or in-flight response. Do not retain tokens.
  const scope = JSON.stringify([user?.id, user?.employee_username, user?.role,
    user?.must_change_password, user?.permissions, authRevision])
  return <AutoCheckContent key={scope} user={user}/>
}

function AutoCheckContent({ user }) {
  usePageRefresh(() => load(), () => Boolean(busy || loading))
  const initialRange = rangeForFilter('Hôm nay')
  const [data, setData] = useState(null)
  const [evidence, setEvidence] = useState(null)
  const [evidenceFailed, setEvidenceFailed] = useState(false)
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [statusView, setStatusView] = useState('closed')
  const [detailsOpen, setDetailsOpen] = useState(false)
  const pendingEvidence = useRef({ version: 0, controller: null, active: true, loading: false })
  const pendingLoad = useRef({ version: 0, controller: null, active: true })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [timeFilter, setTimeFilter] = useState('Hôm nay')
  const [startDate, setStartDate] = useState(initialRange[0])
  const [endDate, setEndDate] = useState(initialRange[1])
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'

  const load = useCallback(async () => {
    if (!pendingLoad.current.active) return
    pendingLoad.current.controller?.abort()
    const version = ++pendingLoad.current.version
    const controller = new AbortController()
    pendingLoad.current.controller = controller
    if (!startDate || !endDate || endDate < startDate) {
      setError('Vui lòng chọn khoảng thời gian hợp lệ.')
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const dashboard = await veraApi.autoCheck(startDate, endDate, { signal: controller.signal })
      if (version !== pendingLoad.current.version) return
      setData(dashboard)
    } catch (err) {
      if (version === pendingLoad.current.version) setError(err.message)
    } finally {
      if (version === pendingLoad.current.version) setLoading(false)
    }
  }, [endDate, startDate])

  useEffect(() => {
    const pending = pendingLoad.current
    pending.active = true
    void load()
    return () => { pending.active = false; pending.version += 1; pending.controller?.abort() }
  }, [load])

  useEffect(() => {
    const pending = pendingEvidence.current
    pending.active = true
    return () => { pending.active = false; pending.version += 1; pending.controller?.abort() }
  }, [])

  const loadEvidence = async () => {
    const pending = pendingEvidence.current
    if (!isAdmin || !pending.active || pending.loading) return
    pending.loading = true
    const version = ++pending.version
    pending.controller = new AbortController()
    setEvidenceLoading(true); setEvidence(null); setEvidenceFailed(false)
    try {
      const report = await veraApi.autoCheckEvidence({ signal: pending.controller.signal })
      if (pending.active && version === pending.version) setEvidence(report)
    } catch {
      if (pending.active && version === pending.version) setEvidenceFailed(true)
    } finally {
      if (pending.active && version === pending.version) {
        pending.loading = false
        setEvidenceLoading(false)
      }
    }
  }

  const openStatus = () => {
    if (!isAdmin) return
    setStatusView('open')
    if (statusView === 'closed' || (!evidence && !evidenceLoading)) void loadEvidence()
  }

  const closeStatus = () => {
    const pending = pendingEvidence.current
    pending.version += 1; pending.controller?.abort(); pending.loading = false
    setEvidenceLoading(false); setDetailsOpen(false); setStatusView('closed')
  }

  const selectTimeFilter = (filter) => {
    setTimeFilter(filter)
    if (filter === 'Tùy chỉnh') return
    const [start, end] = rangeForFilter(filter)
    setStartDate(start)
    setEndDate(end)
  }

  const exportExcel = async () => {
    if (!startDate || !endDate || endDate < startDate) {
      setError('Vui lòng chọn khoảng thời gian hợp lệ trước khi xuất Excel.')
      return
    }
    setExporting(true); setError('')
    try { await veraApi.exportAutoCheckExcel(startDate, endDate) }
    catch (err) { setError(err.message) }
    finally { setExporting(false) }
  }

  const update = async (body) => {
    setBusy(true); setError('')
    try { await veraApi.updateAutoCheck(body); await load() } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const run = async () => {
    setBusy(true); setError('')
    try { const result = await veraApi.runAutoCheck(); await load(); (await alertDialog(result.message)) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const cfg = data?.config || {}
  const connected = Boolean(data)
  const canControl = isAdmin || user?.permissions?.auto_penalty_control
  const canRun = isAdmin || user?.permissions?.auto_penalty_run
  const latestRun = data?.runs?.[0]
  const latestRunFailed = String(latestRun?.status || '').toLowerCase() === 'error'
  const latestRunError = String(latestRun?.error || '').trim()

  return <section data-ui-key="u-b5d6be8f0956" className="page-stack auto-check-page">
    <style>{`.auto-check-evidence{margin:0 0 18px;padding:12px;border:1px solid #b7c6bd;border-radius:10px;font-size:13px;line-height:1.6;overflow-wrap:anywhere}.auto-check-evidence>span,.auto-check-evidence details>span{display:block}.auto-check-evidence summary{cursor:pointer;font-weight:600}.auto-check-evidence summary:focus-visible{outline:2px solid #1f513f;outline-offset:3px}.auto-check-evidence details{margin-top:4px}.auto-check-evidence>span:last-child{color:#52665e;margin-top:6px}.auto-check-card>small{display:block;margin-top:8px;color:#52665e}`}</style>
    <style>{`.auto-check-status-modal{width:min(860px,100%);display:flex;flex-direction:column;overflow:hidden}.auto-check-status-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:16px 20px;border-bottom:1px solid #b7c6bd;flex:0 0 auto}.auto-check-status-head h2{margin:0;font-size:20px;overflow-wrap:anywhere}.auto-check-status-actions{display:flex;gap:8px;flex-wrap:wrap}.auto-check-status-actions button{min-height:44px}.auto-check-status-body{padding:16px 20px;min-height:0;overflow-y:auto;overscroll-behavior:contain}.auto-check-status-note{font-size:13px;line-height:1.6;color:#52665e}.auto-check-status-body .auto-check-evidence{margin-top:12px}.auto-check-status-body .auto-check-paused{color:#a45d1a}.auto-check-status-body button[aria-disabled=true]{opacity:.65;cursor:wait}@media(max-width:640px){.auto-check-status-head{padding:max(12px,env(safe-area-inset-top)) 12px 12px}.auto-check-status-actions{width:100%}.auto-check-status-actions button{flex:1}.auto-check-status-body{padding:12px 12px max(16px,env(safe-area-inset-bottom));flex:1}}`}</style>
    <style>{`.auto-check-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.auto-check-card{background:#fff;border:1px solid #dfe8e2;border-radius:22px;padding:20px}.auto-check-card strong{display:block;font-size:27px;color:#14382c;margin-top:8px}.auto-check-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.auto-check-filter{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.auto-check-filter button.active{background:#1f513f;color:#fff;border-color:#1f513f}.auto-check-custom{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-top:14px}.auto-check-custom label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:#627169}.auto-check-custom input{min-width:165px}.auto-check-history-head{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:12px}.auto-check-history-head h2{margin:0}.auto-check-period{font-size:13px;color:#627169}.auto-check-table{width:100%;border-collapse:collapse}.auto-check-table th,.auto-check-table td{padding:12px 9px;text-align:left;border-bottom:1px solid #e7ece9;font-size:14px}.auto-check-table th{color:#627169}.auto-check-ok{color:#17734b}.auto-check-paused{color:#a45d1a}.tour-cache-control-card{border:2px solid #dfe8e2}.tour-cache-control-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.tour-cache-control-head h2{margin:0 0 5px}.tour-cache-control-status{font-weight:900;font-size:18px}.tour-cache-control-note{margin:12px 0;color:#52665e;line-height:1.55}.tour-cache-meta{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:#66766f;margin-top:12px}.tour-cache-message{margin-top:12px}@media(max-width:720px){.auto-check-grid{grid-template-columns:1fr}.auto-check-table th:nth-child(4),.auto-check-table td:nth-child(4){display:none}.tour-cache-control-head,.auto-check-history-head{align-items:stretch;flex-direction:column}.auto-check-history-head button{width:100%}.auto-check-custom label{flex:1}.auto-check-custom input{min-width:0;width:100%}}`}</style>
    <div data-ui-key="u-ed611a1d46fd" className="page-heading"><div><span className="eyebrow"><ShieldCheck size={18}/> VẬN HÀNH</span><h1>Auto Check</h1><p>Kiểm tra tự động từ nguồn chấm công đã chọn và Bảng tua; dữ liệu được ghi trực tiếp vào PostgreSQL.</p></div><button data-ui-key="u-172eb5d5fb57" className="secondary-button" onClick={load} disabled={loading}><RefreshCw size={17} className={loading ? 'spin' : ''}/> {loading ? 'Đang tải…' : 'Làm mới'}</button></div>
    <StableFeedback>{error && <div className="error-box">{error}</div>}
    {latestRunFailed && <div className="error-box">Lần chạy Auto Check gần nhất gặp lỗi{latestRunError ? `: ${latestRunError}` : '.'}</div>}</StableFeedback>
    <div className="auto-check-grid">
      <div data-ui-key="u-e9f00f13cab7" className="auto-check-card"><span>Cấu hình Auto Check</span><strong className={connected && cfg.status !== 'PAUSED' ? '' : 'auto-check-paused'}>{!connected ? 'Chưa kết nối' : cfg.status === 'PAUSED' ? 'Tạm dừng' : 'Đã bật'}</strong><small>Trạng thái cấu hình không xác nhận kết quả ghi phạt.</small></div>
      <div data-ui-key="u-099084b7b354" className="auto-check-card"><span>Ngưỡng ghi nhận</span><strong>{connected ? `${cfg.threshold_minutes || 5} phút` : '—'}</strong></div>
      <div data-ui-key="u-cf373f87b595" className="auto-check-card"><span>Lịch kiểm tra chuẩn</span><strong>{connected ? (cfg.schedule_hours || [15,20,21]).map(x => `${x}:00`).join(' · ') : '—'}</strong></div>
    </div>
    <div data-ui-key="u-f47c36a57f3d" className="panel auto-check-card"><h2>Điều khiển</h2>
    <UiToolbar data-ui-key="u-850c3cca4f2d" className="auto-check-actions">
      {isAdmin && <button type="button" className="secondary-button" onClick={openStatus} aria-haspopup="dialog" aria-expanded={statusView === 'open'}>{statusView === 'hidden' ? 'Mở lại trạng thái' : 'Mở trạng thái'}</button>}
      {canControl && <button data-ui-key="u-3c4394c8b3a8" className="secondary-button" disabled={busy || !connected} onClick={() => update({status: cfg.status === 'PAUSED' ? 'RUNNING' : 'PAUSED'})}>{cfg.status === 'PAUSED' ? <Play size={17}/> : <Pause size={17}/>} {cfg.status === 'PAUSED' ? 'Mở Auto Check' : 'Tạm dừng'}</button>}
      {canRun && <button data-ui-key="u-cfca77851d42" data-ui-label-default="Chạy Auto Check" className="primary-button" disabled={busy || !connected || cfg.status === 'PAUSED'} onClick={run}><Activity size={17}/><UiCustomText uiKey="u-cfca77851d42"> Chạy Auto Check</UiCustomText></button>}
    </UiToolbar></div>
    {isAdmin && statusView === 'open' && <EmployeeProfileModal className="auto-check-status-modal" labelledBy="auto-check-status-title" onClose={closeStatus}>
      <header className="auto-check-status-head"><h2 id="auto-check-status-title">Trạng thái Auto Check</h2><div className="auto-check-status-actions">
        <button type="button" className="secondary-button" onClick={() => setStatusView('hidden')}>Tạm ẩn</button>
        <button type="button" className="secondary-button" onClick={closeStatus}>Close</button>
      </div></header>
      <div className="auto-check-status-body">
        <p className="auto-check-status-note">Tạm ẩn giữ phần đang xem để mở lại. Close đóng và thu gọn chi tiết. Các nút này chỉ điều khiển cửa sổ trạng thái.</p>
        <button type="button" className="secondary-button" onClick={loadEvidence} aria-disabled={evidenceLoading}><RefreshCw size={17} className={evidenceLoading ? 'spin' : ''}/>{evidenceLoading ? 'Đang tải trạng thái…' : 'Làm mới trạng thái'}</button>
        {evidence?.checked_at && <p className="auto-check-status-note">Đọc lúc: {formatVeraDateTime(evidence.checked_at)}</p>}
        <EvidenceStatus report={evidence} loading={evidenceLoading} failed={evidenceFailed} detailsOpen={detailsOpen} onDetailsToggle={setDetailsOpen}/>
      </div>
    </EmployeeProfileModal>}

    <div data-ui-key="u-dc7341e60db5" className="panel auto-check-card">
      <span className="eyebrow"><CalendarDays size={17}/> LỌC LỊCH SỬ</span>
      <div className="auto-check-filter">
        {FILTER_OPTIONS.map((filter) => <button data-ui-key="u-e0f5bf00a206" key={filter} type="button" className={`secondary-button${timeFilter === filter ? ' active' : ''}`} onClick={() => selectTimeFilter(filter)}>{filter}</button>)}
      </div>
      {timeFilter === 'Tùy chỉnh' && <div className="auto-check-custom">
        <label>Từ ngày<VeraDateInput aria-label="Từ ngày" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label>Đến ngày<VeraDateInput aria-label="Đến ngày" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
      </div>}
    </div>



    <div data-ui-key="u-684cd83f1fef" className="panel auto-check-card"><div className="auto-check-history-head"><div><h2>Lịch sử ghi nhận</h2><div className="auto-check-period">{displayDate(startDate)} – {displayDate(endDate)} · {(data?.events || []).length} dòng</div></div><button data-ui-key="u-62af98cd9421" className="secondary-button" onClick={exportExcel} disabled={exporting || loading}><Download size={17}/> {exporting ? 'Đang xuất…' : 'Xuất excel'}</button></div><div className="table-scroll"><table data-ui-key="u-a306913b678e" className="auto-check-table"><thead><tr><th data-ui-key="u-8d1dc7bd8da5" data-ui-label-default="Ngày"><UiCustomText uiKey="u-8d1dc7bd8da5">Ngày</UiCustomText></th><th data-ui-key="u-6165aa955561" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-6165aa955561">Nhân viên</UiCustomText></th><th data-ui-key="u-65ff9806efb0" data-ui-label-default="Lý do"><UiCustomText uiKey="u-65ff9806efb0">Lý do</UiCustomText></th><th data-ui-key="u-d4954b56dcd7" data-ui-label-default="Nguồn"><UiCustomText uiKey="u-d4954b56dcd7">Nguồn</UiCustomText></th><th data-ui-key="u-a94a1d8f8c9a" data-ui-label-default="Phút"><UiCustomText uiKey="u-a94a1d8f8c9a">Phút</UiCustomText></th></tr></thead><tbody>{(data?.events || []).map((row, i) => <tr key={`${formatVeraDateTime(row.created_at)}-${i}`}><td>{displayDate(row.work_date)}</td><td><b>{row.employee_name}</b></td><td>{row.reason}</td><td>{row.source}</td><td>{row.minutes}</td></tr>)}{!data?.events?.length && <tr><td colSpan="5">Không có vi phạm Auto Check trong khoảng thời gian đã chọn.</td></tr>}</tbody></table></div></div>
  </section>
}
