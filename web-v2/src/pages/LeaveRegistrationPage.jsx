import { CalendarDays, CheckCircle2, Clock3, RefreshCw, UserRoundCheck, UsersRound } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { isApiConfigured, veraApi } from '../lib/api'
import {
  loadEmployees,
  loadLeaveDailyStats,
  loadLeaveReasons,
  loadLeaveRecords,
  loadLeaveSummary,
} from '../lib/data'

const DATE_FILTERS = ['Hôm qua', 'Hôm nay', 'Tuần này', 'Tuần sau', 'Tháng này', 'Tháng sau', 'Tùy chỉnh']

const formatDateInput = (date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = () => formatDateInput(new Date())
const addDays = (date, days) => {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}
const formatDateDisplay = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}/${month}/${year}` : ''
}
const rangeForFilter = (filter) => {
  const now = new Date()
  const monday = addDays(now, -((now.getDay() + 6) % 7))
  if (filter === 'Hôm qua') {
    const yesterday = addDays(now, -1)
    return [formatDateInput(yesterday), formatDateInput(yesterday)]
  }
  if (filter === 'Tuần này') return [formatDateInput(monday), formatDateInput(addDays(monday, 6))]
  if (filter === 'Tuần sau') {
    const nextMonday = addDays(monday, 7)
    return [formatDateInput(nextMonday), formatDateInput(addDays(nextMonday, 6))]
  }
  if (filter === 'Tháng này') {
    return [
      formatDateInput(new Date(now.getFullYear(), now.getMonth(), 1)),
      formatDateInput(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
    ]
  }
  if (filter === 'Tháng sau') {
    return [
      formatDateInput(new Date(now.getFullYear(), now.getMonth() + 1, 1)),
      formatDateInput(new Date(now.getFullYear(), now.getMonth() + 2, 0)),
    ]
  }
  return [today(), today()]
}
const emptyForm = { employee_name: '', leave_reason: '', detail: '', manual_penalty: '' }

export default function LeaveRegistrationPage({ user }) {
  const initialRange = useMemo(() => rangeForFilter('Hôm nay'), [])
  const [date, setDate] = useState(today())
  const [rangeFilter, setRangeFilter] = useState('Hôm nay')
  const [rangeStart, setRangeStart] = useState(initialRange[0])
  const [rangeEnd, setRangeEnd] = useState(initialRange[1])
  const [summary, setSummary] = useState({ working: 0, leave: 0, paid: 0, unpaid: 0 })
  const [dailyStats, setDailyStats] = useState([])
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
  const canChooseEmployee = role === 'admin'
  const canViewPenalty = role === 'admin' || user?.permissions?.employee_penalty_view === true
  const dateIsPast = role !== 'admin' && date < today()
  const canCreate = isApiConfigured
    && user?.permissions?.leave_create !== false
    && !user?.registration_locked
    && !dateIsPast

  const maxEmployeeDate = useMemo(() => {
    const now = new Date()
    return formatDateInput(new Date(now.getFullYear(), now.getMonth() + 2, 0))
  }, [])

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      if (isApiConfigured) {
        const [summaryData, dailyData, recordData, reasonData, employeeData] = await Promise.all([
          veraApi.leaveSummary(date),
          veraApi.leaveDailyStats(rangeStart, rangeEnd),
          veraApi.leaveRecords(date),
          veraApi.leaveReasons(),
          veraApi.employees(),
        ])
        setSummary(summaryData)
        setDailyStats(dailyData.days || [])
        setRecords(recordData.records || [])
        setReasons(reasonData.reasons || [])
        setEmployees(employeeData.employees || [])
      } else {
        const [summaryData, dailyData, recordData, reasonData, employeeData] = await Promise.all([
          loadLeaveSummary(date),
          loadLeaveDailyStats(rangeStart, rangeEnd),
          loadLeaveRecords(date),
          loadLeaveReasons(),
          loadEmployees(),
        ])
        setSummary(summaryData)
        setDailyStats(dailyData)
        setRecords(recordData)
        setReasons(reasonData.map((name) => ({ name, requires_manual_penalty: false })))
        setEmployees(employeeData)
      }
    } catch (err) {
      setError(err.message || 'Không tải được dữ liệu từ PostgreSQL/Supabase.')
    } finally {
      setBusy(false)
    }
  }, [date, rangeEnd, rangeStart])

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

  const chooseRangeFilter = (filter) => {
    setRangeFilter(filter)
    if (filter === 'Tùy chỉnh') return
    const [start, end] = rangeForFilter(filter)
    setRangeStart(start)
    setRangeEnd(end)
    setDate(filter === 'Hôm nay' || filter === 'Tháng này' || filter === 'Tuần này' ? today() : start)
  }

  const changeCustomStart = (value) => {
    setRangeStart(value)
    if (value > rangeEnd) setRangeEnd(value)
    setDate(value)
  }

  const changeCustomEnd = (value) => {
    setRangeEnd(value)
    if (value < rangeStart) setRangeStart(value)
  }

  const submit = async (event) => {
    event.preventDefault()
    setMessage('')
    setWarnings([])
    setError('')
    if (!canCreate) {
      setError(dateIsPast
        ? 'Không được đăng ký lịch nghỉ cho ngày trong quá khứ.'
        : user?.registration_locked
          ? 'Quyền đăng ký nghỉ của vai trò này đang bị Admin tạm khóa.'
          : 'Tài khoản hiện tại chưa được cấp quyền ghi lịch nghỉ.')
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
      setForm({
        ...emptyForm,
        employee_name: canChooseEmployee ? '' : (user?.employee_username || ''),
      })
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
        <div><h1 className="page-title">Đăng ký nghỉ</h1></div>
        <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={17} className={busy ? 'spin' : ''} /> Làm mới</button>
      </div>

      {!isApiConfigured && (
        <div className="warning-box"><strong>Chế độ chỉ đọc.</strong> API chưa được cấu hình nên nút Ghi đang khóa an toàn.</div>
      )}

      {isApiConfigured && user?.registration_locked && (
        <div className="warning-box"><strong>Đang khóa đăng ký.</strong> Admin đang tạm khóa quyền đăng ký nghỉ của vai trò {role}.</div>
      )}

      {isApiConfigured && user?.permissions?.leave_create === false && (
        <div className="warning-box"><strong>Chế độ chỉ xem.</strong> Tài khoản này chưa được cấp quyền ghi lịch nghỉ.</div>
      )}

      <section className="metric-grid">
        <Metric icon={UserRoundCheck} label="Đang làm việc" value={summary.working ?? 0} />
        <Metric icon={UsersRound} label="Tổng nghỉ" value={summary.leave ?? records.length} />
        <Metric icon={CheckCircle2} label="Có phép" value={summary.paid ?? 0} />
        <Metric icon={Clock3} label="Không phép" value={summary.unpaid ?? 0} />
      </section>

      <div className="date-toolbar range-toolbar">
        <div className="range-filter-buttons" role="group" aria-label="Lọc thời gian">
          {DATE_FILTERS.map((filter) => (
            <button
              type="button"
              key={filter}
              className={rangeFilter === filter ? 'active' : ''}
              onClick={() => chooseRangeFilter(filter)}
            >
              {filter}
            </button>
          ))}
        </div>
        {rangeFilter === 'Tùy chỉnh' && (
          <div className="custom-range">
            <DatePickerControl label="Từ ngày" value={rangeStart} onChange={changeCustomStart} />
            <DatePickerControl label="Đến ngày" value={rangeEnd} onChange={changeCustomEnd} />
          </div>
        )}
        <DatePickerControl
          label="Ngày đang xem"
          value={date}
          onChange={setDate}
          max={role === 'admin' ? undefined : maxEmployeeDate}
        />
      </div>

      <section className="panel daily-summary-panel">
        <div className="panel-title-row">
          <div>
            <h2>Thống kê chi tiết theo từng ngày</h2>
            <p>{formatDateDisplay(rangeStart)} – {formatDateDisplay(rangeEnd)} · Chọn ngày trong bảng để xem danh sách chi tiết.</p>
          </div>
        </div>
        <div className="table-wrap daily-summary-wrap">
          <table className="daily-summary-table">
            <thead>
              <tr>
                <th>Ngày</th>
                <th>Thứ ngày</th>
                <th className="center">Tổng nghỉ</th>
                <th>✅ Có phép</th>
                <th>⚠️ Phát sinh</th>
                <th>❌ Không phép</th>
                {canViewPenalty && <th>💰 Tổng tiền phạt</th>}
              </tr>
            </thead>
            <tbody>
              {dailyStats.length === 0 ? (
                <tr><td colSpan={canViewPenalty ? 7 : 6} className="empty-cell">Không có dữ liệu trong khoảng thời gian này.</td></tr>
              ) : dailyStats.map((day) => (
                <tr key={day.date} className={day.date === date ? 'selected-day-row' : ''}>
                  <td>
                    <button type="button" className="date-link" onClick={() => setDate(day.date)}>
                      {formatDateDisplay(day.date)}
                    </button>
                  </td>
                  <td>{day.weekday_label}</td>
                  <td className="center"><strong>{day.total_leave}</strong></td>
                  <td><span className={`quota-value ${day.paid_full ? 'limit-full' : ''}`}>{day.paid}</span></td>
                  <td><span className={`quota-value ${day.generated_full ? 'limit-full' : ''}`}>{day.generated}</span></td>
                  <td><span className="quota-value">{day.unpaid}</span></td>
                  {canViewPenalty && <td className="money-cell">{Number(day.total_penalty || 0).toLocaleString('vi-VN')} đ</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

            {selectedReason && !selectedReason.requires_manual_penalty && (
              <div className="info-box">
                Số ngày tính: <strong>{selectedReason.days ?? 0}</strong>
                {canViewPenalty && selectedReason.penalty !== null && selectedReason.penalty !== undefined && (
                  <> · Phạt nền: <strong>{Number(selectedReason.penalty || 0).toLocaleString('vi-VN')}đ</strong></>
                )}
              </div>
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

            {dateIsPast && <div className="warning-box"><strong>Ngày chỉ xem.</strong> Nhân viên không thể đăng ký cho ngày trong quá khứ.</div>}
            {message && <div className="success-box">{message}</div>}
            {warnings.map((warning) => <div className="warning-box" key={warning}>{warning}</div>)}
            {error && <div className="error-box">{error}</div>}
            <button className="primary-button" type="submit" disabled={saving || !canCreate}>{saving ? 'Đang kiểm tra & ghi…' : 'Ghi'}</button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-title-row">
            <div><h2>Danh sách trong ngày</h2><p>{formatDateDisplay(date)}</p></div>
            {canViewPenalty && <div className="penalty-chip">Phạt: {totalPenalty.toLocaleString('vi-VN')}đ</div>}
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Nhân viên</th><th>Lý do</th><th>Chi tiết</th>{canViewPenalty && <th className="right">Phạt</th>}</tr></thead>
              <tbody>
                {records.length === 0 ? (
                  <tr><td colSpan={canViewPenalty ? 4 : 3} className="empty-cell">Chưa có dữ liệu cho ngày này.</td></tr>
                ) : records.map((item) => (
                  <tr key={item.record_uid || `${item.employee_name}-${item.leave_reason}`}>
                    <td><strong>{item.employee_name}</strong></td>
                    <td>{item.leave_reason}</td>
                    <td className="detail-cell">{item.detail || '—'}</td>
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

function DatePickerControl({ label, value, onChange, min, max }) {
  return (
    <div className="date-input-group">
      <span className="date-input-label">{label}</span>
      <label className="date-picker-control">
        <span>{formatDateDisplay(value)}</span>
        <CalendarDays size={18} aria-hidden="true" />
        <input
          className="date-picker-native"
          type="date"
          aria-label={label}
          value={value}
          min={min}
          max={max}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
    </div>
  )
}

function Metric({ icon: Icon, label, value }) {
  return <div className="metric-card"><div className="metric-icon"><Icon size={20} /></div><div><span>{label}</span><strong>{value}</strong></div></div>
}
