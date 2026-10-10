import UiToolbar from './UiToolbar'
import ReportDatePreset from './ReportDatePreset'
import VeraMoneyInput from './VeraMoneyInput'
import VeraDateInput from './VeraDateInput'
import './LiveTourFilters.css'
import { useMemo, useRef, useState } from 'react'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import { customerMatches } from '../lib/customerSearch'
import { customerTicketLabel } from '../lib/liveTourComboBooking'
import { TOUR_DATE_PRESETS, tourDateRange, tourFilterOptions } from '../lib/liveTourFilters'

const EMPTY_OPTIONS = []
export default function LiveTourFilters({ value, onChange, rows, customers = EMPTY_OPTIONS, services = EMPTY_OPTIONS, employees = EMPTY_OPTIONS, showTotal = false, showTip = false, showDate = false, allowedPresets = null, serverToday = '', onValidityChange }) {
  const options = useMemo(() => {
    const result = tourFilterOptions(rows)
    const merge = (key, labels) => {
      const unique = new Map(result[key].map((option) => [option.label, option]))
      labels.filter(Boolean).forEach((label) => unique.set(String(label), { value: key === 'customer' ? String(label).replace(' - ', ' ') : String(label), label: String(label) }))
      result[key] = [...unique.values()].sort((a, b) => a.label.localeCompare(b.label, 'vi'))
    }
    merge('customer', customers.map((customer) => [customer?.name, customer?.phone].filter(Boolean).join(' - ')))
    const customerByLabel = new Map(customers.map(item => [[item.name, item.phone].filter(Boolean).join(' - '), item]))
    result.customer = result.customer.map(option => {
      const customer = customerByLabel.get(option.label)
      return { ...option, badge: customer ? customerTicketLabel(customer) || 'Còn 0 vé combo' : undefined }
    })
    merge('employee', employees.map(employee => employee?.name || employee?.employee_name || employee?.username))
    merge('service', services.map((service) => service?.name || service?.service))
    return result
  }, [customers, rows, services, employees])
  const draftValidity = useRef({})
  const [dateGeneration, setDateGeneration] = useState(0)
  const reportValidity = (field, valid) => {
    draftValidity.current[field] = valid
    onValidityChange?.(!Object.values(draftValidity.current).includes(false))
  }
  const presets = allowedPresets ? TOUR_DATE_PRESETS.filter(([id]) => allowedPresets.includes(id)) : TOUR_DATE_PRESETS
  const canCustom = presets.some(([id]) => id === 'custom')
  const change = patch => onChange({ ...value, ...patch })
  const choosePreset = (preset, date) => {
    if (!presets.some(([id]) => id === preset) || (date && !canCustom)) return
    draftValidity.current = {}; onValidityChange?.(true); setDateGeneration(current => current + 1)
    change({ preset, ...(date ? { date, date_from: date, date_to: date } : preset === 'custom' ? {} : { date: '', ...tourDateRange(preset, serverToday ? new Date(`${serverToday}T12:00:00+07:00`) : new Date()) }) })
  }
  return <UiToolbar data-ui-key="u-aee0d456f8e9" className="live-tour-filters" role="group" aria-label="Bộ lọc danh sách">
    <UiToolbar data-ui-key="u-6cab38b8ea72" className="live-tour-filters-row live-tour-filters-dates">
      <ReportDatePreset key={value.preset + value.date_from + value.date_to} className="live-tour-filters-preset" value={value.preset} presets={presets} allowDateSearch={canCustom} onChange={choosePreset}/>
      {canCustom && <><label><span>Từ ngày</span><VeraDateInput key={`from-${dateGeneration}`} onDraftValidity={valid => reportValidity('date_from', valid)} value={value.date_from} max={value.date_to || undefined} onChange={e => change({ date: '', date_from: e.target.value, preset: 'custom' })}/></label>
      <label><span>Đến ngày</span><VeraDateInput key={`to-${dateGeneration}`} onDraftValidity={valid => reportValidity('date_to', valid)} value={value.date_to} min={value.date_from || undefined} onChange={e => change({ date: '', date_to: e.target.value, preset: 'custom' })}/></label></>}
    </UiToolbar>
    <UiToolbar data-ui-key="u-f4dd81a665cc" className={`live-tour-filters-row live-tour-filters-search${showTotal || showTip ? ' live-tour-filters-five' : ''}${showDate ? ' live-tour-filters-date-search' : ''}`}>
      {showDate && canCustom && <label><span>Ngày</span><VeraDateInput key={`date-${dateGeneration}`} onDraftValidity={valid => reportValidity('date', valid)} clearable aria-label="Lọc ngày hóa đơn" value={value.date || ''} onChange={event => { if (!event.target.value) reportValidity('date', true); change({ date: event.target.value, date_from: event.target.value, date_to: event.target.value, preset: event.target.value ? 'custom' : presets.some(([id]) => id === 'all') ? 'all' : 'custom' }) }} /></label>}
      <LiveTourSearchSelect label="Số hóa đơn" placeholder="Nhập hoặc chọn số hóa đơn" options={options.bill_no} value={value.bill_no || ''} searchValue={value.bill_no || ''} onSearch={text => change({ bill_no: text })} onChange={text => change({ bill_no: text })} showAllOptions emptyLabel="Tất cả"/>
      <LiveTourSearchSelect label="Nhân viên" placeholder="Tìm tên nhân viên" options={options.employee} value={value.employee} searchValue={value.employee} onSearch={text => change({ employee: text })} onChange={text => change({ employee: text })} showAllOptions emptyLabel="Tất cả"/>
      <LiveTourSearchSelect label="Khách hàng" placeholder="Tìm tên hoặc số điện thoại" filterOption={(option, query) => { const [name, phone] = option.label.split(' - '); return customerMatches({ name, phone }, query) }} options={options.customer} value={value.customer} searchValue={value.customer} onSearch={text => change({ customer: text })} onChange={text => change({ customer: text })} showAllOptions emptyLabel="Tất cả"/>
      <LiveTourSearchSelect label="Dịch vụ" placeholder="Tìm dịch vụ" options={options.service} value={value.service} searchValue={value.service} onSearch={text => change({ service: text })} onChange={text => change({ service: text })} showAllOptions emptyLabel="Tất cả"/>
      {showTotal && <label><span>Tổng tiền (đ)</span><VeraMoneyInput aria-label="Lọc tổng tiền" placeholder="Tất cả số tiền" value={value.total_amount ?? ''} onChange={event => change({ total_amount: event.target.value })}/></label>}
      {showTip && <label><span>Số tiền TIP (đ)</span><VeraMoneyInput aria-label="Lọc số tiền TIP" placeholder="Tất cả số tiền" value={value.tip_amount ?? ''} onChange={event => change({ tip_amount: event.target.value })}/></label>}
    </UiToolbar>
    <UiToolbar data-ui-key="u-4f2eb3da8de7" className="live-tour-filters-actions report-date-buttons">
      {presets.map(([id, label]) => <button key={id} type="button" className={`secondary-button live-tour-filters-reset ${value.preset === id ? 'active' : ''}`} aria-pressed={value.preset === id} onClick={() => choosePreset(id)}>{label}</button>)}
    </UiToolbar>
  </UiToolbar>
}
