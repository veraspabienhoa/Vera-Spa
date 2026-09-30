import { useMemo } from 'react'
import { Trash2 } from 'lucide-react'
import { formatVeraDate } from '../lib/veraDate'
import { combineObligationGroups } from '../lib/payrollObligationGroups'

const money = value => Number(value || 0).toLocaleString('vi-VN') + 'đ'

export default function PayrollObligationTable({ groups = [], obligations = [], onRemove, disabled = false }) {
  const rows = useMemo(() => combineObligationGroups(groups, obligations), [groups, obligations])
  const total = rows.reduce((sum, row) => sum + row.total, 0)
  return <div className="payroll-obligation-group payroll-obligation-unified">
    <div className="responsive-data-table"><table aria-label="Nợ và nghĩa vụ chưa hoàn thành">
      <thead><tr><th>Nhân viên</th><th>Số tiền</th><th>Bắt đầu trừ</th><th>Nội dung</th><th>Thao tác</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.key}>
        <td><strong>{row.employee_name}</strong></td>
        <td><strong>{money(row.total)}</strong></td>
        <td>{row.details.map((item, index) => <div key={index}>{row.details.length > 1 ? `${index + 1}. ` : ''}{formatVeraDate(item.due_from, '—')}</div>)}</td>
        <td>{row.details.map((item, index) => <div key={index}>{row.details.length > 1 ? `${index + 1}. ` : ''}{item.content || 'Chưa hoàn thành nghĩa vụ Vi phạm'} · {item.type} · {money(item.amount)}</div>)}</td>
        <td>{row.details.map((item, index) => item.id && onRemove ? <div key={item.id}><button type="button" className="danger-button compact" disabled={disabled} aria-label={`Xóa khoản ${index + 1} của ${row.employee_name}`} onClick={() => onRemove(item.id)}><Trash2 size={14} />{row.details.length > 1 ? `Xóa khoản ${index + 1}` : 'Xóa'}</button></div> : null)}</td>
      </tr>)}</tbody>
      <tfoot><tr><th>Tổng cộng</th><td><strong>{money(total)}</strong></td><td colSpan={3}>{rows.length} nhân viên · {rows.reduce((sum, row) => sum + row.details.length, 0)} khoản</td></tr></tfoot>
    </table></div>
    {!rows.length && <div className="setup-note">Không có khoản đang mở.</div>}
  </div>
}
