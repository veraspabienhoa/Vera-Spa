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
const emptyForm = { employee_name: '', leave_reason: '', detail: '', manual_penalty: '' }

export default function LeaveRegistrationPage({ user }) {
  const [date, setDate] = useState(today())
  const [summary, setSummary] = useState({ working: 0, leave: 0, paid: 0, unpaid: 0 })
  const [records, setRecords] = useState([])
  const [reasons, setReasons] = useState([])
  const [employees, setEmployees] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [warnings, setWarnings] = useState([])
  const [error, setError] = useState('')
  const role = String(user?.role || '').toLowerCase()
  const canChooseEmployee = ['admin', 'quanly', 'letan'].includes(role)
  const canViewPenalty = role === 'admin'
  const canCreate = isApiConfigured
    && user?.permissions?.leave_create !== false
    && !user?.registration_locked

  const maxEmployeeDate = useMemo(() => {
    const now = new Date()
    return formatDateInput(new Date(now.getFullYear(), now.getMonth() + 2, 0))
  }, [])

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
        setReasons(reasonData.map((name) => ({ name, requires_manual_penalty: false })))
        setEmployees(employeeData)
      }
    } catch (err) {
      setError(err.message || 'Không tải được dữ liệu thật từ PostgreSQL/Supabase.')
    } finally {
      setBusy(false)
    }
  }, [date])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (canChooseEmployee || !user?.employee_username) return
    setForm((current) => ({ ...current, employee_name: user.employee_username }))
  }, [canChooseEmployee, user?.employee_username])

  const totalPenalty = useMemo(
    () => records.reduce((sum, item) => sum + Number(item.penalty || 0), 0),
    [records],
  )
  const selectedReason = useMemo(() => reasons.find((item) => item.name === form.leave_reason), [reasons, form.leave_reason])

  const shiftDate = (offset) => {
    const current = new Date(`${date}T00:00:00`)
    current.setDate(current.getDate() + offset)
    setDate(formatDateInput(current))
  }

  const submit = async (event) => {
    event.preventDefault()
    setMessage('')
    setWarnings([])
    setError('')
    if (!canCreate) {
      setError(user?.registration_locked
        ? 'Quyền đăng ký nghỉ của vai trò này đang bị Admin tạm khóa.'
        : 'Tài khoản hiện tại chưa được cấp quyền ghi lịch nghỉ trên Web V2.')
      return
    }
    setSaving(true)
    try {
      const payload = {
        employee_name: form.employee_name,
        leave_reason: form.leave_reason,
        detail: form.detail,
        leave_date: date,
      }
      if (selectedReason?.requires_manual_penalty) {
        if (form.manual_penalty === '') throw new Error('Lý do này bắt buộc nhập Mức phạt vi phạm.')
        payload.manual_penalty = Number(form.manual_penalty)
      }
      const result = await veraApi.createLeave(payload)
      setForm(emptyForm)
      setWarnings(result.warnings || [])
      setMessage(result.message || 'Đã ghi đăng ký nghỉ.')
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
          <span className="eyebrow"><CalendarDays size={15} /> Web V2 · Python business API</span>
          <h1 className="page-title">Đăng ký nghỉ</h1>
          <p className="page-subtitle">Dữ liệu thật PostgreSQL; khi ghi, Python API xác thực tài khoản, đọc Nội quy/LoaiNghi và mirror MainData.</p>
        </div>
        <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={17} className={busy ? 'spin' : ''} /> Làm mới</button>
      </div>

      {!isApiConfigured && (
        <div className="warning-box"><strong>Chế độ chỉ đọc.</strong> Python API V2 chưa có URL trong GitHub Pages nên nút Ghi vẫn khóa an toàn.</div>
      )}

      {isApiConfigured && user?.registration_locked && (
        <div className="warning-box"><strong>Đang khóa đăng ký.</strong> Admin đang tạm khóa quyền đăng ký nghỉ của vai trò {role}.</div>
      )}

      {isApiConfigured && user?.permissions?.leave_create === false && (
        <div className="warning-box"><strong>Chế độ chỉ xem.</strong> Tài khoản này chưa được cấp quyền ghi lịch nghỉ.</div>
      )}

      <div className="date-toolbar">
        <button onClick={() => shiftDate(-1)}>Hôm qua</button>
        <button onClick={() => setDate(today())}>Hôm nay</button>
        <button onClick={() => shiftDate(1)}>Ngày mai</button>
        <input
          type="date"
          value={date}
          min={role === 'admin' ? undefined : today()}
          max={role === 'admin' ? undefined : maxEmployeeDate}
          onChange={(e) => setDate(e.target.value)}
        />
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
            <div><h2>Đăng ký mới</h2><p>Ngày tính và mức phạt mặc định do server lấy từ Nội quy; trình duyệt không được tự quyết định.</p></div>
          </div>
          <form className="leave-form" onSubmit={submit}>
            <label>Tên nhân viên</label>
            <select
              value={form.employee_name}
              onChange={(e) => setForm({ ...form, employee_name: e.target.value })}
              disabled={!canChooseEmployee}
              required
            >
              <option value="">-- Chọn nhân viên --</option>
              {employees.map((employee) => (
                <option key={employee.username} value={employee.username}>
                  {employee.username}{employee.full_name && employee.full_name !== employee.username ? ` · ${employee.full_name}` : ''}
                </option>
              ))}
            </select>

            <label>Lý do nghỉ</label>
            <select value={form.leave_reason} onChange={(e) => setForm({ ...form, leave_reason: e.target.value, manual_penalty: '' })} required>
              <option value="">-- Chọn lý do nghỉ --</option>
              {reasons.map((reason) => <option key={reason.name} value={reason.name}>{reason.name}</option>)}
            </select>

            {selectedReason && !selectedReason.requires_manual_penalty && selectedReason.penalty !== null && selectedReason.penalty !== undefined && (
              <div className="info-box">Số ngày tính: <strong>{selectedReason.days ?? 0}</strong> · Phạt nền: <strong>{Number(selectedReason.penalty || 0).toLocaleString('vi-VN')}đ</strong>. Giá trị cuối cùng vẫn do server kiểm tra lại khi Ghi.</div>
            )}

            {selectedReason?.requires_manual_penalty && (
              <>
                <label>Mức phạt vi phạm</label>
                <input
                  type="number"
                  min="0"
                  step="1000"
                  value={form.manual_penalty}
                  onChange={(e) => setForm({ ...form, manual_penalty: e.target.value })}
                  placeholder="Nhập số tiền"
                  required
                />
              </>
            )}

            <label>Chi tiết</label>
            <textarea value={form.detail} onChange={(e) => setForm({ ...form, detail: e.target.value })} rows="3" placeholder="Ghi chú nếu cần" />

            {message && <div className="success-box">{message}</div>}
            {warnings.map((warning) => <div className="warning-box" key={warning}>{warning}</div>)}
            {error && <div className="error-box">{error}</div>}
            <button className="primary-button" type="submit" disabled={saving || !canCreate}>{saving ? 'Đang kiểm tra & ghi…' : 'Ghi'}</button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-title-row">
            <div><h2>Danh sách trong ngày</h2><p>{date}</p></div>
            {canViewPenalty && <div className="penalty-chip">Phạt: {totalPenalty.toLocaleString('vi-VN')}đ</div>}
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Nhân viên</th><th>Lý do</th>{canViewPenalty && <th className="right">Phạt</th>}</tr></thead>
              <tbody>
                {records.length === 0 ? (
                  <tr><td colSpan={canViewPenalty ? 3 : 2} className="empty-cell">Chưa có dữ liệu cho ngày này.</td></tr>
                ) : records.map((item) => (
                  <tr key={item.record_uid || `${item.employee_name}-${item.leave_reason}`}>
                    <td><strong>{item.employee_name}</strong></td>
                    <td>{item.leave_reason}</td>
                    {canViewPenalty && <td className="right">{Number(item.penalty || 0).toLocaleString('vi-VN')}đ</td>}
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
