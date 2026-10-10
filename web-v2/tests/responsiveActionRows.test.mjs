import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { JSDOM } from 'jsdom'

// CSS contract checks complement the rendered component tests. JSDOM does not
// calculate layout: these assertions do not claim browser viewport coverage.
const shared = fs.readFileSync(new URL('../src/clear-borders.css', import.meta.url), 'utf8')
const dom = new JSDOM(`<style>${shared}</style>`)
const rules = []
function visit(children, media = '') {
  for (const rule of children) {
    if (rule.selectorText) rules.push({ selector: rule.selectorText, style: rule.style, media })
    else if (rule.cssRules) visit(rule.cssRules, rule.conditionText || media)
  }
}
visit(dom.window.document.styleSheets[0].cssRules)
dom.window.close()
const find = (selector, media = '') => rules.find(rule => rule.selector === selector && rule.media === media)?.style

test('check-in action grid has three equal tracks and wraps labels inside each button', () => {
  const row = find('.checkin-history-page .checkin-history-actions')
  assert.equal(row.display, 'grid')
  assert.equal(row.getPropertyValue('grid-template-columns'), 'repeat(3,minmax(0,1fr))')
  assert.equal(row.getPropertyValue('align-items'), 'stretch')
  const buttons = find('.checkin-history-page .checkin-history-actions button')
  assert.equal(buttons.getPropertyValue('min-width'), '0')
  assert.equal(buttons.getPropertyValue('min-height'), '44px')
  assert.equal(buttons.getPropertyValue('white-space'), 'normal')
  assert.equal(buttons.getPropertyValue('overflow-wrap'), 'anywhere')
  assert.equal(find('.checkin-history-page .checkin-history-actions button', '(max-width:480px)').getPropertyValue('flex-direction'), 'column')
  assert.ok(!rules.some(rule => /checkin-(history-actions|live-device-button)/.test(rule.selector) && rule.style.getPropertyValue('grid-column') === '1 / -1'))
  assert.ok(!rules.some(rule => /checkin-history-actions/.test(rule.selector) && rule.media && rule.style.getPropertyValue('grid-template-columns')),
    'mobile styling must not turn the three actions into separate grid rows')
})

test('booking footer stays a right-aligned equal-width row and fills narrow screens', () => {
  const row = find('.online-booking-modal .online-booking-detail-actions')
  assert.equal(row.display, 'grid')
  assert.equal(row.getPropertyValue('grid-auto-flow'), 'column')
  assert.equal(row.getPropertyValue('grid-auto-columns'), 'minmax(0,1fr)')
  assert.equal(row.getPropertyValue('align-items'), 'stretch')
  assert.equal(row.getPropertyValue('margin'), '12px 0 0 auto')
  assert.equal(row.width, 'min(100%,420px)')
  assert.equal(find('.online-booking-modal .online-booking-detail-actions', '(max-width:600px)').width, '100%')
  const buttons = find('.online-booking-modal .online-booking-detail-actions>button')
  assert.equal(buttons.width, '100%')
  assert.equal(buttons.getPropertyValue('min-width'), '0')
  assert.equal(buttons.getPropertyValue('min-height'), '44px')
  assert.equal(buttons.getPropertyValue('white-space'), 'normal')
})

test('booking date toolbar makes room for all six presets and keeps its responsive wrap', () => {
  assert.equal(find('body .online-booking-page .online-booking-periods').getPropertyValue('grid-template-columns'), 'minmax(190px,1.6fr) repeat(6,minmax(0,1fr))')
  assert.equal(find('body .online-booking-page .online-booking-periods', '(max-width:1000px)').getPropertyValue('grid-template-columns'), 'repeat(3,minmax(0,1fr))')
})
