import { useState } from 'react'

// Keep variable-length lists inside a single-screen form without truncation.
export default function LiveTourPageItems({ items, children, pageSize = 2, label, className = '' }) {
  const [requestedPage, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(items.length / pageSize))
  const page = Math.min(requestedPage, pages - 1)
  const start = page * pageSize
  return <div className={`tour-page-items ${className}`}>
    <div className="tour-page-items-content">{items.slice(start, start + pageSize).map((item, index) => children(item, start + index))}</div>
    {pages > 1 && <div className="tour-list-pages" aria-label={label}>
      <button type="button" disabled={!page} onClick={() => setPage(page - 1)} aria-label={`${label} trước`}>‹</button>
      <span aria-live="polite">{start + 1}–{Math.min(start + pageSize, items.length)} / {items.length}</span>
      <button type="button" disabled={page >= pages - 1} onClick={() => setPage(page + 1)} aria-label={`${label} tiếp`}>›</button>
    </div>}
  </div>
}
