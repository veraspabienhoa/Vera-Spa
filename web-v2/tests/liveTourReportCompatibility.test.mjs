import assert from 'node:assert/strict'
import test from 'node:test'
import { adaptReportResponse, isLegacyReportResponse, reportReadQuery, EMPTY_REPORT_PAGE } from '../src/lib/liveTourReportPage.js'
import { selectReportRows } from '../src/lib/liveTourReportSelection.js'
import { filterTourRows } from '../src/lib/liveTourFilters.js'
import { reportInvoiceMetrics } from '../src/lib/liveTourReportMetrics.js'
import { summarizeTourRevenue } from '../src/lib/liveTourRevenue.js'
import { summarizeEmployeeRevenue } from '../src/lib/liveTourEmployeeRevenue.js'

const legacy = () => ({ revision: 92, capabilities: { export: true, paid_invoice_view: true, pending_view: true, invoice_view: true }, payment_settings: {},
  invoices: [{ id: 'paid', bill_no: 'BILL-1', effective_at: '2026-10-09T01:00:00+07:00', total: 110, tip: 10, discount: 5,
    entries: [{ employee_name: 'Ánh', service: 'Body' }, { employee_name: 'Bình', service: 'Combo' }] },
  { id: 'zero', total: 0, discount: 100 }],
  reports: [
    { id: 'r1', invoice_id: 'paid', bill_no: 'BILL-1', effective_at: '2026-10-08T18:00:00Z', total: 60, tip: 10, employee_name: 'Ánh', service: 'Body', request: 'YC' },
    { id: 'r2', invoice_id: 'paid', bill_no: 'BILL-1', effective_at: '2026-10-08T18:00:00Z', total: 50, tip: 0, employee_name: 'Bình', service: 'Combo', combo_units: 1 },
    { id: 'r0', invoice_id: 'zero', bill_no: 'BILL-0', business_date: '9/10/2026', total: 0, tip: 0, employee_name: 'Ánh', service: 'Body' },
    { id: 'excluded-day', bill_no: 'OLD', effective_at: '2026-10-08T16:59:00Z', total: 999, tip: 100, employee_name: 'Ánh', service: 'Body' },
  ],
  pending: [{ id: 'p1', booked_at: '2026-10-09T12:00:00+07:00', employee_name: 'Ánh', service: 'Body', total: 60, tip: 10 }],
  performance: [{ id: 's1', booked_at: '2026-10-08T18:00:00Z', employee_name: 'Ánh', service: 'Body', completion_delta_minutes: -2 },
    { id: 's2', booked_at: '2026-10-09T10:00:00+07:00', employee_name: 'Bình', service: 'Combo', completion_delta_minutes: 2 }],
})

for (const tab of ['revenue', 'employee', 'tip', 'combos', 'performance', 'invoices']) {
  test(`legacy ${tab} adapter matches the established full-filter helper semantics`, () => {
    const original = legacy()
    const query = reportReadQuery({ date: '2026-10-09', date_from: '2026-10-09', date_to: '2026-10-09' }, tab, 'early')
    const expectedRows = selectReportRows(original, tab, query, 'early')
    const actual = adaptReportResponse(original, query)
    assert.equal(actual.read_mode, 'legacy')
    assert.equal(actual.revision, 92)
    assert.deepEqual(actual.rows, expectedRows)
    assert.equal(actual.total, expectedRows.length)
    const metric = reportInvoiceMetrics(expectedRows, new Map(original.invoices.map(invoice => [invoice.id, invoice])))
    assert.deepEqual({ zeroInvoices: actual.summary.zeroInvoices, discount: actual.summary.discount }, metric)
    for (const [key, value] of Object.entries(summarizeTourRevenue(expectedRows))) assert.equal(actual.summary[key], value)
    assert.equal(actual.summary.pendingInvoiceCount, filterTourRows(original.pending, query).length)
    assert.deepEqual(actual.employee_totals, tab === 'employee' ? summarizeEmployeeRevenue(expectedRows) : [])
    if (tab === 'revenue') {
      assert.equal(actual.summary.totalRevenue, 110)
      assert.equal(actual.summary.invoiceCount, 2)
      assert.equal(actual.summary.zeroInvoices, 1)
      assert.equal(actual.summary.discount, 105, 'discount counted once per whole invoice')
      assert.ok(actual.rows.some(row => row.id === 'r0'), 'legacy slash date remains matched')
      assert.ok(!actual.rows.some(row => row.id === 'excluded-day'), 'UTC timestamp is compared on the Vietnam calendar')
    }
  })
}

test('legacy page slicing keeps whole-filter totals and only linked permitted receipt snapshots', () => {
  const response = legacy()
  response.reports = Array.from({ length: 251 }, (_, i) => ({ id: `r${i}`, invoice_id: `i${i}`, bill_no: `BILL-${i}`, total: 110, tip: 10, employee_name: 'Ánh' }))
  response.invoices = response.reports.map(row => ({ ...row, id: row.invoice_id, revision: 7, entries: [{ service: 'Body', employee_name: 'Ánh', price: 100 }] }))
  const result = adaptReportResponse(response, reportReadQuery({}, 'revenue', 'all', 2))
  assert.equal(result.total, 251)
  assert.equal(result.rows.length, 100)
  assert.equal(result.rows[0].id, 'r100')
  assert.equal(result.invoices.length, 100)
  assert.equal(result.invoices[0], response.invoices[100])
  assert.equal(result.revision, 92)
  assert.equal(result.summary.totalRevenue, 251 * 110)
  assert.equal(result.summary.invoiceCount, 251)
  assert.deepEqual(result.capabilities, response.capabilities)
  const restricted = adaptReportResponse({ ...response, invoices: [], capabilities: { pending_view: false, invoice_view: true, paid_invoice_view: false } }, reportReadQuery({}, 'revenue', 'all', 2))
  assert.deepEqual(restricted.invoices, [])
  assert.equal(restricted.summary.pendingInvoiceCount, null)
})

test('legacy adapter applies zero-money and text filters before totals and slicing', () => {
  const query = reportReadQuery({ total_amount: 0, employee: 'Ánh', service: 'Body', bill_no: 'BILL-0' }, 'revenue', 'all')
  const result = adaptReportResponse(legacy(), query)
  assert.equal(result.total, 1)
  assert.equal(result.rows[0].id, 'r0')
  assert.equal(result.summary.zeroInvoices, 1)
  assert.equal(result.summary.discount, 100)
  assert.equal(result.summary.pendingInvoiceCount, 0)
})

test('only the exact successful legacy DTO is adaptable; malformed bounded DTOs and errors never fallback', () => {
  const query = reportReadQuery({}, 'revenue', 'all')
  const valid = legacy()
  assert.equal(isLegacyReportResponse(valid), true)
  const { pending: _pending, ...missing } = valid
  const invalid = [null, {}, missing, { ...valid, revision: '92' }, { ...valid, revision: -1 },
    { ...valid, reports: null }, { ...valid, reports: [null] }, { ...valid, invoices: ['wrong'] },
    { ...valid, capabilities: { export: 'true' } }, { ...valid, payment_settings: [] },
    { ...valid, error: 'upstream failure' }, { ...valid, rows: [], summary: {} },
    { ...EMPTY_REPORT_PAGE, rows: [{}], total: 1000, pages: 10, page_size: 1000 },
  ]
  for (const response of invalid) {
    assert.equal(isLegacyReportResponse(response), false)
    assert.throws(() => adaptReportResponse(response, query), /phân trang/)
  }
  assert.equal(adaptReportResponse(EMPTY_REPORT_PAGE, query).read_mode, 'paged')
})
