import { formatVeraDate } from '../lib/veraDate'

export default function OnlineBookingDetails({ row }) {
  const missing = 'Chưa cung cấp'
  return <dl className="online-booking-details">
    <dt>Khách hàng</dt><dd>{row.customer_name}</dd>
    <dt>Số điện thoại</dt><dd>{row.phone}</dd>
    <dt>Ngày hẹn</dt><dd>{formatVeraDate(row.appointment_date, missing)}</dd>
    <dt>Giờ hẹn</dt><dd>{row.appointment_time || missing}</dd>
    <dt>Dịch vụ</dt><dd>{row.service || missing}</dd>
    <dt>Số khách</dt><dd>{row.guests ?? missing}</dd>
    {row.message && <><dt>Lời nhắn</dt><dd className="online-booking-message">{row.message}</dd></>}
  </dl>
}
