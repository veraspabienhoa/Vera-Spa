export function breakCellValue(record, column, nowMs) {
  if (column === 'TG nghỉ còn lại' && record._attendance_break_active && record._break_countdown_deadline) {
    const deadline = Date.parse(record._break_countdown_deadline)
    if (Number.isFinite(deadline)) return Math.ceil((deadline - nowMs) / 60000)
  }
  if (record._break_from_attendance && ['Giờ ra', 'Giờ vào'].includes(column) && record[column]) {
    const date = new Date(record[column])
    if (Number.isFinite(date.getTime())) return date.toLocaleTimeString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour12: false })
  }
  return record[column] ?? ''
}
