import { formatVeraDate } from './veraDate'

const date = value => formatVeraDate(value, '—')

// Text-only content preserves every result safely, including long names and
// lists. Shared dialogs wrap on mobile and scroll without truncating records.
export function annualRequestFeedback(result) {
  const requests = result.requests || []
  const lines = [
    `${result.employee_count || 0} nhân viên khác nghỉ trong ${date(result.start)} – ${date(result.end)}`,
    `Cao nhất ${result.peak_with_applicant || 0} người/ngày nếu tính cả đơn này.`,
    '',
    ...((result.days || []).map(day => `${date(day.date)}: ${day.other_count || 0} người khác · Đã duyệt: ${day.approved_count || 0} · Chờ duyệt: ${day.pending_count || 0}`)),
    '',
    ...(requests.length ? requests.map(row => `${row.full_name || row.employee_name} · ${row.employee_name} · ${row.request_type} · ${row.status}\n${date(row.start_date)} – ${date(row.end_date)}`) : ['Không có nhân viên khác nghỉ trùng khoảng ngày này.']),
  ]
  return lines.join('\n')
}

export function annualOverviewFeedback(result, filters) {
  const days = result.days || []
  const occupied = days.filter(day => day.leave_count > 0)
  const lines = [
    `Khoảng ngày ${date(filters.start)} – ${date(filters.end)}`,
    result.has_alert ? 'Có ngày từ 3 người nghỉ, gồm cả đơn đang chờ duyệt. Không tính nhân viên nghỉ việc.'
      : occupied.length ? 'Không có ngày từ 3 người nghỉ trong khoảng ngày đã chọn.'
        : 'Không có nhân viên nghỉ trong khoảng ngày đã chọn.',
    '',
    ...occupied.map(day => `${date(day.date)}: ${day.leave_count} người nghỉ · ${day.pending_count || 0} người có đơn chờ duyệt\n${(day.departments || []).map(dept => `${dept.department_id}: ${dept.leave_count}/${dept.headcount}${dept.exceeds_threshold ? ' (vượt ngưỡng)' : ''}`).join(' · ')}`),
  ]
  return lines.join('\n')
}
