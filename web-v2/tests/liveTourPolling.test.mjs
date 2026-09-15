import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const page = readFileSync(new URL('../src/pages/LiveTourPage.jsx', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/lib/api.js', import.meta.url), 'utf8')

test('quiet Live Tour polls send the current revision and skip unchanged state replacement', () => {
  assert.match(page, /load\(false, true, true\)/)
  assert.match(page, /conditional \? latestRevisionRef\.current : null/)
  assert.match(page, /if \(response\?\.unchanged\)/)
  assert.match(api, /params\.set\('known_revision', String\(knownRevision\)\)/)
})
