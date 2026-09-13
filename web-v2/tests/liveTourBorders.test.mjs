import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
const controls = fs.readFileSync(new URL('../src/pages/LiveTourControls.css', import.meta.url), 'utf8')
const shared = fs.readFileSync(new URL('../src/clear-borders.css', import.meta.url), 'utf8')

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
