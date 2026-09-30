import UiToolbar from './UiToolbar'
import ReportDatePreset from './ReportDatePreset'
import VeraMoneyInput from './VeraMoneyInput'
import VeraDateInput from './VeraDateInput'
import './LiveTourFilters.css'
import { useMemo } from 'react'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import { customerMatches } from '../lib/customerSearch'
import { customerTicketLabel } from '../lib/liveTourComboBooking'
import { TOUR_DATE_PRESETS, tourDateRange, tourFilterOptions } from '../lib/liveTourFilters'

export default function LiveTourFilters({ value, onChange, rows, customers = [], services = [], employees = [], showTotal = false, showTip = false }) {
  const options = useMemo(() => {
    const result = tourFilterOptions(rows)
    const merge = (key, labels) => {
      const unique = new Map(result[key].map((option) => [option.label, option]))
      labels.filter(Boolean).forEach((label) => unique.set(String(label), { value: key === 'customer' ? String(label).replace(' - ', ' ') : String(label), label: String(label) }))
      result[key] = [...unique.values()].sort((a, b) => a.label.localeCompare(b.label, 'vi'))
    }
    merge('customer', customers.map((customer) => [customer?.name, customer?.phone].filter(Boolean).join(' - ')))
    result.customer = result.customer.map(option => {
      const customer = customers.find(item => [item.name, item.phone].filter(Boolean).join(' - ') === option.label)
      return { ...option, badge: customer ? customerTicketLabel(customer) || 'Còn 0 vé combo' : undefined }
    })
    merge('employee', employees.map(employee => employee?.name || employee?.employee_name || employee?.username))
    merge('service', services.map((service) => service?.name || service?.service))
    return result
  }, [customers, rows, services, employees])
  const change = patch => onChange({ ...value, ...patch })
  const choosePreset = (preset, date) => change({ preset, ...(date ? { date_from: date, date_to: date } : preset === 'custom' ? {} : tourDateRange(preset)) })
  return <UiToolbar data-ui-key="u-aee0d456f8e9" className="live-tour-filters" role="group" aria-label="Bộ lọc danh sách">
    <UiToolbar data-ui-key="u-6cab38b8ea72" className="live-tour-filters-row live-tour-filters-dates">
      <ReportDatePreset key={value.preset + value.date_from + value.date_to} className="live-tour-filters-preset" value={value.preset} presets={TOUR_DATE_PRESETS} onChange={choosePreset}/>
      <label><span>Từ ngày</span><VeraDateInput value={value.date_from} max={value.date_to || undefined} onChange={e => change({ date_from: e.target.value, preset: 'custom' })}/></label>
      <label><span>Đến ngày</span><VeraDateInput value={value.date_to} min={value.date_from || undefined} onChange={e => change({ date_to: e.target.value, preset: 'custom' })}/></label>
    </UiToolbar>
    <UiToolbar data-ui-key="u-f4dd81a665cc" className={`live-tour-filters-row live-tour-filters-search${showTotal || showTip ? ' live-tour-filters-five' : ''}`}>
      <LiveTourSearchSelect label="Số hóa đơn" placeholder="Nhập hoặc chọn số hóa đơn" options={options.bill_no} value={value.bill_no || ''} searchValue={value.bill_no || ''} onSearch={text => change({ bill_no: text })} onChange={text => change({ bill_no: text })} showAllOptions emptyLabel="Tất cả"/>
      <LiveTourSearchSelect label="Nhân viên" placeholder="Tìm tên nhân viên" options={options.employee} value={value.employee} searchValue={value.employee} onSearch={text => change({ employee: text })} onChange={text => change({ employee: text })} showAllOptions emptyLabel="Tất cả"/>
      <LiveTourSearchSelect label="Khách hàng" placeholder="Tìm tên hoặc số điện thoại" filterOption={(option, query) => { const [name, phone] = option.label.split(' - '); return customerMatches({ name, phone }, query) }} options={options.customer} value={value.customer} searchValue={value.customer} onSearch={text => change({ customer: text })} onChange={text => change({ customer: text })} showAllOptions emptyLabel="Tất cả"/>
      <LiveTourSearchSelect label="Dịch vụ" placeholder="Tìm dịch vụ" options={options.service} value={value.service} searchValue={value.service} onSearch={text => change({ service: text })} onChange={text => change({ service: text })} showAllOptions emptyLabel="Tất cả"/>
      {showTotal && <label><span>Tổng tiền (đ)</span><VeraMoneyInput aria-label="Lọc tổng tiền" placeholder="Tất cả số tiền" value={value.total_amount ?? ''} onChange={event => change({ total_amount: event.target.value })}/></label>}
      {showTip && <label><span>Số tiền TIP (đ)</span><VeraMoneyInput aria-label="Lọc số tiền TIP" placeholder="Tất cả số tiền" value={value.tip_amount ?? ''} onChange={event => change({ tip_amount: event.target.value })}/></label>}
    </UiToolbar>
    <UiToolbar data-ui-key="u-4f2eb3da8de7" className="live-tour-filters-actions report-date-buttons">
      {TOUR_DATE_PRESETS.map(([id, label]) => <button key={id} type="button" className={`secondary-button live-tour-filters-reset ${value.preset === id ? 'active' : ''}`} aria-pressed={value.preset === id} onClick={() => choosePreset(id)}>{label}</button>)}
    </UiToolbar>
  </UiToolbar>
}
