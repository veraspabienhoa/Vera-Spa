import { hasTourRevenueSummary, REPORT_DATA_ERROR } from '../lib/liveTourReportCollection'
import './LiveTourRevenueSummary.css'

const money = value => `${value.toLocaleString('vi-VN')} đ`

export default function LiveTourRevenueSummary({ summary }) {
  if (!hasTourRevenueSummary(summary)) return <p role="alert">{REPORT_DATA_ERROR}</p>
  const totals = summary
  return <dl className="tour-revenue-summary" aria-label="Tổng hợp doanh thu theo bộ lọc">
    <div className="tour-revenue-summary-total"><dt>Tổng doanh thu</dt><dd>{money(totals.totalRevenue)}</dd></div>
    <div className="tour-revenue-summary-invoices"><dt>Số hóa đơn</dt><dd>{totals.invoiceCount.toLocaleString('vi-VN')}</dd></div>
    <div><dt>Tiền dịch vụ</dt><dd>{money(totals.serviceRevenue)}</dd></div>
    <div><dt>Tiền TIP</dt><dd>{money(totals.tip)}</dd></div>
  </dl>
}
