// Run against the pre-change helper bundled with esbuild, using identical rows.
// node scripts/benchmarkReportFilters.mjs /tmp/vera-report-filters-before.mjs
import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import { selectReportRows } from '../src/lib/liveTourReportSelection.js'
const baseline = await import(pathToFileURL(process.argv[2]))
const filters = { date_from: '2026-09-01', date_to: '2026-09-30' }
const results = []
for (const count of [100, 1000, 3000]) {
  const reports = Array.from({ length: count }, (_, i) => ({ id: `r${i}`, invoice_id: `i${i}`,
    effective_at: `2026-09-${String(1 + i % 28).padStart(2, '0')}T12:00:00+07:00`,
    employee_name: 'Mỹ Duyên', service: 'Body 90', total: 300000, tip: 0 }))
  const data = { reports, invoices: reports.map(row => ({ ...row, entries: [{ employee_name: row.employee_name, service: row.service }] })), performance: reports }
  const before = () => {
    baseline.filterTourRows(data.invoices, filters, true)
    const rows = baseline.filterTourRows(data.reports, filters, true)
    baseline.filterTourRows(data.performance, filters)
    return rows.filter(() => true) // Original revenue tab's final projection.
  }
  const after = () => selectReportRows(data, 'revenue', filters)
  assert.deepEqual(after(), before())
  const timed = fn => { const start = performance.now(); fn(); return performance.now() - start }
  const firstMeasured = { before: timed(before), after: timed(after) }
  const a = [], b = []
  for (let i = 0; i < 20; i++) {
    if (i % 2) { b.push(timed(after)); a.push(timed(before)) }
    else { a.push(timed(before)); b.push(timed(after)) }
  }
  const percentiles = values => {
    values.sort((a, b) => a - b)
    return { p50_ms: +values[9].toFixed(3), p95_ms: +values[18].toFixed(3) }
  }
  results.push({ rows_per_collection: count, samples: 20, concurrent_users: 1,
    first_measured_ms: firstMeasured, before: percentiles(a), after: percentiles(b), errors: 0,
    http_requests_before_after: [0, 0], sql_before_after: [0, 0],
    rows_scanned_before_after: [count * 3, count],
    response_bytes_before_after: [0, 0] })
}
console.log(JSON.stringify({ environment: `Node ${process.version}, synthetic data; filter CPU only, excludes DOM/network/VPS`, results }, null, 2))
