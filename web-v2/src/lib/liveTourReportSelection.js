import { filterTourRows } from './liveTourFilters.js'

export const isComboReport = row => row.combo_sale || row.combo_units || /combo/i.test(row.service || '')

// Evaluate only the visible dataset. A receipt/modal render must not rescan it.
export function selectReportRows(data, tab, filters, performanceTiming = 'all') {
  if (tab === 'history') return []
  const source = tab === 'performance' ? data.performance || [] : tab === 'invoices' ? data.invoices : data.reports
  const filtered = filterTourRows(source, filters, tab !== 'performance')
  if (tab === 'tip') return filtered.filter(row => Number(row.tip || 0) > 0)
  if (tab === 'combos') return filtered.filter(isComboReport)
  if (tab !== 'performance' || performanceTiming === 'all') return filtered
  return filtered.filter(row => {
    const delta = Number(row.completion_delta_minutes)
    return performanceTiming === 'early' ? delta < 0 : performanceTiming === 'late' ? delta > 0 : delta === 0
  })
}
