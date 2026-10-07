import VeraDateInput from './VeraDateInput'

export default function DateSearchField({ value, onChange, label = 'Ngày', ariaLabel = 'Tìm kiếm ngày' }) {
  return <label className="date-search-field"><span>{label}</span><VeraDateInput aria-label={ariaLabel} value={value} onChange={event => onChange(event.target.value)} /></label>
}
