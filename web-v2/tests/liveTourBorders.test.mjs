import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
const controls = fs.readFileSync(new URL('../src/pages/LiveTourControls.css', import.meta.url), 'utf8')
const shared = fs.readFileSync(new URL('../src/clear-borders.css', import.meta.url), 'utf8')
const serviceActions = fs.readFileSync(new URL('../src/components/LiveTourServiceActions.css', import.meta.url), 'utf8')
const transactionDialog = fs.readFileSync(new URL('../src/components/LiveTourTransactionDialog.css', import.meta.url), 'utf8')
const page = fs.readFileSync(new URL('../src/pages/LiveTourPage.jsx', import.meta.url), 'utf8')

test('Live Tour removes body grid only and preserves outer frame and header borders', () => {
  const exception = shared.slice(shared.indexOf('/* Live Tour exception:'))
  assert.match(exception, /body \.live-tour-page \.tour-table table\s*\{\s*border: 2px solid #264f3c !important;/)
  assert.match(exception, /tbody tr > :is\(td, th\)\s*\{\s*border: 0 !important;/)
  assert.match(exception, /thead :is\(th, td\)\s*\{\s*border: 2px solid #264f3c !important;/)
  assert.doesNotMatch(exception, /background\s*:|color\s*:|outline\s*:|box-shadow\s*:/)
})

test('Live Tour table name and inline appointment have no border while quick input stays bordered', () => {
  const exception = controls.match(/\.live-tour-page \.tour-table \.tour-col-employee > \.text-button,[\s\S]*?\n\}/)?.[0] || ''
  assert.match(exception, /\.tour-col-appointment \.live-tour-appointment-editor:not\(\.quick\) input/)
  assert.match(exception, /border:\s*0\s*!important/)
  assert.match(exception, /box-shadow:\s*none\s*!important/)
  assert.match(controls, /\.tour-col-employee > \.text-button:focus-visible,[\s\S]*?outline:\s*2px solid/)
  assert.match(controls, /\.live-tour-appointment-editor\.quick input\{border-color:/)
  assert.match(shared, /body :is\(th, td,[\s\S]*?border:\s*2px solid var\(--table-border\)\s*!important/)
})

test('Live Tour reallocates compact column space equally to appointment and status', () => {
  assert.match(controls, /\.tour-col-request\{width:27px;min-width:27px;max-width:27px\}/)
  assert.match(controls, /\.tour-col-remaining\{width:29px;min-width:29px;max-width:29px\}/)
  assert.match(controls, /\.tour-col-room\{width:43px;min-width:43px;max-width:43px\}/)
  assert.match(controls, /\.tour-col-status\s*\{[\s\S]*?width:\s*153\.5px;[\s\S]*?min-width:\s*153\.5px;[\s\S]*?max-width:\s*153\.5px;/)
  assert.match(controls, /\.tour-col-appointment\{width:153\.5px;min-width:153\.5px;max-width:153\.5px;/)
  assert.match(controls, /\.tour-col-status,\s*\n\s*\.live-tour-page \.tour-table \.tour-col-appointment\{width:25\.75%\}/)
})

test('Live Tour keeps the desktop action column compact without changing the mobile fit-content layout', () => {
  assert.match(serviceActions, /\.live-tour-actions-col\{width:90px;min-width:90px;max-width:90px\}/)
  assert.match(controls, /\.tour-table \.live-tour-actions-col\{width:1%!important;min-width:max-content!important;/)
})

test('Live Tour keeps ten metrics on one bounded row and enlarges combo approval buttons', () => {
  const labels = [...page.matchAll(/key: '[^']+', label: '([^']+)'/g)].map(([, label]) => label)
  assert.deepEqual(labels.slice(0, 10), ['Tất cả', 'Có thể lên tua', 'Đang rảnh', 'Sắp xong', 'Đang chờ', 'Thực hiện', 'Số nhân viên', 'Nghỉ phép', 'Đi làm', 'Nghỉ giữa Ca'])
  assert.match(page, /tour-metrics\{grid-template-columns:repeat\(10,minmax\(0,1fr\)\)/)
  assert.match(controls, /tour-metrics\{grid-template-columns:repeat\(10,minmax\(0,1fr\)\)!important/)
  assert.match(page, /className="secondary-button live-tour-combo-approval-button"/)
  assert.match(page, /live-tour-combo-approval-button\{min-height:28\.8px\}/)
  assert.match(page, /live-tour-combo-approvals \.live-tour-card-actions button\{min-height:32\.4px\}/)
})

test('mobile payment dialogs scroll the form with touch momentum inside the visual viewport', () => {
  assert.match(transactionDialog, /\.tour-payment-dialog>form\{[^}]*flex:1 1 auto;[^}]*min-height:0;[^}]*overflow-y:auto;/)
  assert.match(transactionDialog, /\.tour-payment-dialog>form\{[^}]*-webkit-overflow-scrolling:touch;[^}]*touch-action:pan-y;/)
})
