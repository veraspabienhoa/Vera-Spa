import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Printer, X } from 'lucide-react'
import './LiveTourReceipt.css'
import useDialogFocus from '../lib/useDialogFocus'

const money = (value) => Number(value || 0).toLocaleString('vi-VN') + ' đ'

export default function LiveTourReceipt({ invoice, autoPrint, onClose }) {
  const printed = useRef(false)
  const dialogRef = useDialogFocus(onClose)
  useEffect(() => {
    if (!autoPrint || printed.current) return undefined
    const timer = setTimeout(() => { printed.current = true; window.print() }, 250)
    return () => clearTimeout(timer)
  }, [invoice.id, autoPrint])
  return createPortal(<div id="live-tour-receipt" className="tour-receipt-backdrop"><section ref={dialogRef} tabIndex="-1" className="tour-receipt" role="dialog" aria-modal="true" aria-label={`Hóa đơn ${invoice.bill_no}`}>
    <div className="tour-receipt-actions"><button className="primary-button" onClick={() => window.print()}><Printer size={16}/> In hóa đơn</button><button className="secondary-button" onClick={onClose}><X size={16}/> Đóng</button></div>
    <h2>MASSAGE VERA</h2><h3>HÓA ĐƠN DỊCH VỤ</h3><p>{invoice.bill_no}</p><p>{invoice.effective_at ? new Date(invoice.effective_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }) : invoice.created_at}</p>
    <p>Khách hàng: <strong>{invoice.customer_name || 'Khách lẻ'}</strong>{invoice.customer_phone ? ` · ${invoice.customer_phone}` : ''}</p>
    <table><thead><tr><th>Dịch vụ</th><th>SL</th><th>Thành tiền</th></tr></thead><tbody>{(invoice.entries || []).flatMap((entry, index) => entry.service_items?.length && entry.price_source !== 'manual' ? entry.service_items.map((item) => <tr key={`${index}:${item.service_id}`}><td>{item.name}<small>{entry.employee_name} · {entry.room}</small></td><td>{item.quantity}</td><td>{money(item.unit_price * item.quantity)}</td></tr>) : [<tr key={index}><td>{entry.service}<small>{entry.employee_name} · {entry.room}</small></td><td>1</td><td>{money(entry.price)}</td></tr>])}</tbody></table>
    <dl><dt>Tiền dịch vụ</dt><dd>{money(invoice.subtotal)}</dd><dt>Giảm giá{invoice.discount_mode === 'percent' ? ` (${invoice.discount_percent}%)` : ''}</dt><dd>{money(invoice.discount)}</dd>{invoice.combo_covered_amount > 0 && <><dt>Combo đã thanh toán</dt><dd>{money(invoice.combo_covered_amount)}</dd></>}<dt>TIP</dt><dd>{money(invoice.tip)}</dd><dt><strong>Tổng tiền</strong></dt><dd><strong>{money(invoice.total)}</strong></dd></dl>
    <p>Thanh toán: {invoice.payment_method}</p>{invoice.combo_units > 0 && <p>Đã trừ combo: {invoice.combo_units} lượt/vé</p>}{invoice.note && <p>Ghi chú: {invoice.note}</p>}<p className="tour-receipt-thanks">Cảm ơn quý khách!</p>
  </section></div>, document.body)
}
