import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import { JSDOM, VirtualConsole } from 'jsdom'
const controls = fs.readFileSync(new URL('../src/pages/LiveTourControls.css', import.meta.url), 'utf8')
const shared = fs.readFileSync(new URL('../src/clear-borders.css', import.meta.url), 'utf8')
const serviceActions = fs.readFileSync(new URL('../src/components/LiveTourServiceActions.css', import.meta.url), 'utf8')
const transactionDialog = fs.readFileSync(new URL('../src/components/LiveTourTransactionDialog.css', import.meta.url), 'utf8')
const page = fs.readFileSync(new URL('../src/pages/LiveTourPage.jsx', import.meta.url), 'utf8')

const normalizeSelector = selector => selector.replace(/\s+/g, ' ').trim()

function cssRules(source) {
  const virtualConsole = new VirtualConsole()
  virtualConsole.on('jsdomError', error => { throw error })
  const dom = new JSDOM('', { virtualConsole })
  try {
    const style = dom.window.document.createElement('style')
    style.textContent = source
    dom.window.document.head.append(style)
    assert.ok(style.sheet, 'the stylesheet must parse successfully')
    const rules = []
    const visit = (children, atRules = []) => {
      for (const rule of children) {
        if (rule.selectorText) {
          rules.push({
            selector: normalizeSelector(rule.selectorText),
            atRules,
            declarations: Array.from(rule.style, property => [
              property, rule.style.getPropertyValue(property), rule.style.getPropertyPriority(property),
            ]),
          })
        } else if (rule.cssRules) {
          visit(rule.cssRules, [...atRules, rule.cssText.split('{', 1)[0].trim()])
        }
      }
    }
    visit(style.sheet.cssRules)
    return rules
  } finally {
    dom.window.close()
  }
}

function assertLiveTourBorderContract(source) {
  const rules = cssRules(source)
  const borderRule = (selector, value, atRules = [], property = 'border') => ({
    selector: normalizeSelector(selector), atRules, declarations: [[property, value, 'important']],
  })
  // Inspect every matching rule, regardless of comments or position. Empty
  // atRules proves the exception applies on desktop, mobile and print. These
  // overrides may only change borders, preserving status, selection and focus.
  assert.deepEqual(rules.filter(rule => /\.tour-(?:table|row-before-shift)(?![\w-])/.test(rule.selector)), [
    borderRule('body .tour-table tr.tour-row-before-shift td.tour-col-employee', '3px solid #087bbd', ['@media screen'], 'border-left'),
    borderRule('body .live-tour-page .tour-table table', '2px solid #264f3c'),
    borderRule(`body .live-tour-page .tour-table tbody,
      body .live-tour-page .tour-table tbody tr,
      body .live-tour-page .tour-table tr.tour-row-before-shift td.tour-col-employee,
      body .live-tour-page .tour-table tbody tr > :is(td, th)`, '0'),
    borderRule('body .live-tour-page .tour-table thead :is(th, td)', '2px solid #264f3c'),
  ], 'Live Tour border rules must remain scoped, border-only and ordered after the legacy before-shift border')

  // The exception must not remove the common grids used by other tables.
  for (const expected of [
    borderRule("body :is(th, td, [role='columnheader'], [role='rowheader'], [role='gridcell'])", '2px solid var(--table-border)', ['@media screen']),
    borderRule('body :is(table, th, td):not(.tour-receipt *)', '1.5pt solid #587561', ['@media print']),
  ]) {
    assert.deepEqual(rules.filter(rule => rule.selector === expected.selector), [expected], `preserve shared grid: ${expected.selector}`)
  }
}

test('Live Tour removes body grid only and preserves outer frame and header borders', () => {
  assertLiveTourBorderContract(shared)
})

test('Live Tour border validation ignores unrelated declarations and comment markers', () => {
  assertLiveTourBorderContract(shared.replace(/\/\*[\s\S]*?\*\//g, ''))
  assertLiveTourBorderContract(`${shared}
    /* Live Tour exception: an unrelated later section is not part of it. */
    .unrelated-table { background: red; color: white; outline: 2px solid; box-shadow: none; }
  `)
})

test('Live Tour border validation rejects relevant regressions anywhere in the stylesheet', () => {
  const regressions = [
    ['restored body grid', 'body .live-tour-page .tour-table tbody td { border: 1px solid !important; }'],
    ['removed outer frame', 'body .live-tour-page .tour-table table { border: 0 !important; }'],
    ['removed header grid', '@media print { body .live-tour-page .tour-table thead th { border: 0 !important; } }'],
    ['restored mobile before-shift border', '@media(max-width:820px) { body .live-tour-page .tour-table tr.tour-row-before-shift td.tour-col-employee { border-left: 3px solid !important; } }'],
    ...['background', 'color', 'outline', 'box-shadow'].map(property => [
      `overridden ${property}`, `body .live-tour-page .tour-table tbody td { ${property}: initial !important; }`,
    ]),
  ]
  for (const [name, regression] of regressions) {
    for (const source of [`${regression}\n${shared}`, `${shared}\n/* Later section */\n${regression}`]) {
      assert.throws(() => assertLiveTourBorderContract(source), { code: 'ERR_ASSERTION' }, name)
    }
  }
  assert.throws(() => assertLiveTourBorderContract(shared.replace(
    'body .live-tour-page .tour-table tr.tour-row-before-shift td.tour-col-employee,', '',
  )), { code: 'ERR_ASSERTION' }, 'the before-shift cell must be explicitly included in border removal')
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
