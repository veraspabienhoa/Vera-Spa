import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import postcss from 'postcss'

// Parsed CSS contracts only: JSDOM does not implement geometry or reliable
// media-query/specificity/!important cascade. Real-browser QA is separate.
const read = path => readFile(new URL(path, import.meta.url), 'utf8')
const panelCss = postcss.parse(await read('../src/pages/DepartmentPayrollPanel.css'))
const sharedCss = postcss.parse(await read('../src/lib/fitPayrollTables.css'))
const ledgerSource = await read('../src/lib/departmentSalaryAdvanceLedger.js')
const ledgerCss = postcss.parse(ledgerSource.match(/style.textContent = `([\s\S]*?)`/)[1].replaceAll('${PANEL_ID}', 'vera-department-salary-advance-ledger'))
function rulesAt(css, width) {
  const result = []
  css.walkRules(rule => {
    for (let parent = rule.parent; parent; parent = parent.parent) {
      if (parent.type !== 'atrule' || parent.name !== 'media') continue
      if (/forced-colors|print/.test(parent.params)) return
      const max = parent.params.match(/max-width:\s*(\d+)px/), min = parent.params.match(/min-width:\s*(\d+)px/)
      if ((max && width > Number(max[1])) || (min && width < Number(min[1]))) return
    }
    result.push(rule)
  })
  return result
}
function declaration(css, width, selector, property) {
  return rulesAt(css, width).filter(rule => rule.selector === selector).flatMap(rule => rule.nodes).filter(node => node.prop === property).at(-1)
}
const table = 'body .department-payroll-page .department-payroll-source-table table'
const cells = 'body .department-payroll-page .department-payroll-source-table :is(th,td)'
const toolbar = '.department-payroll-panel .department-payroll-toolbar,.department-payroll-top-actions'
const ledger = '#vera-department-salary-advance-ledger'
for (const width of [320, 360, 375, 390, 430, 1024, 1440]) {
  test(`source-table sizing and full text contracts at ${width}px`, () => {
    for (const [property, value] of [['width', '100%'], ['min-width', '0'], ['table-layout', 'fixed']]) {
      const actual = declaration(panelCss, width, table, property)
      assert.equal(actual.value, value); assert.equal(actual.important, true, 'must beat the shared payroll fitter')
    }
    const shared = declaration(sharedCss, width, 'body :is(.payroll-tabs-page,.department-payroll-page) table:where(:not([data-payroll-layout="scroll"]))', 'width')
    assert.equal(shared.value, 'max-content'); assert.equal(shared.important, true)
    // Scoped source selector has two classes; shared fitter has one :is class.
    assert.equal(declaration(panelCss, width, cells, 'white-space').value, 'normal')
    assert.equal(declaration(panelCss, width, cells, 'white-space').important, true)
    assert.equal(declaration(panelCss, width, cells, 'overflow-wrap').value, 'anywhere')
    assert.equal(declaration(panelCss, width, 'body .department-payroll-page .department-payroll-source-table', 'overflow').value, 'visible')
    assert.equal(declaration(panelCss, width, 'body .department-payroll-page .department-payroll-source-identity', 'display').value, 'grid')
    assert.equal(declaration(panelCss, width, 'body .department-payroll-page .department-payroll-source-identity :is(strong,small)', 'display').value, 'block')
    assert.equal(declaration(panelCss, width, '.department-payroll-source-options', 'min-width').value, '0')
    assert.equal(declaration(panelCss, width, '.department-payroll-source-options label', 'min-height').value, '44px')
    assert.equal(declaration(panelCss, width, '.department-payroll-source-options label>span', 'overflow-wrap').value, 'anywhere')
    const radio = '.department-payroll-source-options input[type=radio]'
    for (const [property, value] of [['padding', '0'], ['box-sizing', 'border-box'], ['flex', '0 0 18px']]) assert.equal(declaration(panelCss, width, radio, property).value, value)
    assert.equal(['name', 'department', 'choice'].reduce((sum, name) => sum + parseInt(declaration(panelCss, width, `.department-source-${name}-column`, 'width').value), 0), 100)
  })
  test(`marked payroll and advance control contracts at ${width}px`, () => {
    const mobile = width <= 640
    assert.equal(declaration(panelCss, width, toolbar, 'display')?.value, mobile ? 'grid' : undefined)
    assert.equal(declaration(ledgerCss, width, `${ledger} .advance-ledger-title`, 'display').value, mobile ? 'grid' : 'flex')
    assert.equal(declaration(ledgerCss, width, `${ledger} .advance-period-filters`, 'display').value, mobile ? 'grid' : 'flex')
    if (!mobile) return
    assert.equal(declaration(panelCss, width, toolbar, 'grid-template-columns').value, 'repeat(2,minmax(0,1fr))')
    assert.equal(declaration(panelCss, width, '.department-payroll-panel .department-payroll-toolbar>label', 'grid-template-columns').value, 'minmax(0,1fr)')
    const month = 'body .department-payroll-panel .department-payroll-toolbar>label input[type=month]'
    for (const [property, value] of [['width', '100%'], ['min-width', '0'], ['max-width', '100%'], ['box-sizing', 'border-box'], ['appearance', 'none']]) assert.equal(declaration(panelCss, width, month, property).value, value)
    assert.equal(declaration(panelCss, width, '.department-payroll-panel .department-payroll-toolbar>.department-payroll-calculate,.department-payroll-panel .department-payroll-toolbar>.department-payroll-delete-draft', 'grid-column').value, '1/-1')
    assert.equal(declaration(ledgerCss, width, `${ledger} .advance-period-filters`, 'grid-template-columns').value, 'repeat(3,minmax(0,1fr))')
    assert.equal(declaration(ledgerCss, width, `${ledger} .advance-period-filters>label`, 'grid-column').value, '1/-1')
    assert.equal(declaration(ledgerCss, width, `${ledger} .advance-ledger-controls`, 'grid-template-columns').value, 'repeat(2,minmax(0,1fr))')
    const buttons = `${ledger} .advance-period-filters>button,${ledger} .advance-ledger-controls>button`
    for (const [property, value] of [['width', '100%'], ['min-width', '0'], ['min-height', '44px'], ['white-space', 'normal'], ['box-sizing', 'border-box']]) assert.equal(declaration(ledgerCss, width, buttons, property).value, value)
  })
}
