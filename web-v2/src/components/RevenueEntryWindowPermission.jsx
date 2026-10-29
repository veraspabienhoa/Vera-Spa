import { useState } from 'react'

export default function RevenueEntryWindowPermission({ value, onChange, disabled = false }) {
  const [custom, setCustom] = useState(value !== null && ![3, 5, 7].includes(Number(value)))
  const selected = custom ? 'custom' : value === null ? 'all' : String(value)
  return <div className="revenue-entry-window-permission" style={{ width: '100%', minWidth: 0, padding: '10px', boxSizing: 'border-box', border: '1px solid #547461', borderRadius: '8px' }}>
    <label>Phạm vi Nhập doanh thu - chi phí<select aria-label="Phạm vi Nhập doanh thu - chi phí" disabled={disabled} value={selected} style={{ width: '100%', maxWidth: '100%' }} onChange={event => {
      const next = event.target.value
      setCustom(next === 'custom')
      onChange(next === 'all' ? null : next === 'custom' ? 1 : Number(next))
    }}><option value="3">3 ngày</option><option value="5">5 ngày</option><option value="7">7 ngày</option><option value="custom">Số ngày tùy chỉnh</option><option value="all">Tất cả các ngày</option></select></label>
    {custom && <label>Số ngày được nhập<input aria-label="Số ngày được nhập" type="number" min="1" max="36500" step="1" value={value ?? ''} disabled={disabled} onChange={event => onChange(event.target.value)} /></label>}
    <small>Gồm hôm nay và các ngày trước đó, theo giờ Việt Nam. Tất cả các ngày không giới hạn ngày giao dịch. Chỉ có hiệu lực khi được cấp quyền nhập.</small>
  </div>
}
