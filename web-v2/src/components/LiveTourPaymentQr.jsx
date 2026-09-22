import PaymentCustomerScreen from './PaymentCustomerScreen'
import { useState } from 'react'
import { paymentQrUrl, tipMoney } from '../lib/paymentPresentation'
export default function LiveTourPaymentQr({ bank, amount, reference, screenSettings }) {
  const url = paymentQrUrl(bank, amount, reference)
  const [failed, setFailed] = useState('')
  if (!url) return null
  return <div className="tour-payment-qr wide">
    <strong>Quét mã chuyển khoản · {tipMoney(amount)}</strong>
    {failed === url ? <p role="alert">Không tải được mã QR. Vui lòng chuyển khoản theo thông tin bên dưới.</p> : <img src={url} alt={`QR chuyển khoản ${tipMoney(amount)} đến ${bank.account_no}`} referrerPolicy="no-referrer" onError={() => setFailed(url)}/>}
    <PaymentCustomerScreen bank={bank} amount={amount} reference={reference} settings={screenSettings}/>
    <small>{bank.bank_id} · {bank.account_no} · {bank.account_name}</small>
  </div>
}
