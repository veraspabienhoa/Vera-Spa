import { ClipboardCopy } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'

import { copyPngToClipboard, elementToPngBlob } from '../lib/clipboardImage'
import { summarizeEmployeeRevenue } from '../lib/liveTourEmployeeRevenue'

const money = value => `${Number(value || 0).toLocaleString('vi-VN')} đ`
const integer = value => Number(value || 0).toLocaleString('vi-VN')

function sortChartItems(items, valueKey, sortMode) {
  const sorted = [...items]
  if (sortMode === 'value_asc') return sorted.sort((a, b) => Number(a[valueKey] || 0) - Number(b[valueKey] || 0) || a.employee.localeCompare(b.employee, 'vi'))
  if (sortMode === 'name_asc') return sorted.sort((a, b) => a.employee.localeCompare(b.employee, 'vi'))
  if (sortMode === 'name_desc') return sorted.sort((a, b) => b.employee.localeCompare(a.employee, 'vi'))
  return sorted.sort((a, b) => Number(b[valueKey] || 0) - Number(a[valueKey] || 0) || a.employee.localeCompare(b.employee, 'vi'))
}

function RevenueBars({
  items,
  valueKey,
  label,
  sortMode,
  onSortModeChange,
  valueFormatter = money,
  captureRef,
  onCapture,
  copying = false,
  hideValuesInSnapshot = false,
}) {
  const sortedItems = useMemo(() => sortChartItems(items, valueKey, sortMode), [items, sortMode, valueKey])
  const max = Math.max(1, ...sortedItems.map(item => Math.max(0, Number(item[valueKey] || 0))))

  return <div ref={captureRef} className="employee-revenue-chart" aria-label={label}>
    <div className="employee-revenue-chart-head">
      <h4>{label}</h4>
      <div className="employee-revenue-chart-actions" data-snapshot-ignore>
        <label>
          <span>Sắp xếp</span>
          <select aria-label={`Sắp xếp ${label}`} value={sortMode} onChange={(event) => onSortModeChange(event.target.value)}>
            <option value="value_desc">Giá trị giảm dần</option>
            <option value="value_asc">Giá trị tăng dần</option>
            <option value="name_asc">Tên A → Z</option>
            <option value="name_desc">Tên Z → A</option>
          </select>
        </label>
        {onCapture && <button type="button" className="secondary-button" disabled={copying} onClick={onCapture}><ClipboardCopy size={15}/>{copying ? 'Đang chụp…' : 'Chụp biểu đồ'}</button>}
      </div>
    </div>
    <div className="employee-revenue-chart-list">
      {sortedItems.map(item => <div className="employee-revenue-chart-row" key={item.employee}>
        <span className="employee-revenue-chart-name">{item.employee}</span>
        <span className="employee-revenue-chart-track"><i style={{ width: `${Math.max(0, Number(item[valueKey] || 0)) / max * 100}%` }}/></span>
        <strong data-snapshot-ignore={hideValuesInSnapshot ? true : undefined}>{valueFormatter(item[valueKey])}</strong>
      </div>)}
      {!sortedItems.length && <p>Không có dữ liệu phù hợp bộ lọc.</p>}
    </div>
  </div>
}

export default function LiveTourEmployeeRevenueBreakdown({ rows }) {
  const items = useMemo(() => summarizeEmployeeRevenue(rows), [rows])
  const serviceChartRef = useRef(null)
  const [serviceSort, setServiceSort] = useState('value_desc')
  const [tipSort, setTipSort] = useState('value_desc')
  const [copying, setCopying] = useState(false)
  const [notice, setNotice] = useState('')

  const copyServiceChart = async () => {
    if (copying || !serviceChartRef.current) return
    setCopying(true)
    setNotice('')
    try {
      await copyPngToClipboard(() => elementToPngBlob(serviceChartRef.current))
      setNotice('Đã chụp Biểu đồ dịch vụ theo nhân viên và lưu ảnh vào clipboard.')
    } catch (error) {
      setNotice(error?.message || 'Không chụp được Biểu đồ dịch vụ theo nhân viên.')
    } finally {
      setCopying(false)
    }
  }

  const serviceTotal = items.reduce((sum, item) => sum + Number(item.service || 0), 0)
  const tipTotal = items.reduce((sum, item) => sum + Number(item.tip || 0), 0)

  return <section className="employee-revenue-section" aria-label="Thống kê doanh thu theo nhân viên">
    <RevenueBars
      items={items}
      valueKey="rows"
      label="Biểu đồ dịch vụ theo nhân viên"
      sortMode={serviceSort}
      onSortModeChange={setServiceSort}
      valueFormatter={integer}
      captureRef={serviceChartRef}
      onCapture={copyServiceChart}
      copying={copying}
      hideValuesInSnapshot
    />
    {notice && <p data-snapshot-ignore className="employee-revenue-copy-status">{notice}</p>}
    <div className="employee-revenue-head">
      <div><h3>THỐNG KÊ THEO NHÂN VIÊN</h3><p>Tiền dịch vụ và tiền TIP theo đúng bộ lọc Báo cáo hiện tại.</p></div>
    </div>
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
    <RevenueBars
      items={items}
      valueKey="tip"
      label="Biểu đồ tiền TIP theo nhân viên"
      sortMode={tipSort}
      onSortModeChange={setTipSort}
      valueFormatter={money}
    />
  </section>
}
