import { CalendarDays, CheckCircle2, Clock3, RefreshCw, UserRoundCheck, UsersRound } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { demoMode, isApiConfigured, veraApi } from '../lib/api'

const formatDateInput = (date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = () => formatDateInput(new Date())

const demoRecords = [
  { record_uid: 'demo-1', employee_name: 'Nhân viên A', leave_reason: 'Nghỉ CÓ phép', penalty: 0 },
  { record_uid: 'demo-2', employee_name: 'Nhân viên B', leave_reason: 'Nghỉ KHÔNG phép', penalty: 500000 },
]

export default function LeaveRegistrationPage() {
  const [date, setDate] = useState(today())
  const [summary, setSummary] = useState({ working: 0, leave: 0, paid: 0, unpaid: 0 })
  const [records, setRecords] = useState([])
  const [reasons, setReasons] = useState([])
  const [form, setForm] = useState({ employee_name: '', leave_reason: '', detail: '' })
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      if (!isApiConfigured) {
        if (!demoMode) return
        setSummary({ working: 34, leave: 2, paid: 1, unpaid: 1 })
        setRecords(demoRecords)
        setReasons(['Nghỉ CÓ phép', 'Nghỉ KHÔNG phép', 'Đi trễ CÓ phép', 'Đi trễ KHÔNG phép'])
        return
      }
      const [summaryData, recordData, reasonData] = await Promise.all([
        veraApi.leaveSummary(date),
        veraApi.leaveRecords(date),
        veraApi.leaveReasons(),
      ])
      setSummary(summaryData)
      setRecords(recordData.records || [])
      setReasons(reasonData.reasons || [])
    } catch (err) {
      setError(err.message || 'Không tải được dữ liệu.')
    } finally {
      setBusy(false)
    }
  }, [date])

  useEffect(() => { load() }, [load])

  const totalPenalty = useMemo(() => records.reduce((sum, item) => sum + Number(item.penalty || 0), 0), [records])

  const shiftDate = (offset) => {
    const current = new Date(`${date}T00:00:00`)
    current.setDate(current.getDate() + offset)
    setDate(formatDateInput(current))
  }

  const submit = async (event) => {
    event.preventDefault()
    setMessage('')
    setError('')
    if (!isApiConfigured) {
      setError('Chưa cấu hình Python API. Web V2 không ghi trực tiếp vào leave_records để tránh bỏ qua nghiệp vụ tính phép/phạt.')
      return
    }
    setSaving(true)
    try {
      await veraApi.createLeave({ ...form, leave_date: date })
      setForm({ employee_name: '', leave_reason: '', detail: '' })
      setMessage('Đã ghi đăng ký nghỉ.')
      await load()
    } catch (err) {
      setError(err.message || 'Không ghi được đăng ký nghỉ.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="page-heading-row">
        <div>
          <span className="eyebrow"><CalendarDays size={15} /> Web V2 Pilot</span>
          <h1 className="page-title">Đăng ký nghỉ</h1>
          <p className="page-subtitle">Giao diện React mới. Dữ liệu nghiệp vụ vẫn giữ PostgreSQL/Supabase làm trung tâm.</p>
        </div>
        <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={17} className={busy ? 'spin' : ''} /> Làm mới</button>
      </div>

      {!isApiConfigured && !demoMode && (
        <div className="warning-box"><strong>Frontend đã sẵn sàng.</strong> Cần cấu hình VITE_VERA_API_BASE_URL để đọc/ghi dữ liệu thật. Hệ thống Streamlit hiện tại không bị thay đổi.</div>
      )}

      <div className="date-toolbar">
        <button onClick={() => shiftDate(-1)}>Hôm qua</button>
        <button onClick={() => setDate(today())}>Hôm nay</button>
        <button onClick={() => shiftDate(1)}>Ngày mai</button>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>

      <section className="metric-grid">
        <Metric icon={UserRoundCheck} label="Đang làm việc" value={summary.working ?? 0} />
        <Metric icon={UsersRound} label="Tổng nghỉ" value={summary.leave ?? records.length} />
        <Metric icon={CheckCircle2} label="Có phép" value={summary.paid ?? 0} />
        <Metric icon={Clock3} label="Không phép" value={summary.unpaid ?? 0} />
      </section>

      <div className="content-grid">
        <section className="panel">
          <div className="panel-title-row">
            <div><h2>Đăng ký mới</h2><p>Ghi qua Python API để giữ nguyên toàn bộ business rules hiện tại.</p></div>
          </div>
          <form className="leave-form" onSubmit={submit}>
            <label>Tên nhân viên</label>
            <input value={form.employee_name} onChange={(e) => setForm({ ...form, employee_name: e.target.value })} placeholder="Nhập tên nhân viên" required />

            <label>Lý do nghỉ</label>
            <select value={form.leave_reason} onChange={(e) => setForm({ ...form, leave_reason: e.target.value })} required>
              <option value="">-- Chọn lý do nghỉ --</option>
              {reasons.map((reason) => <option key={reason} value={reason}>{reason}</option>)}
            </select>

            <label>Chi tiết</label>
            <textarea value={form.detail} onChange={(e) => setForm({ ...form, detail: e.target.value })} rows="3" placeholder="Ghi chú nếu cần" />

            {message && <div className="success-box">{message}</div>}
            {error && <div className="error-box">{error}</div>}
            <button className="primary-button" type="submit" disabled={saving}>{saving ? 'Đang ghi…' : 'Ghi'}</button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-title-row">
            <div><h2>Danh sách trong ngày</h2><p>{date}</p></div>
            <div className="penalty-chip">Phạt: {totalPenalty.toLocaleString('vi-VN')}đ</div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Nhân viên</th><th>Lý do</th><th className="right">Phạt</th></tr></thead>
              <tbody>
                {records.length === 0 ? (
                  <tr><td colSpan="3" className="empty-cell">Chưa có dữ liệu cho ngày này.</td></tr>
                ) : records.map((item) => (
                  <tr key={item.record_uid || `${item.employee_name}-${item.leave_reason}`}>
                    <td><strong>{item.employee_name}</strong></td>
                    <td>{item.leave_reason}</td>
                    <td className="right">{Number(item.penalty || 0).toLocaleString('vi-VN')}đ</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  )
}

function Metric({ icon: Icon, label, value }) {
  return <div className="metric-card"><div className="metric-icon"><Icon size={20} /></div><div><span>{label}</span><strong>{value}</strong></div></div>
}
