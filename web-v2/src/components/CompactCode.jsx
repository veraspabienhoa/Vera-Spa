import { useState } from 'react'
import { displayCode } from '../lib/displayCode'
import './CompactCode.css'

export default function CompactCode({ value, label = 'Mã' }) {
  const [expanded, setExpanded] = useState(false)
  const full = String(value ?? '').trim()
  const compact = displayCode(value)
  if (!full || compact === full) return <span className="compact-code">{compact}</span>
  return <button type="button" className="compact-code compact-code-toggle" title={full}
    aria-label={`${expanded ? 'Thu gọn' : 'Xem đầy đủ'} ${label.toLocaleLowerCase('vi')}`}
    aria-expanded={expanded} onClick={event => { event.stopPropagation(); setExpanded(current => !current) }}>
    {expanded ? full : compact}
  </button>
}
