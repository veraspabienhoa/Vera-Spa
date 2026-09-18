import { ClipboardCopy } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'

import { copyPngToClipboard, elementToPngBlob } from '../lib/clipboardImage'
import { summarizeEmployeeRevenue } from '../lib/liveTourEmployeeRevenue'

const money = value => `${Number(value || 0).toLocaleString('vi-VN')} đ`

function RevenueBars({ items, valueKey, label }) {
  const max = Math.max(1, ...items.map(item => Math.max(0, Number(item[valueKey] || 0))))
  return <div className="employee-revenue-chart" aria-label={label}>
    <h4>{label}</h4>
    <div className="employee-revenue-chart-list">
      {items.map(item => <div className="employee-revenue-chart-row" key={item.employee}>
        <span className="employee-revenue-chart-name">{item.employee}</span>
        <span className="employee-revenue-chart-track"><i style={{ width: `${Math.max(0, Number(item[valueKey] || 0)) / max * 100}%` }}/></span>
        <strong>{money(item[valueKey])}</strong>
      </div>)}
      {!items.length && <p>Không có dữ liệu phù hợp bộ lọc.</p>}
    </div>
  </div>
}

export default function LiveTourEmployeeRevenueBreakdown({ rows }) {
  const items = useMemo(() => summarizeEmployeeRevenue(rows), [rows])
  const sectionRef = useRef(null)
  const [copying, setCopying] = useState(false)
  const [notice, setNotice] = useState('')

  const copySection = async () => {
    if (copying || !sectionRef.current) return
    setCopying(true)
    setNotice('')
    try {
      await copyPngToClipboard(() => elementToPngBlob(sectionRef.current))
      setNotice('Đã chụp toàn bộ bảng + biểu đồ và lưu ảnh vào clipboard.')
    } catch (error) {
      setNotice(error?.message || 'Không chụp được khu vực thống kê.')
    } finally {
      setCopying(false)
    }
  }

  const serviceTotal = items.reduce((sum, item) => sum + Number(item.service || 0), 0)
  const tipTotal = items.reduce((sum, item) => sum + Number(item.tip || 0), 0)

  return <section ref={sectionRef} className="employee-revenue-section" aria-label="Thống kê doanh thu theo nhân viên">
    <div className="employee-revenue-head">
      <div><h3>THỐNG KÊ THEO NHÂN VIÊN</h3><p>Tiền dịch vụ và tiền TIP theo đúng bộ lọc Báo cáo hiện tại.</p></div>
      <button data-snapshot-ignore type="button" className="secondary-button" disabled={copying} onClick={copySection}><ClipboardCopy size={16}/>{copying ? 'Đang chụp…' : 'Chụp toàn bộ section & copy'}</button>
    </div>
    {notice && <p data-snapshot-ignore className="employee-revenue-copy-status">{notice}</p>}
    <div className="employee-revenue-kpis">
      <div><span>Nhân viên</span><strong>{items.length}</strong></div>
      <div><span>Tiền dịch vụ</span><strong>{money(serviceTotal)}</strong></div>
      <div><span>Tiền TIP</span><strong>{money(tipTotal)}</strong></div>
    </div>
    <div className="employee-revenue-table-wrap">
      <table className="employee-revenue-table">
        <thead><tr><th>Nhân viên</th><th>Số dòng dịch vụ</th><th>Tiền dịch vụ</th><th>Tiền TIP</th><th>Tổng</th></tr></thead>
        <tbody>
          {items.map(item => <tr key={item.employee}><td>{item.employee}</td><td>{item.rows}</td><td>{money(item.service)}</td><td>{money(item.tip)}</td><td>{money(item.total)}</td></tr>)}
          {!items.length && <tr><td colSpan="5">Không có dữ liệu phù hợp bộ lọc.</td></tr>}
        </tbody>
      </table>
    </div>
    <div className="employee-revenue-charts">
      <RevenueBars items={items} valueKey="service" label="Biểu đồ tiền dịch vụ theo nhân viên"/>
      <RevenueBars items={items} valueKey="tip" label="Biểu đồ tiền TIP theo nhân viên"/>
    </div>
  </section>
}
