import './LiveTourFilters.css'
import { EMPTY_TOUR_FILTERS, TOUR_DATE_PRESETS, tourDateRange } from '../lib/liveTourFilters'
export default function LiveTourFilters({ value, onChange }) {
  const change = patch => onChange({ ...value, ...patch })
  return <div className="live-tour-export-filters" aria-label="Bộ lọc danh sách">
    <label>Thời gian<select value={value.preset} onChange={e => change({ preset: e.target.value, ...tourDateRange(e.target.value) })}>{TOUR_DATE_PRESETS.map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>
    <label>Từ ngày<input type="date" value={value.date_from} max={value.date_to || undefined} onChange={e => change({ date_from: e.target.value, preset: 'custom' })}/></label>
    <label>Đến ngày<input type="date" value={value.date_to} min={value.date_from || undefined} onChange={e => change({ date_to: e.target.value, preset: 'custom' })}/></label>
    <label>Nhân viên<input type="search" value={value.employee} onChange={e => change({ employee: e.target.value })}/></label>
    <label>Khách hàng<input type="search" value={value.customer} onChange={e => change({ customer: e.target.value })}/></label>
    <label>Dịch vụ<input type="search" value={value.service} onChange={e => change({ service: e.target.value })}/></label>
    <button type="button" className="secondary-button" onClick={() => onChange({ ...EMPTY_TOUR_FILTERS })}>Xóa bộ lọc</button>
  </div>
}
