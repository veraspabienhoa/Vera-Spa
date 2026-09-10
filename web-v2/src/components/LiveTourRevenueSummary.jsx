import { summarizeTourRevenue } from '../lib/liveTourRevenue'
import './LiveTourRevenueSummary.css'

const money = value => `${value.toLocaleString('vi-VN')} đ`

export default function LiveTourRevenueSummary({ rows }) {
  const totals = summarizeTourRevenue(rows)
  return <dl className="tour-revenue-summary" aria-label="Tổng hợp doanh thu theo bộ lọc">
    <div className="tour-revenue-summary-total"><dt>Tổng doanh thu</dt><dd>{money(totals.totalRevenue)}</dd></div>
    <div><dt>Tiền dịch vụ</dt><dd>{money(totals.serviceRevenue)}</dd></div>
    <div><dt>Tiền TIP</dt><dd>{money(totals.tip)}</dd></div>
  </dl>
}
