import './LiveTourFilters.css'
import { EMPTY_TOUR_FILTERS, TOUR_DATE_PRESETS, tourDateRange } from '../lib/liveTourFilters'

export default function LiveTourFilters({ value, onChange }) {
  const change = patch => onChange({ ...value, ...patch })
  return <div className="live-tour-filters" role="group" aria-label="Bộ lọc danh sách">
    <div className="live-tour-filters-row live-tour-filters-dates">
      <label className="live-tour-filters-preset"><span>Thời gian</span><select value={value.preset} onChange={e => change({ preset: e.target.value, ...tourDateRange(e.target.value) })}>{TOUR_DATE_PRESETS.map(([id, label]) => <option value={id} key={id}>{label}</option>)}</select></label>
      <label><span>Từ ngày</span><input type="date" value={value.date_from} max={value.date_to || undefined} onChange={e => change({ date_from: e.target.value, preset: 'custom' })}/></label>
      <label><span>Đến ngày</span><input type="date" value={value.date_to} min={value.date_from || undefined} onChange={e => change({ date_to: e.target.value, preset: 'custom' })}/></label>
    </div>
    <div className="live-tour-filters-row live-tour-filters-search">
      <label><span>Nhân viên</span><input type="search" placeholder="Tìm tên nhân viên" value={value.employee} onChange={e => change({ employee: e.target.value })}/></label>
      <label><span>Khách hàng</span><input type="search" placeholder="Tìm tên hoặc số điện thoại" value={value.customer} onChange={e => change({ customer: e.target.value })}/></label>
      <label><span>Dịch vụ</span><input type="search" placeholder="Tìm dịch vụ" value={value.service} onChange={e => change({ service: e.target.value })}/></label>
    </div>
    <div className="live-tour-filters-actions">
      <button type="button" className="secondary-button live-tour-filters-reset" onClick={() => onChange({ ...EMPTY_TOUR_FILTERS })}>Xóa bộ lọc</button>
    </div>
  </div>
}
