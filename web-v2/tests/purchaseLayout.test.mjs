import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { JSDOM } from 'jsdom'

// JSDOM parses CSS but does not calculate layout. These contracts protect the
// source rules; a synthetic browser fixture is prepared separately for geometry QA.
const purchase = fs.readFileSync(new URL('../src/pages/PurchasePage.css', import.meta.url), 'utf8')
const revenue = fs.readFileSync(new URL('../src/pages/RevenuePage.css', import.meta.url), 'utf8')
const dom = new JSDOM(`<style>${purchase}</style><style>${revenue}</style>`)
const rules = []
function visit(children, media = '') {
  for (const rule of children) {
    if (rule.selectorText) rules.push({ selector: rule.selectorText, style: rule.style, media })
    else if (rule.cssRules) visit(rule.cssRules, rule.conditionText || media)
  }
}
visit(dom.window.document.styleSheets[0].cssRules)
dom.window.close()
const find = (selector, media = '') => rules.findLast(rule => rule.selector === selector && rule.media === media)?.style
const desktop = '(min-width: 761px)'

test('purchase summary explicitly keeps its own grid when Revenue CSS is also loaded', () => {
  const row = find('.purchase-controls .purchase-summary-head')
  assert.equal(row.display, 'grid')
  assert.equal(row.getPropertyValue('grid-template-columns'), 'minmax(0,1fr)')
  assert.equal(row.padding, '12px 0 0')
  assert.equal(find('.purchase-controls .purchase-summary-head', desktop).getPropertyValue('grid-template-columns'), 'max-content minmax(0, 1fr)')
})

test('purchase total keeps its natural width and does not split large currency amounts', () => {
  const total = find('.purchase-controls .purchase-filter-total')
  assert.equal(total.width, 'fit-content')
  assert.equal(total.getPropertyValue('max-width'), '100%')
  assert.equal(total.getPropertyValue('min-width'), '0')
  assert.equal(find('.purchase-controls .purchase-filter-total', desktop).width, 'max-content')
  assert.equal(find('.purchase-controls .purchase-filter-total', desktop).getPropertyValue('align-self'), 'start')
  const amount = find('.purchase-controls .purchase-filter-total strong')
  assert.equal(amount.getPropertyValue('font-size'), '18px')
  assert.equal(amount.getPropertyValue('white-space'), 'nowrap')
  assert.equal(amount.getPropertyValue('overflow-wrap'), 'normal')
  assert.equal(amount.getPropertyValue('font-variant-numeric'), 'tabular-nums')
})

test('desktop actions wrap complete buttons instead of crushing words into narrow columns', () => {
  const actions = find('.purchase-controls .purchase-actions', desktop)
  assert.equal(actions.display, 'grid')
  assert.equal(actions.getPropertyValue('grid-template-columns'), 'repeat(auto-fit, minmax(96px, 1fr))')
  assert.ok(!actions.getPropertyValue('grid-auto-flow'))
  const button = find('.purchase-controls .purchase-actions button')
  assert.equal(button.getPropertyValue('overflow-wrap'), 'normal')
  assert.equal(button.getPropertyValue('word-break'), 'normal')
  assert.equal(find('.purchase-controls .purchase-actions button', desktop).getPropertyValue('font-size'), '12px')
})

test('mobile keeps a bounded two-column action grid', () => {
  const row = find('.purchase-periods,.purchase-actions', '(max-width:760px)')
  assert.equal(row.getPropertyValue('grid-template-columns'), 'repeat(2,minmax(0,1fr))')
  assert.equal(row.width, '100%')
})
