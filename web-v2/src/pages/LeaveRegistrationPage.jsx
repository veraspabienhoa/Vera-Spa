import { CalendarDays, CheckCircle2, Clock3, RefreshCw, UserRoundCheck, UsersRound } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { isApiConfigured, veraApi } from '../lib/api'
import { loadEmployees, loadLeaveReasons, loadLeaveRecords, loadLeaveSummary } from '../lib/data'

const formatDateInput = (date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = () => formatDateInput(new Date())

export default function LeaveRegistrationPage() {
  const [date, setDate] = useState(today())
  const [summary, setSummary] = useState({ working: 0, leave: 0, paid: 0, unpaid: 0 })
  const [records, setRecords] = useState([])
  const [reasons, setReasons] = useState([])
  const [employees, setEmployees] = useState([])
  const [form, setForm] = useState({ employee_name: '', leave_reason: '', detail: '' })
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      if (isApiConfigured) {
        const [summaryData, recordData, reasonData, employeeData] = await Promise.all([
          veraApi.leaveSummary(date),
          veraApi.leaveRecords(date),
          veraApi.leaveReasons(),
          veraApi.employees(),
        ])
        setSummary(summaryData)
        setRecords(recordData.records || [])
        setReasons(reasonData.reasons || [])
        setEmployees(employeeData.employees || [])
      } else {
        const [summaryData, recordData, reasonData, employeeData] = await Promise.all([
          loadLeaveSummary(date),
          loadLeaveRecords(date),
          loadLeaveReasons(),
          loadEmployees(),
        ])
        setSummary(summaryData)
        setRecords(recordData)
        setReasons(reasonData)
        setEmployees(employeeData)
      }
    } catch (err) {
      setError(err.message || 'Không tải được dữ liệu thật từ PostgreSQL/Supabase.')
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
      setError('Web V2 đang đọc dữ liệu thật. Chức năng Ghi sẽ được mở sau khi Python API dùng chung business rules hiện tại được triển khai; hiện chưa ghi trực tiếp vào PostgreSQL để tránh sai phép/phạt.')
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
          <span className="eyebrow"><CalendarDays size={15} /> Web V2 · dữ liệu thật</span>
          <h1 className="page-title">Đăng ký nghỉ</h1>
          <p className="page-subtitle">Đọc trực tiếp dữ liệu PostgreSQL/Supabase đã được bảo vệ bằng Supabase Auth + RLS/RPC.</p>
        </div>
        <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={17} className={busy ? 'spin' : ''} /> Làm mới</button>
      </div>

      {!isApiConfigured && (
        <div className="warning-box"><strong>Đã kết nối dữ liệu thật.</strong> Danh sách, số liệu, nhân viên và lý do nghỉ lấy từ PostgreSQL/Supabase. Nút Ghi tạm khóa cho tới khi Python API nghiệp vụ dùng chung với hệ thống hiện tại hoàn tất.</div>
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
            <select value={form.employee_name} onChange={(e) => setForm({ ...form, employee_name: e.target.value })} required>
              <option value="">-- Chọn nhân viên --</option>
              {employees.map((employee) => (
                <option key={employee.username} value={employee.username}>
                  {employee.username}{employee.full_name && employee.full_name !== employee.username ? ` · ${employee.full_name}` : ''}
                </option>
              ))}
            </select>

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
