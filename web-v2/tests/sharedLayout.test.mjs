import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import { layoutKey, layoutCss } from '../src/lib/sharedLayout.js'
import { transformSync } from '@babel/core'
import layoutIdentity from '../build/layoutIdentity.js'

test('layout identity is unique per menu item and independent of permission-filtered siblings', () => {
  const dom = new JSDOM('<div class="app-shell"><aside class="sidebar" data-vera-node="side"><nav data-vera-node="nav"><a data-vera-node="a" data-vera-item="leave">Lịch nghỉ</a><a data-vera-node="a" data-vera-item="settings">Cài đặt</a></nav></aside></div>')
  const [leave, settings] = dom.window.document.querySelectorAll('a')
  const key = layoutKey(settings, 'settings')
  assert.notEqual(key, layoutKey(leave, 'settings'))
  leave.remove()
  settings.textContent = 'New label'
  assert.equal(key, layoutKey(settings, 'live-tour'))
  dom.window.close()
})

test('layout CSS bounds width to its parent and rejects arbitrary selectors or values', () => {
  const css = layoutCss({ 'l-example': { width: 500, height: 80, order: 2, parent: 'l-parent' }, 'body} *{': { width: 500 }, 'l-bad': { width: '100px;color:red', order: -1 } })
  assert.match(css, /width:min\(500px,100%\)/)
  assert.match(css, /height:auto!important/)
  assert.match(css, /order:2!important/)
  assert.doesNotMatch(css, /color:red|body\}|order:-1/)
})

test('build gives native elements source identities and retains keyed list identities', () => {
  const code = 'const UI = () => <nav>{items.map(item => <button key={item.id}>{item.label}</button>)}</nav>'
  const result = transformSync(code, { filename: '/app/src/components/Example.jsx', parserOpts: { plugins: ['jsx'] }, plugins: [layoutIdentity], configFile: false, babelrc: false }).code
  assert.equal((result.match(/data-vera-node=/g) || []).length, 2)
  assert.match(result, /data-vera-item=\{item.id\}/)
  assert.equal(result, transformSync(code, { filename: '/another/src/components/Example.jsx', parserOpts: { plugins: ['jsx'] }, plugins: [layoutIdentity], configFile: false, babelrc: false }).code)
})

test('source identities survive added whitespace and comments', () => {
  const options = { filename: '/app/src/components/Example.jsx', parserOpts: { plugins: ['jsx'] }, plugins: [layoutIdentity], configFile: false, babelrc: false }
  const source = 'function Example(){return <section className="panel"><button>Lưu</button></section>}'
  const keys = code => [...transformSync(code, options).code.matchAll(/data-vera-node="([^"]+)"/g)].map(match => match[1])
  assert.deepEqual(keys(source), keys('\n// unrelated comment\n\n' + source))
})
