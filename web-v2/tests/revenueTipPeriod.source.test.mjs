import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('../src/pages/RevenuePage.jsx', import.meta.url), 'utf8')

test('Revenue page loads server-calculated TIP and defaults the period from current date', () => {
  assert.match(source, /\/v2\/revenue\/tip-summary/)
  assert.match(source, /defaultRevenueTipStart\(result\.current_date\)/)
  assert.match(source, /loadPeriodTip\(tipStart, tipEnd, controller.signal, !sharedSourceSupported\)/)
  assert.match(source, /value=\{datedReportReady \? money\(commonReport \? data\?\.period_tip : tip\) : '—'\} readOnly/)
  assert.match(source, /setTipEndValid\(true\); setTipEnd\(data\?\.current_date \|\| ''\)/)
})
