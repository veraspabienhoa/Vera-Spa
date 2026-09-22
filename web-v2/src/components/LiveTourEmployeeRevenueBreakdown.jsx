import UiToolbar from './UiToolbar'
import UiCustomText from './UiCustomText'
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
  captureLabel = 'Chụp biểu đồ',
}) {
  const sortedItems = useMemo(() => sortChartItems(items, valueKey, sortMode), [items, sortMode, valueKey])
  const max = Math.max(1, ...sortedItems.map(item => Math.max(0, Number(item[valueKey] || 0))))

  return <div ref={captureRef} className="employee-revenue-chart" aria-label={label}>
    <div className="employee-revenue-chart-head">
      <h4>{label}</h4>
      <UiToolbar data-ui-key="u-ef1ca3a0ca06" className="employee-revenue-chart-actions" data-snapshot-ignore>
        <label>
          <span>Sắp xếp</span>
          <select aria-label={`Sắp xếp ${label}`} value={sortMode} onChange={(event) => onSortModeChange(event.target.value)}>
            <option value="value_desc">Giá trị giảm dần</option>
            <option value="value_asc">Giá trị tăng dần</option>
            <option value="name_asc">Tên A → Z</option>
            <option value="name_desc">Tên Z → A</option>
          </select>
        </label>
        {onCapture && <button data-ui-key="u-3c4ac8ea1ccf" type="button" className="secondary-button" disabled={copying} onClick={onCapture}><ClipboardCopy size={15}/>{copying ? 'Đang chụp…' : captureLabel}</button>}
      </UiToolbar>
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
  const tipChartRef = useRef(null)
  const [serviceSort, setServiceSort] = useState('value_desc')
  const [tipSort, setTipSort] = useState('value_desc')
  const [copying, setCopying] = useState(false)
  const [copyingTip, setCopyingTip] = useState(false)
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

  const copyTipChart = async () => {
    if (copyingTip || !tipChartRef.current) return
    setCopyingTip(true)
    setNotice('')
    try {
      await copyPngToClipboard(() => elementToPngBlob(tipChartRef.current))
      setNotice('Đã chụp toàn bộ Biểu đồ tiền TIP và lưu ảnh PNG vào clipboard. Cột số tiền đã được loại khỏi ảnh.')
    } catch (error) {
      setNotice(error?.message || 'Không chụp được Biểu đồ tiền TIP theo nhân viên.')
    } finally {
      setCopyingTip(false)
    }
  }

  const serviceTotal = items.reduce((sum, item) => sum + Number(item.service || 0), 0)
  const tipTotal = items.reduce((sum, item) => sum + Number(item.tip || 0), 0)

  return <section data-ui-key="u-7887eeaa4028" className="employee-revenue-section" aria-label="Thống kê doanh thu theo nhân viên">
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
    <RevenueBars
      items={items}
      valueKey="tip"
      label="Biểu đồ tiền TIP theo nhân viên"
      sortMode={tipSort}
      onSortModeChange={setTipSort}
      valueFormatter={money}
      captureRef={tipChartRef}
      onCapture={copyTipChart}
      copying={copyingTip}
      hideValuesInSnapshot
      captureLabel="Chụp toàn bảng"
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
      <table data-ui-key="u-f8ab6688e487" className="employee-revenue-table">
        <thead><tr><th data-ui-key="u-577b62b1e913" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-577b62b1e913">Nhân viên</UiCustomText></th><th data-ui-key="u-792bcb3d5bba" data-ui-label-default="Số dòng theo tour"><UiCustomText uiKey="u-792bcb3d5bba">Số dòng theo tour</UiCustomText></th><th data-ui-key="u-d04f54c8b12d" data-ui-label-default="Số dòng theo yêu cầu"><UiCustomText uiKey="u-d04f54c8b12d">Số dòng theo yêu cầu</UiCustomText></th><th data-ui-key="u-3f321e267c13" data-ui-label-default="Số dòng dịch vụ"><UiCustomText uiKey="u-3f321e267c13">Số dòng dịch vụ</UiCustomText></th><th data-ui-key="u-8b648f70a5eb" data-ui-label-default="Tiền dịch vụ"><UiCustomText uiKey="u-8b648f70a5eb">Tiền dịch vụ</UiCustomText></th><th data-ui-key="u-44cf97a87026" data-ui-label-default="Tiền TIP"><UiCustomText uiKey="u-44cf97a87026">Tiền TIP</UiCustomText></th><th data-ui-key="u-8e94256b50f1" data-ui-label-default="Tổng"><UiCustomText uiKey="u-8e94256b50f1">Tổng</UiCustomText></th></tr></thead>
        <tbody>
          {items.map(item => <tr key={item.employee}><td>{item.employee}</td><td>{item.tourRows}</td><td>{item.requestRows}</td><td>{item.rows}</td><td>{money(item.service)}</td><td>{money(item.tip)}</td><td>{money(item.total)}</td></tr>)}
          {!items.length && <tr><td colSpan="7">Không có dữ liệu phù hợp bộ lọc.</td></tr>}
        </tbody>
      </table>
    </div>
  </section>
}
