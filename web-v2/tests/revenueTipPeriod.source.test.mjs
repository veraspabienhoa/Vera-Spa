import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('../src/pages/RevenuePage.jsx', import.meta.url), 'utf8')

test('Revenue page auto-loads Live Tour TIP and defaults the period from current date', () => {
  assert.match(source, /\/v2\/live-tour\/reports/)
  assert.match(source, /defaultRevenueTipStart\(result\.current_date\)/)
  assert.match(source, /revenueTipTotal\(tipRows, tipStart, tipEnd\)/)
  assert.match(source, /value=\{Number\.isFinite\(Number\(tip\)\) \? tip : 0\} readOnly/)
  assert.match(source, /onClick=\{\(\) => setTipEnd\(data\?\.current_date \|\| ''\)\}/)
})
