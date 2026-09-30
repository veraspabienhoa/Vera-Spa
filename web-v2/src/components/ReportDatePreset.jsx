import { useState } from 'react'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import { formatVeraDate, parseVeraDate } from '../lib/veraDate'
import { searchTextMatches } from '../lib/searchText'

function searchDate(value) {
  const raw = String(value || '').trim()
  if (/^\d{8}$/.test(raw)) return parseVeraDate(`${raw.slice(0, 2)}-${raw.slice(2, 4)}-${raw.slice(4)}`)
  if (/^\d{2}[-/]\d{2}[-/]\d{4}$/.test(raw)) return parseVeraDate(raw.replaceAll('/', '-'))
  return ''
}

// Selecting a date applies one day. Incomplete/invalid drafts never change the
// active filter. Keep the shared combobox's keyboard, portal and Clear behavior.
export default function ReportDatePreset({ value, presets, onChange, label = 'Thời gian', className = '' }) {
  const [draft, setDraft] = useState(null)
  const selectedLabel = presets.find(([id]) => id === value)?.[1] || ''
  const query = draft ?? selectedLabel
  const date = searchDate(query)
  const options = presets.map(([id, title]) => ({ value: id, label: title }))
  if (date) options.push({ value: `date:${date}`, label: formatVeraDate(date), detail: 'Xem dữ liệu ngày này' })
  return <LiveTourSearchSelect className={`report-date-preset ${className}`} label={label}
    required value={value} options={options} searchValue={query}
    placeholder="Gõ thời gian hoặc ngày ddmmyyyy" onSearch={setDraft}
    filterOption={(option, text) => draft === null || option.value === `date:${date}` || searchTextMatches(option.label, text)}
    onChange={next => {
      setDraft(null)
      if (next.startsWith('date:')) onChange('custom', next.slice(5))
      else onChange(next || 'all')
    }}/>
}
