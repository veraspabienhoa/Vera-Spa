const money = (value) => `${Number(value || 0).toLocaleString('vi-VN')} đ`
const labels = { pending_update: 'Sửa hóa đơn chờ', pending_delete: 'Xóa hóa đơn chờ', paid_invoice_update: 'Sửa hóa đơn đã thanh toán', paid_invoice_delete: 'Hủy hóa đơn đã thanh toán' }

export default function LiveTourInvoiceChanges({ changes }) {
  return <div className="live-tour-catalog-section"><h3>Lịch sử sửa / hủy hóa đơn</h3>
    {!changes.length && <p>Chưa có điều chỉnh hóa đơn trong phạm vi được phép xem.</p>}
    {[...changes].sort((a, b) => String(b.at).localeCompare(String(a.at))).map((change) => <details className="live-tour-data-card" key={change.id}>
      <summary><strong>{labels[change.action] || change.action} · {change.before?.bill_no || change.pending_id}</strong><br/>{change.at} · {change.actor}</summary>
      <p>Lý do: <strong>{change.reason}</strong></p>
      {['before', 'after'].map((key) => <div key={key}><h4>{key === 'before' ? 'Trước thay đổi' : 'Sau thay đổi'}</h4>
        {change[key] ? <><p>{change[key].customer_name || 'Khách lẻ'} · {change[key].customer_phone}</p>
          {change[key].entries?.map((entry, index) => <p key={index}>{entry.employee_name} · {entry.service} · {entry.room} · {money(entry.price)}</p>)}
          {change[key].total != null && <p>Giảm giá: {money(change[key].discount)} · TIP: {money(change[key].tip)} · Tổng tiền: <strong>{money(change[key].total)}</strong> · {change[key].payment_method}</p>}
          <p>Ghi chú: {change[key].note || '—'}</p></> : <p>Đã xóa / hủy; không còn trong sổ hóa đơn có hiệu lực.</p>}
      </div>)}
    </details>)}
  </div>
}
