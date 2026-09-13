import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const source = fs.readFileSync(new URL('../src/pages/SpaManagementPage.jsx', import.meta.url), 'utf8')
const history = source.slice(source.indexOf('function CustomerHistory('), source.indexOf('export default function'))

test('history export uses selected customer and existing authenticated Excel download', () => {
  assert.match(history, /exportLiveTourExcel\('customer_detail', \{ customer_id: value.customer.id \}\)/)
  assert.match(history, /Xuất Excel mua \/ sử dụng combo/)
  assert.match(source, /canExport=\{data\?\.can_export\}/)
})

test('history export fails closed and prevents concurrent downloads', () => {
  for (const grant of ['customers_view', 'invoice_view', 'paid_invoice_view', 'pending_view', 'reports_view']) {
    assert.ok(history.includes(`'${grant}'`))
  }
  assert.match(history, /canExport === true/)
  assert.match(history, /value.capabilities\?\.\[key\] === true/)
  assert.match(history, /if \(!allowed \|\| !value.customer\?\.id \|\| exportRunning.current\) return/)
  assert.match(history, /finally \{\s*exportRunning.current = false\s*setExporting\(false\)/)
  assert.match(history, /role="alert"/)
})
