import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act, useState } from 'react'
import { JSDOM } from 'jsdom'
const bundle = await build({ stdin: { contents: "export {default} from './src/components/RulesTabs'", resolveDir: process.cwd() }, bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react-dom', 'react/jsx-runtime'], loader: { '.css': 'empty' } })
const mod = { exports: {} }; new Function('require', 'module', 'exports', bundle.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports)
test('unified rules tabs retain edits when switching and honor the HC entry', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test' })
  globalThis.window = dom.window; globalThis.document = dom.window.document; globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.querySelector('#root'))
  t.after(async () => { await act(() => root.unmount()); dom.window.close() })
  let change
  function Draft() { const [value, setValue] = useState(''); change = setValue; return React.createElement('p', {}, value || 'HC') }
  await act(() => root.render(React.createElement(mod.exports.default, { initialTab: 'administrative', administrative: React.createElement(Draft), ktv: React.createElement('p', {}, 'KTV') })))
  assert.equal(document.querySelector('h1').textContent, 'Nội qui')
  await act(() => change('Bản đang sửa'))
  await act(() => document.querySelector('#rules-tab-ktv').click())
  assert.equal(document.querySelector('#rules-panel-administrative').hidden, true)
  await act(() => document.querySelector('#rules-tab-administrative').click())
  assert.match(document.querySelector('#rules-panel-administrative').textContent, /Bản đang sửa/)
})
