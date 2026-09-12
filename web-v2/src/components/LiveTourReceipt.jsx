import { receiptNumber, isComboRedemption } from '../lib/paymentPresentation'
import LiveTourPaymentQr from './LiveTourPaymentQr'
import { useCallback, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Printer, X } from 'lucide-react'
import './LiveTourReceipt.css'
import useDialogFocus from '../lib/useDialogFocus'

const money = (value) => Number(value || 0).toLocaleString('vi-VN') + ' đ'
const dateTime = (value) => value && !Number.isNaN(new Date(value).getTime()) ? new Date(value).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' }) : 'Chưa ghi nhận'

export default function LiveTourReceipt({ invoice, autoPrint, onClose }) {
  const prepaid = isComboRedemption(invoice)
  const bookings = [...new Set((invoice.entries || []).map(entry => `${dateTime(entry.booked_at)} · ${entry.booking_actor || 'Chưa ghi nhận người đặt'}`))]
  const printed = useRef(false)
  const dialogRef = useDialogFocus(onClose)
  const printReceipt = useCallback(async () => {
    const node = dialogRef.current
    if (!node) return
    await Promise.race([Promise.all([document.fonts?.ready, ...[...node.querySelectorAll('img')].map(img => img.decode?.().catch(() => undefined))]), new Promise(resolve => setTimeout(resolve, 5000))])
    if (node.isConnected) window.print()
  }, [dialogRef])
  useEffect(() => {
    if (!autoPrint || printed.current) return undefined
    const timer = setTimeout(() => { printed.current = true; void printReceipt() }, 250)
    return () => clearTimeout(timer)
  }, [invoice.id, autoPrint, printReceipt])
  return createPortal(<div id="live-tour-receipt" className="tour-receipt-backdrop"><section ref={dialogRef} tabIndex="-1" className="tour-receipt" role="dialog" aria-modal="true" aria-label={`Hóa đơn ${receiptNumber(invoice.bill_no)}`}>
    <div className="tour-receipt-actions"><button className="primary-button" onClick={printReceipt}><Printer size={16}/> In hóa đơn</button><button className="secondary-button" onClick={onClose}><X size={16}/> Đóng</button></div>
    <h2><span className="vera-receipt-brand">VERA</span> SPA</h2><p className="vera-receipt-address">193 Trương Định, Tam Hiệp, Đồng Nai</p><h3>HÓA ĐƠN DỊCH VỤ</h3><p>{receiptNumber(invoice.bill_no)}</p>
    {(bookings.length ? bookings : ['Chưa ghi nhận']).map(booking => <p key={booking}>Ngày giờ booking · Người đặt: {booking}</p>)}
    <p>Ngày giờ thanh toán · Người thanh toán: {dateTime(invoice.recorded_at || invoice.created_at)} · {invoice.actor || 'Chưa ghi nhận'}</p>
    <p>Khách hàng: <strong>{invoice.customer_name || 'Khách lẻ'}</strong>{invoice.customer_phone ? ` · ${invoice.customer_phone}` : ''}</p>
    <table><thead><tr><th>Dịch vụ</th><th>SL</th><th>Thành tiền</th></tr></thead><tbody>{(invoice.entries || []).flatMap((entry, index) => entry.service_items?.length && entry.price_source !== 'manual' ? entry.service_items.map((item) => <tr key={`${index}:${item.service_id}`}><td>{item.name}<small>{entry.employee_name} · {entry.room}</small></td><td>{item.quantity}</td><td>{money(prepaid ? 0 : item.unit_price * item.quantity)}</td></tr>) : [<tr key={index}><td>{entry.service}<small>{entry.employee_name} · {entry.room}</small></td><td>1</td><td>{money(prepaid ? 0 : entry.price)}</td></tr>])}</tbody></table>
    <dl><dt>Tiền dịch vụ</dt><dd>{money(prepaid ? 0 : invoice.subtotal)}</dd><dt>Giảm giá{invoice.discount_mode === 'percent' ? ` (${invoice.discount_percent}%)` : ''}</dt><dd>{money(invoice.discount)}</dd><dt>TIP</dt><dd>{money(invoice.tip)}</dd><dt><strong>Tổng tiền</strong></dt><dd><strong>{money(invoice.total)}</strong></dd></dl>
    <p>Thanh toán: {invoice.payment_method}</p>{prepaid && <p>Dịch vụ đã thanh toán khi mua vé Combo.</p>}{invoice.combo_units > 0 && <p>Đã trừ combo: {invoice.combo_units} lượt/vé</p>}{invoice.note && <p>Ghi chú: {invoice.note}</p>}<LiveTourPaymentQr bank={invoice.payment_bank} amount={Number(invoice.total)} reference={invoice.bill_no}/><p className="tour-receipt-thanks">Cảm ơn quý khách!</p>
  </section></div>, document.body)
}
