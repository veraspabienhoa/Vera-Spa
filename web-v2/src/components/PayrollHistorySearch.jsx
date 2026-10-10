import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { normalizeSearchText } from '../lib/searchText'
import TablePager from './TablePager'
import useTablePage from '../lib/useTablePage'
import './PayrollHistorySearch.css'

const normalize = value => normalizeSearchText(value).replace(/\b0+(\d+)\b/g, '$1')

export default function PayrollHistorySearch({ items, onView, onEdit, disabled = false }) {
  const [query, setQuery] = useState('')
  const results = useMemo(() => {
    const terms = normalize(query).split(' ').filter(Boolean)
    if (!terms.length) return []
    return items.filter(item => { const text = normalize([item.label, item.searchText].join(' ')); return terms.every(term => text.includes(term)) })
  }, [items, query])
  const page = useTablePage(results, query, 50)
  return <div className="panel payroll-history-search">
    <label><Search size={17} /> Tìm bảng lương đã lưu<input type="search" value={query} disabled={disabled} onChange={event => setQuery(event.target.value)} placeholder="Nhập kỳ, tháng, năm hoặc ngày lưu…" /></label>
    {query.trim() && <div className="payroll-history-search-results" role="region" aria-label="Kết quả tìm bảng lương">
      <p role="status">{results.length} bảng lương phù hợp</p>
      <TablePager pagination={page} label="kết quả tìm bảng lương" />
      {page.rows.map(item => <article key={item.id}><div><strong>{item.label}</strong><small>{item.description}</small></div><div className="list-actions">
        {onView && <button type="button" className="secondary-button" disabled={disabled} onClick={() => onView(item.id)}>Xem chi tiết</button>}
        {onEdit && <button type="button" className="primary-button" disabled={disabled} onClick={() => onEdit(item.id)}>Sửa bảng lương</button>}
      </div></article>)}
    </div>}
  </div>
}
