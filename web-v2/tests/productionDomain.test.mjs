import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('production web artifacts target only the app.veraspa.vn root', () => {
  const vite = read('../vite.config.js')
  const html = read('../index.html')
  const manifest = JSON.parse(read('../public/manifest.webmanifest'))
  const worker = read('../public/sw.js')
  const cname = read('../public/CNAME').trim()

  assert.equal(cname, 'app.veraspa.vn')
  assert.match(vite, /base: '\/'/)
  assert.equal(manifest.id, '/')
  assert.equal(manifest.start_url, '/')
  assert.equal(manifest.scope, '/')
  assert.match(html, /href="\/manifest\.webmanifest"/)
  assert.match(worker, /const APP_URL = '\/'/)
  for (const source of [vite, html, worker, JSON.stringify(manifest)]) {
    assert.doesNotMatch(source, /Vera-Spa\//)
    assert.doesNotMatch(source, /veraspabienhoa\.github\.io/)
  }
})
