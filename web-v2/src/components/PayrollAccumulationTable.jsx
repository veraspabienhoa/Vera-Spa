import { formatVeraDate } from '../lib/veraDate'
const money = value => `${Number(value || 0).toLocaleString('vi-VN')}đ`
export default function PayrollAccumulationTable({ rows, onAdd, onEdit, onDelete, onRemoveRefund, busyEmployee, disabled }) {
  return <div className="responsive-data-table payroll-personal-admin-table"><table aria-label="Tích lũy và hoàn trả nhân viên">
    <thead><tr><th>Nhân viên</th><th>Trạng thái</th><th>Mục tiêu</th><th>Đã đóng</th><th>Còn phải đóng</th><th>Hoàn trả đã cài đặt</th><th>Kỳ / Ghi chú hoàn trả</th><th>Điều chỉnh tích lũy</th><th>Chi tiết</th></tr></thead>
    <tbody>{rows.map(item => <tr key={item.employee_name}>
      <td><strong>{item.employee_name}</strong><small>{item.full_name}</small></td>
      <td>{item.employment_status || '—'}<small>{item.hasTracking ? item.completed || Number(item.remaining || 0) <= 0 ? 'Đã hoàn thành đóng' : 'Đang còn đóng' : 'Chưa có số liệu tích lũy'}</small></td>
      <td>{item.hasTracking ? money(item.target) : '—'}</td><td>{item.hasTracking ? money(item.paid_total) : '—'}</td><td>{item.hasTracking ? money(item.remaining) : '—'}</td>
      <td><strong>{money(item.configuredRefund)}</strong></td>
      <td>{item.refunds.map(refund => <div key={refund.id}><strong>{money(refund.amount)}</strong> · {refund.period_label || `${formatVeraDate(refund.start, '—')} – ${formatVeraDate(refund.end, '—')}`} · {refund.note} <button type="button" className="danger-button compact" disabled={disabled} onClick={() => onRemoveRefund(refund.id)} aria-label={`Xóa hoàn trả ${refund.id} của ${item.employee_name}`}>Xóa hoàn trả</button></div>)}</td>
      <td>{item.hasTracking && !item.completed && Number(item.remaining || 0) > 0 && <div className="payroll-personal-adjust-actions">{[['Thêm', onAdd], ['Sửa', onEdit], ['Xóa', onDelete]].map(([label, action]) => <button key={label} type="button" className={label === 'Xóa' ? 'danger-button compact' : 'secondary-button compact'} disabled={disabled || busyEmployee === item.employee_name} onClick={() => action(item)}>{label}</button>)}</div>}</td>
      <td><details><summary>Xem</summary>{(item.periods || []).map((period, index) => <div key={index}>{period.batch} · {formatVeraDate(period.start, '—')} – {formatVeraDate(period.end, '—')} · Đóng: {money(period.contribution)} · Hoàn trả: {money(period.refund)}</div>)}{Number(item.manual_adjustment_total || 0) !== 0 && <div>Admin điều chỉnh: {money(item.manual_adjustment_total)}</div>}</details></td>
    </tr>)}</tbody>
    <tfoot><tr><th>Tổng cộng ({rows.length})</th><td></td><td>{money(rows.reduce((sum, row) => sum + Number(row.target || 0), 0))}</td><td>{money(rows.reduce((sum, row) => sum + Number(row.paid_total || 0), 0))}</td><td>{money(rows.reduce((sum, row) => sum + Number(row.remaining || 0), 0))}</td><td>{money(rows.reduce((sum, row) => sum + row.configuredRefund, 0))}</td><td colSpan={3}></td></tr></tfoot>
  </table>{!rows.length && <div className="setup-note">Chưa có dữ liệu tích lũy hoặc hoàn trả.</div>}</div>
}
