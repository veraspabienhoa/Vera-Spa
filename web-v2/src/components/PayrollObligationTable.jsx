import { Fragment, useMemo, useState } from 'react'
import { formatVeraDate } from '../lib/veraDate'
import { combineObligationGroups } from '../lib/payrollObligationGroups'

const money = value => Number(value || 0).toLocaleString('vi-VN') + 'đ'
const dateText = value => formatVeraDate(value, '—')

export default function PayrollObligationTable({ groups }) {
  const rows = useMemo(() => combineObligationGroups(groups), [groups])
  const [expanded, setExpanded] = useState(new Set())
  const toggle = key => setExpanded(current => {
    const next = new Set(current)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })
  return <div className="payroll-obligation-group payroll-obligation-unified">
    <h3>Nợ &amp; Nghĩa vụ chưa hoàn thành</h3>
    {rows.length ? <div className="responsive-data-table"><table aria-label="Nợ và nghĩa vụ chưa hoàn thành">
      <thead><tr><th>Nhân viên</th><th>Nợ thực nhận âm</th><th>Vi phạm tạm hoãn</th><th>Tổng còn phải trừ</th><th>Số khoản</th><th>Chi tiết</th></tr></thead>
      <tbody>{rows.map(row => <Fragment key={row.key}>
        <tr><td><strong>{row.employee_name}</strong></td><td>{money(row.negative)}</td><td>{money(row.deferred)}</td><td><strong>{money(row.total)}</strong></td><td>{row.details.length}</td><td><button type="button" className="secondary-button compact" aria-label={`${expanded.has(row.key) ? 'Ẩn' : 'Xem'} chi tiết ${row.employee_name}`} aria-expanded={expanded.has(row.key)} aria-controls={`payroll-debt-details-${encodeURIComponent(row.key)}`} onClick={() => toggle(row.key)}>{expanded.has(row.key) ? 'Ẩn chi tiết' : 'Xem chi tiết'}</button></td></tr>
        {expanded.has(row.key) && <tr id={`payroll-debt-details-${encodeURIComponent(row.key)}`}><td colSpan={6}>
          <div className="responsive-data-table"><table aria-label={`Chi tiết nợ ${row.employee_name}`}>
            <thead><tr><th>Loại khoản</th><th>Số tiền còn lại</th><th>Kỳ phát sinh</th><th>Bắt đầu trừ từ</th><th>Nội dung</th><th>Trạng thái</th></tr></thead>
            <tbody>{row.details.map((item, index) => <tr key={index}><td>{item.type}</td><td>{money(item.amount)}</td><td>{dateText(item.period_start)} – {dateText(item.period_end)}</td><td>{dateText(item.due_from)}</td><td>{item.content}</td><td>{item.status}</td></tr>)}</tbody>
          </table></div>
        </td></tr>}
      </Fragment>)}</tbody>
    </table></div> : <div className="setup-note">Không có khoản đang mở.</div>}
  </div>
}
