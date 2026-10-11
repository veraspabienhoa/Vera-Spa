import test from 'node:test'
import assert from 'node:assert/strict'
import { validateTourReportCollection, hasTourRevenueSummary } from '../src/lib/liveTourReportCollection.js'

const summary = { totalRevenue: 100, serviceRevenue: 90, tip: 10, invoiceCount: 1 }
const response = () => ({ revision: 1, page: 1, page_size: 50, total: 500, pages: 10,
  data: { report_totals: { ...summary }, report_rows: [{ id: 'r1' }], state: { reports: [{ id: 'r1' }], invoices: [] } } })

test('collection contract rejects missing or malformed full-filter financial aggregates without coercion', () => {
  for (const totals of [undefined, null, {}, [], { ...summary, totalRevenue: null }, { ...summary, tip: '10' },
    { ...summary, serviceRevenue: Infinity }, { ...summary, invoiceCount: -1 }, { ...summary, invoiceCount: 1.5 }]) {
    const value = response(); value.data.report_totals = totals
    assert.equal(hasTourRevenueSummary(totals), false)
    assert.throws(() => validateTourReportCollection(value), /REPORT_DATA_INVALID/)
  }
  assert.equal(validateTourReportCollection(response()).data.report_totals.totalRevenue, 100)
})

test('collection contract rejects unsafe pagination, records and recursively nested invoice-number sources', () => {
  const mutations = [
    value => { value.total = {} }, value => { value.pages = {} }, value => { value.revision = {} },
    value => { value.page_size = 0 }, value => { value.pages = 1 },
    value => { value.data.report_rows = [null] }, value => { value.data.state.invoices = [null] },
    value => { value.data.state.reports = [{ service: {} }] }, value => { value.data.report_rows[0].entries = 'broken' },
    ...['before', 'after', 'invoice', 'pending', 'payload'].map(key => value => { value.data.report_rows[0][key] = [{ invoice: { bill_numbers: {} } }] }),
    value => { value.data.report_rows[0].payload = value.data.report_rows[0] },
  ]
  for (const mutate of mutations) {
    const value = response(); mutate(value)
    assert.throws(() => validateTourReportCollection(value), /REPORT_DATA_INVALID/)
  }
})

test('invalid data preserves current response permission metadata for fail-closed reconciliation', () => {
  const value = response()
  value.data.report_totals = {}
  value.capabilities = { reports_view: false, date_filters: { version: 1, sections: { reports: [] } } }
  assert.throws(() => validateTourReportCollection(value), error => error.reportCapabilities === value.capabilities)
})
