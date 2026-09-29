import { useState } from 'react'
import VeraDateInput from './VeraDateInput'
import { veraApi } from '../lib/api'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'
import './FacegateAttendancePreview.css'

const reasons = {
  no_mapped_evidence: 'Chưa có sự kiện đủ ánh xạ để tính thử.',
  unmapped_employees: 'Chưa ánh xạ đủ nhân viên có lịch làm việc.',
  unresolved_events: 'Có sự kiện chưa xác định được nhân viên, ca hoặc trạng thái.',
  attendance_differences: 'Kết quả chấm công còn khác TimeSoft.',
  raw_evidence_differences: 'Danh sách thời điểm quét còn khác TimeSoft.',
  incomplete_archive_days: 'Có ngày chưa lưu đủ log sau khi ngày kết thúc.',
  no_timesoft_reference: 'Chưa có log TimeSoft trong kỳ để đối chiếu.',
  device_status_semantics_unverified: 'Cần xác minh ý nghĩa mã trạng thái trên máy; không suy ra vào/ra từ mã 1/0.',
  production_cutover_review_required: 'Cần kiểm chứng công, nghỉ phép và Auto Check trên VPS trước khi chuyển nguồn.',
  unmapped_reference: 'Chưa có ánh xạ duy nhất', device_address_changed: 'IP máy đã thay đổi',
  unverified_status_type: 'Mã trạng thái chưa xác minh', no_vera_shift: 'Chưa có ca VERA phù hợp',
  overlapping_shifts: 'Có nhiều ca cùng phù hợp', invalid_timestamp: 'Ngày giờ không hợp lệ',
  conflicting_duplicate: 'Sự kiện trùng nhưng khác nội dung',
}
const fieldLabels = { check_in: 'Vào ca', check_out: 'Ra ca', punch_times: 'Nhóm quét', break_out: 'Ra nghỉ', break_in: 'Vào lại', break_actual_minutes: 'Số phút nghỉ', shift: 'Ca', shift_start: 'Bắt đầu ca', shift_end: 'Kết thúc ca' }
function comparisonValue(value) {
  if (Array.isArray(value)) return value.map(comparisonValue).join(' · ')
  if (value === null || value === undefined || value === '') return '—'
  const raw = String(value)
  return raw.includes('T') || /\d{4}[ ,]+\d{2}:\d{2}/.test(raw) ? formatVeraDateTime(raw, raw) : raw
}
function ComparedFields({ values }) {
  return <div>{Object.entries(values).map(([key, value]) => <div key={key}><strong>{fieldLabels[key] || key}:</strong> {comparisonValue(value)}</div>)}</div>
}

function yesterday() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const value = Object.fromEntries(parts.map(p => [p.type, p.value]))
  const day = new Date(`${value.year}-${value.month}-${value.day}T00:00:00Z`)
  day.setUTCDate(day.getUTCDate() - 1)
  return day.toISOString().slice(0, 10)
}

export default function FacegateAttendancePreview() {
  const [start, setStart] = useState(yesterday)
  const [end, setEnd] = useState(yesterday)
  const [result, setResult] = useState(null)
  const [payroll, setPayroll] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async (event, salary = false) => {
    event.preventDefault()
    if (!start || !end || end < start || (Date.parse(end) - Date.parse(start)) / 86400000 > 6) {
      setError('Chọn khoảng từ 1 đến 7 ngày.'); return
    }
    setBusy(true); setError(''); setResult(null); setPayroll(null)
    try {
      if (salary) setPayroll(await veraApi.previewFacegatePayroll(start, end))
      else setResult(await veraApi.previewFacegateAttendance(start, end))
    }
    catch (cause) { setError(cause.message || 'Không đọc được dữ liệu đối chiếu.') }
    finally { setBusy(false) }
  }
  const change = setter => event => { setter(event.target.value); setResult(null); setPayroll(null); setError('') }
  return <details className="facegate-attendance-preview"><summary>Đối chiếu FaceGate → Chấm công VERA</summary>
    <p>Tính thử từ log đã lưu theo lịch VERA. TimeSoft vẫn là nguồn chính. Không ghi công, lương hoặc phạt khi đối chiếu.</p>
    <form onSubmit={run}><fieldset disabled={busy}><label>Từ ngày<VeraDateInput required value={start} onChange={change(setStart)} /></label><label>Đến ngày<VeraDateInput required value={end} onChange={change(setEnd)} /></label><button className="secondary-button" disabled={busy} type="submit">{busy ? 'Đang đối chiếu…' : 'Tính thử và đối chiếu'}</button><button type="button" className="secondary-button" disabled={busy} onClick={event => run(event, true)}>Tính lương cơ bản từ FaceGate</button></fieldset></form>
    {error && <p role="alert">{error}</p>}
    {payroll && <section aria-label="Lương cơ bản FaceGate">
      <p role="status">{formatVeraDate(payroll.start)} – {formatVeraDate(payroll.end)} · {payroll.pending_count} nhân viên chờ bổ sung công.</p>
      <p>Lương cơ bản tạm tính theo cấu hình VERA, chưa gồm phụ cấp, tip, thưởng, phạt hoặc tạm ứng. Chưa lưu bảng lương chính thức. Nhân viên thiếu dữ liệu hiển thị “Chờ bổ sung”, không tính thành 0 đồng.</p>
      <div className="responsive-data-table"><table><thead><tr><th>Nhân viên</th><th>Bộ phận</th><th>Giờ tính thử</th><th>Lương cơ bản tạm tính</th><th>Trạng thái</th></tr></thead><tbody>{payroll.rows.map(row => <tr key={row.employee_username}><td>{row.employee_name}</td><td>{row.department_label}</td><td>{row.hours ?? '—'}</td><td>{row.basic_salary_estimate === null ? 'Chờ bổ sung' : new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(row.basic_salary_estimate)}</td><td>{row.pending_reasons.length ? row.pending_reasons.join(' · ') : 'Đã tính thử, cần đối chiếu'}</td></tr>)}</tbody></table></div>
      <p>Tổng lương cơ bản các dòng đã tính thử: {new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(payroll.estimated_basic_pay_total)}. Tổng chưa bao gồm nhân viên chờ bổ sung.</p>
      {!!payroll.blockers.length && <details><summary>Các mục đối chiếu còn lại</summary><ul>{payroll.blockers.map(key => <li key={key}>{reasons[key] || key}</li>)}</ul></details>}
      <p>Lương KTV theo tip được xử lý ở bảng Lương KTV; lượt quét FaceGate không thay thế dữ liệu tip.</p>
    </section>}
    {result && <>
      <p role="status">{formatVeraDate(result.start)} – {formatVeraDate(result.end)} · {result.facegate_event_count} lượt quét đã ánh xạ · {result.differences.length} dòng chấm công khác · {result.evidence_differences.length} nhân viên khác log gốc · {result.issue_count} sự kiện cần kiểm tra.</p>
      <p>Đồng bộ gần nhất: {formatVeraDateTime(result.last_sync_at, 'Chưa có')}. Quét lặp được gom trong 5 phút. Ca bình thường không bắt buộc quét kết thúc.</p>
      <details open><summary>Điều kiện còn thiếu trước khi bỏ TimeSoft</summary><ul>{result.blockers.map(reason => <li key={reason}>{reasons[reason] || reason}</li>)}</ul>
        {!!result.unmapped_employees.length && <p>Chưa ánh xạ: {result.unmapped_employees.join(' · ')}</p>}
        {!!result.incomplete_days.length && <p>Ngày chưa đủ log: {result.incomplete_days.map(day => formatVeraDate(day)).join(' · ')}</p>}
      </details>
      <div className="responsive-data-table"><table><thead><tr><th>Ngày làm việc</th><th>Nhân viên VERA</th><th>Ca VERA</th><th>Vào ca</th><th>Các nhóm quét</th><th>Ra / vào nghỉ</th></tr></thead><tbody>{result.records.map(row => <tr key={`${row.date}:${row.employee_name}`}><td>{formatVeraDate(row.date)}</td><td>{row.employee_name}</td><td>{row.shift || '—'}{row.overnight_shift ? ' · qua đêm' : ''}</td><td>{row.check_in_at ? formatVeraDateTime(row.check_in_at) : row.check_in || '—'}</td><td>{(row.punch_datetimes || row.punch_times || []).map(value => value.includes('T') ? formatVeraDateTime(value) : value).join(' · ') || '—'}</td><td>{row.break_out || '—'} / {row.break_in || '—'}</td></tr>)}</tbody></table></div>
      <details><summary>Gợi ý ánh xạ từ thời điểm quét trùng khớp</summary><p>Đây là gợi ý đối chiếu. Đọc ID hồ sơ trên máy và xác nhận ở bảng Ánh xạ bên trên; không dùng mã TimeSoft làm ID FaceGate.</p>
        <div className="responsive-data-table"><table><thead><tr><th>Tên trên máy</th><th>Nhân viên VERA gợi ý</th><th>Số lượt</th><th>Tham chiếu hồ sơ</th></tr></thead><tbody>{result.mapping_candidates.map((row, i) => <tr key={i}><td>{row.device_names.join(' · ')}</td><td>{row.username_candidate || (row.status === 'ambiguous' ? 'Nhiều kết quả — cần đối chiếu' : 'Chưa khớp')}</td><td>{row.event_count}</td><td>{JSON.stringify(row.registration_ref)}</td></tr>)}</tbody></table></div>
      </details>
      {!!result.issues.length && <details><summary>Sự kiện cần kiểm tra{result.issues_truncated ? ' (200 dòng đầu)' : ''}</summary><ul>{result.issues.map((row, i) => <li key={i}>#{row.event_id} · {row.username || row.device_name || ''} · {reasons[row.reason] || row.reason}</li>)}</ul></details>}
      {!!result.evidence_differences.length && <details><summary>Thời điểm quét chưa khớp</summary><div className="responsive-data-table"><table><thead><tr><th>Nhân viên</th><th>Thiếu bên FaceGate</th><th>Chỉ có bên FaceGate</th></tr></thead><tbody>{result.evidence_differences.map(row => <tr key={row.employee_name}><td>{row.employee_name}</td><td>{row.missing_in_facegate.map(value => formatVeraDateTime(value)).join(' · ') || '—'}</td><td>{row.extra_in_facegate.map(value => formatVeraDateTime(value)).join(' · ') || '—'}</td></tr>)}</tbody></table></div></details>}
      {!!result.differences.length && <details><summary>Chi tiết kết quả khác nhau</summary><div className="responsive-data-table"><table><thead><tr><th>Ngày</th><th>Nhân viên</th><th>TimeSoft</th><th>FaceGate</th></tr></thead><tbody>{result.differences.map(row => <tr key={`${row.date}:${row.employee_name}`}><td>{formatVeraDate(row.date)}</td><td>{row.employee_name}</td><td><ComparedFields values={row.timesoft}/></td><td><ComparedFields values={row.facegate}/></td></tr>)}</tbody></table></div></details>}
    </>}
  </details>
}
