import { useState } from 'react'

// Bound DOM work, while totals, filters and exports keep the full result set.
export default function useTablePage(rows, scope, pageSize = 100) {
  const [position, setPosition] = useState({ scope, page: 1 })
  const pages = Math.max(1, Math.ceil(rows.length / pageSize))
  const page = position.scope === scope ? Math.min(position.page, pages) : 1
  if (position.scope !== scope || position.page !== page) setPosition({ scope, page })
  return { page, pages, total: rows.length, pageSize,
    rows: rows.slice((page - 1) * pageSize, page * pageSize),
    setPage: value => setPosition({ scope, page: Math.max(1, Math.min(value, pages)) }),
  }
}
