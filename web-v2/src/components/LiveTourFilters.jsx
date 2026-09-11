import './LiveTourFilters.css'
import { useMemo } from 'react'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import { EMPTY_TOUR_FILTERS, TOUR_DATE_PRESETS, tourDateRange, tourFilterOptions } from '../lib/liveTourFilters'

export default function LiveTourFilters({ value, onChange, rows }) {
  const options = useMemo(() => tourFilterOptions(rows), [rows])
  const change = patch => onChange({ ...value, ...patch })
  return <div className="live-tour-filters" role="group" aria-label="Bộ lọc danh sách">
    <div className="live-tour-filters-row live-tour-filters-dates">
      <label className="live-tour-filters-preset"><span>Thời gian</span><select value={value.preset} onChange={e => change({ preset: e.target.value, ...tourDateRange(e.target.value) })}>{TOUR_DATE_PRESETS.map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>
      <label><span>Từ ngày</span><input type="date" value={value.date_from} max={value.date_to || undefined} onChange={e => change({ date_from: e.target.value, preset: 'custom' })}/></label>
      <label><span>Đến ngày</span><input type="date" value={value.date_to} min={value.date_from || undefined} onChange={e => change({ date_to: e.target.value, preset: 'custom' })}/></label>
    </div>
    <div className="live-tour-filters-row live-tour-filters-search">
      <LiveTourSearchSelect label="Nhân viên" placeholder="Tìm tên nhân viên" options={options.employee} value={value.employee} searchValue={value.employee} onSearch={text => change({ employee: text })} onChange={text => change({ employee: text })} showAllOptions emptyLabel="Tất cả"/>
      <LiveTourSearchSelect label="Khách hàng" placeholder="Tìm tên hoặc số điện thoại" options={options.customer} value={value.customer} searchValue={value.customer} onSearch={text => change({ customer: text })} onChange={text => change({ customer: text })} showAllOptions emptyLabel="Tất cả"/>
      <LiveTourSearchSelect label="Dịch vụ" placeholder="Tìm dịch vụ" options={options.service} value={value.service} searchValue={value.service} onSearch={text => change({ service: text })} onChange={text => change({ service: text })} showAllOptions emptyLabel="Tất cả"/>
    </div>
    <div className="live-tour-filters-actions">
      <button type="button" className="secondary-button live-tour-filters-reset" onClick={() => onChange({ ...EMPTY_TOUR_FILTERS })}>Xóa bộ lọc</button>
    </div>
  </div>
}
