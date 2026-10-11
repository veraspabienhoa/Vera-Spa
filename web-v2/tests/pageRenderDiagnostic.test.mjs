import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { loadedPageRevision, pageRenderDiagnostic } from '../src/lib/pageRenderDiagnostic.js'

test('render diagnostics use fixed categories and never return raw exception details', () => {
  const cases = [
    [new TypeError("Cannot read properties of undefined (reading 'toLocaleString')"), 'RENDER_NUMBER_FORMAT'],
    [new Error('Objects are not valid as a React child: PRIVATE-CUSTOMER'), 'RENDER_OBJECT_CHILD'],
    [new Error('Minified React error #31; visit https://reactjs.org/docs/error-decoder.html?invariant=31&args[]=PRIVATE'), 'RENDER_OBJECT_CHILD'],
    [new TypeError('PRIVATE-CUSTOMER is not iterable'), 'RENDER_COLLECTION'],
    [new Error('Rendered fewer hooks than expected'), 'RENDER_HOOKS'],
    [new TypeError('PRIVATE-CUSTOMER'), 'RENDER_TYPE'], [new RangeError('PRIVATE-CUSTOMER'), 'RENDER_RANGE'],
    [new ReferenceError('PRIVATE-CUSTOMER'), 'RENDER_REFERENCE'], [new Error('https://private.test/?token=PRIVATE'), 'RENDER_OTHER'],
    [{ name: '__proto__', message: 'PRIVATE' }, 'RENDER_OTHER'], [{ name: 'constructor', message: 'PRIVATE' }, 'RENDER_OTHER'],
  ]
  for (const [error, expected] of cases) assert.equal(pageRenderDiagnostic(error), expected)
  assert.equal(loadedPageRevision, 'development')
})

test('mounted recovery shows the loaded build and category without customer names, secrets or URLs', async () => {
  const revision = '1234567890abcdef'.repeat(2) + '12345678'
  const built = await build({ entryPoints: ['src/components/PageErrorBoundary.jsx'], bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime'], define: { __VERA_BUILD_REVISION__: JSON.stringify(revision) } })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test/?token=SECRET' })
  const globals = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true }
  const saved = Object.fromEntries(Object.keys(globals).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { value, configurable: true })
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.querySelector('#root'))
  const previousError = console.error; console.error = () => {}
  dom.window.addEventListener('error', event => event.preventDefault())
  function Broken() { throw Error('Objects are not valid as a React child: PRIVATE-CUSTOMER https://private.test/?token=SECRET') }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { page: 'live-tour' }, React.createElement(Broken))))
    assert.match(document.body.textContent, /PAGE_RENDER · live-tour/)
    assert.match(document.body.textContent, /RENDER_OBJECT_CHILD · bản 1234567890ab/)
    assert.doesNotMatch(document.body.textContent, /PRIVATE|SECRET|https:/)
  } finally {
    await act(() => root.unmount()); console.error = previousError; dom.window.close()
    for (const [key, value] of Object.entries(saved)) { if (value) Object.defineProperty(globalThis, key, value); else delete globalThis[key] }
  }
})
