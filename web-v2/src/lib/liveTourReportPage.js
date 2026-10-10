import { filterTourRows } from './liveTourFilters.js'
import { selectReportRows } from './liveTourReportSelection.js'
import { reportInvoiceMetrics } from './liveTourReportMetrics.js'
import { summarizeTourRevenue } from './liveTourRevenue.js'
import { summarizeEmployeeRevenue } from './liveTourEmployeeRevenue.js'

// The page and exports share filters, never a page-sized financial aggregate.
export const REPORT_PAGE_SIZE = 100
export const EMPTY_REPORT_PAGE = {
  rows: [], invoices: [], employee_totals: [], capabilities: {}, payment_settings: {}, revision: 0,
  total: 0, pages: 1, page: 1, page_size: REPORT_PAGE_SIZE,
  summary: { totalRevenue: 0, serviceRevenue: 0, tip: 0, invoiceCount: 0,
    zeroInvoices: 0, discount: 0, pendingInvoiceCount: 0, tipEmployeeCount: 0 },
}

export function reportReadQuery(filters, tab, performanceTiming, page = 1) {
  const query = { tab, page, page_size: REPORT_PAGE_SIZE }
  for (const key of ['preset', 'date', 'date_from', 'date_to', 'employee', 'customer', 'service', 'bill_no']) {
    if (filters[key] != null && filters[key] !== '') query[key] = filters[key]
  }
  if (tab === 'revenue' && filters.total_amount != null && filters.total_amount !== '') query.total_amount = filters.total_amount
  if (tab === 'tip' && filters.tip_amount != null && filters.tip_amount !== '') query.tip_amount = filters.tip_amount
  if (tab === 'performance') query.performance_timing = performanceTiming
  return query
}

export function validateReportPage(result) {
  // New-contract failures must never be treated as legacy responses or yield
  // page-local financial totals. Only the exact old endpoint DTO is adaptable.
  if (!Number.isSafeInteger(result?.revision) || result.revision < 0
    || !record(result?.capabilities) || !record(result?.payment_settings)
    || !Array.isArray(result?.rows) || !Array.isArray(result?.invoices)
    || !Array.isArray(result?.employee_totals) || !record(result?.summary)
    || result.rows.some(row => !record(row)) || result.invoices.some(row => !record(row))
    || result.employee_totals.some(row => !record(row))
    || !Number.isInteger(result.total) || result.total < 0
    || !Number.isInteger(result.page_size) || result.page_size < 1 || result.page_size > REPORT_PAGE_SIZE
    || !Number.isInteger(result.page) || result.page < 1
    || !Number.isInteger(result.pages) || result.pages < 1
    || result.rows.length > result.page_size || result.rows.length > result.total || result.invoices.length > result.page_size
    || result.pages !== Math.max(1, Math.ceil(result.total / result.page_size))
    || ['totalRevenue', 'serviceRevenue', 'tip', 'invoiceCount', 'zeroInvoices', 'discount', 'tipEmployeeCount']
      .some(key => !Number.isFinite(result.summary[key]))) {
    throw new Error('Máy chủ chưa trả về báo cáo phân trang hợp lệ. Vui lòng tải lại sau khi cập nhật hệ thống.')
  }
  return result
}

const LEGACY_KEYS = ['revision', 'invoices', 'reports', 'pending', 'performance', 'capabilities', 'payment_settings']
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)

// One-release bridge: frontend deployment precedes the separately deployed API.
// Accept only the actual legacy DTO, never errors or malformed paged responses.
export function isLegacyReportResponse(value) {
  return record(value) && Object.keys(value).length === LEGACY_KEYS.length
    && LEGACY_KEYS.every(key => Object.hasOwn(value, key))
    && Number.isSafeInteger(value.revision) && value.revision >= 0
    && ['invoices', 'reports', 'pending', 'performance'].every(key => Array.isArray(value[key]) && value[key].every(record))
    && record(value.capabilities) && Object.values(value.capabilities).every(flag => typeof flag === 'boolean')
    && record(value.payment_settings)
}

export function adaptReportResponse(response, query) {
  if (!isLegacyReportResponse(response)) return { ...validateReportPage(response), read_mode: 'paged' }
  const allRows = selectReportRows(response, query.tab, query, query.performance_timing || 'all')
  const invoiceById = new Map(response.invoices.map(invoice => [invoice.id, invoice]))
  const rows = allRows.slice((query.page - 1) * query.page_size, query.page * query.page_size)
  const invoiceIds = new Set(rows.map(row => query.tab === 'invoices' ? row.id : row.invoice_id).filter(Boolean))
  const summary = {
    ...summarizeTourRevenue(allRows), ...reportInvoiceMetrics(allRows, invoiceById),
    invoiceCount: new Set(allRows.map(row => String(row?.invoice_id || row?.bill_no || '').trim()).filter(Boolean)).size,
    tipEmployeeCount: new Set(allRows.map(row => row.employee_id || row.employee_name)).size,
    pendingInvoiceCount: response.capabilities.pending_view && response.capabilities.invoice_view
      ? filterTourRows(response.pending, query).length : null,
  }
  return validateReportPage({
    revision: response.revision, capabilities: response.capabilities, payment_settings: response.payment_settings,
    rows, invoices: response.invoices.filter(invoice => invoiceIds.has(invoice.id)), summary,
    employee_totals: query.tab === 'employee' ? summarizeEmployeeRevenue(allRows) : [],
    total: allRows.length, page: query.page, page_size: query.page_size,
    pages: Math.max(1, Math.ceil(allRows.length / query.page_size)), read_mode: 'legacy',
  })
}
