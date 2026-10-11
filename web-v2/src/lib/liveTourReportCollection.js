const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const records = value => Array.isArray(value) && value.every(record)
const scalar = value => value == null || ['string', 'number', 'boolean'].includes(typeof value)
const invoiceMetadataKeys = ['before', 'after', 'invoice', 'pending', 'payload']

export const REPORT_DATA_ERROR = 'Dữ liệu báo cáo trả về chưa hợp lệ. Hãy thử tải lại; nếu vẫn lỗi, gửi mã REPORT_DATA_INVALID để kiểm tra. Chưa thể hiển thị số liệu an toàn.'

export function hasTourRevenueSummary(summary) {
  return record(summary) && ['totalRevenue', 'serviceRevenue', 'tip'].every(key => Number.isFinite(summary[key]))
    && Number.isSafeInteger(summary.invoiceCount) && summary.invoiceCount >= 0
}

function renderableRow(row) {
  return record(row)
    && ['id', '_id', 'code', 'name', 'customer_id', 'employee_name', 'service', 'customer_name', 'customer_phone',
      'invoice_id', 'bill_no', 'effective_at', 'business_date', 'total', 'tip', 'revenue', 'amount'].every(key => scalar(row[key]))
    && validInvoiceMetadata(row)
    && (row.entries == null || (records(row.entries) && row.entries.every(entry => ['employee_name', 'service'].every(key => scalar(entry[key])))))
}

function validInvoiceMetadata(value, depth = 0) {
  if (value == null || typeof value !== 'object') return true
  // Match invoiceNumbers' nested sources, with a bounded malformed-data guard.
  if (depth > 20) return false
  if (Array.isArray(value)) return value.every(item => validInvoiceMetadata(item, depth + 1))
  return scalar(value.bill_no)
    && (value.bill_numbers == null || (Array.isArray(value.bill_numbers) && value.bill_numbers.every(scalar)))
    && invoiceMetadataKeys.every(key => validInvoiceMetadata(value[key], depth + 1))
}

export function validateTourReportCollection(value) {
  const data = value?.data
  // Collection rows are paged. Missing aggregates cannot be replaced with the
  // visible page's sum, zero, or a previous board's financial data.
  if (!record(value) || !Number.isSafeInteger(value.revision) || value.revision < 0
    || !Number.isSafeInteger(value.total) || value.total < 0
    || !Number.isInteger(value.page) || value.page < 1
    || !Number.isInteger(value.page_size) || value.page_size < 1 || value.page_size > 100
    || !Number.isSafeInteger(value.pages) || value.pages !== Math.max(1, Math.ceil(value.total / value.page_size))
    || !record(data) || !hasTourRevenueSummary(data.report_totals)
    || !Array.isArray(data.report_rows) || !data.report_rows.every(renderableRow)
    || data.report_rows.length > value.page_size || data.report_rows.length > value.total
    || !record(data.state) || !records(data.state.invoices) || !data.state.invoices.every(renderableRow)
    || !records(data.state.reports) || !data.state.reports.every(renderableRow)) {
    const error = new Error(REPORT_DATA_ERROR)
    // A malformed row must not prevent the same response's permission reduction
    // from closing copied receipts/dialogs. The loader applies this only while
    // the request is current, under its usual disposed-request guard.
    error.reportCapabilities = value?.capabilities || data?.capabilities
    throw error
  }
  return value
}
