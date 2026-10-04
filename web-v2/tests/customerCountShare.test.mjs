import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { canSharePdf, shareCustomerCountPdf } from '../src/lib/customerCountShare.js'

const file = { name: 'VERA_SoLuongKhach.pdf', type: 'application/pdf' }
test('native sharing passes only the prepared PDF; unsupported devices do not send a URL', async () => {
 let calls = []
 const browser = { canShare: data => data.files[0] === file, share: data => { calls.push(data); return Promise.resolve() } }
 assert.equal(canSharePdf(file, browser), true)
 await shareCustomerCountPdf(file, browser)
 assert.equal(calls.length, 1); assert.equal(calls[0].files[0], file); assert.equal(calls[0].url, undefined)
 assert.throws(() => shareCustomerCountPdf(file, { canShare: () => false, share: () => { throw Error('must not call') } }), /Tải|tải PDF/)
 assert.equal(canSharePdf(file, { canShare: () => { throw Error('blocked') } }), false)
})

const built = await build({ stdin: { contents: "export { default } from './src/components/CustomerCountShareDialog'", loader: 'jsx', resolveDir: process.cwd() }, bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react-dom', 'react/jsx-runtime'], loader: { '.css': 'empty' }, plugins: [{ name: 'api', setup(b) {
 b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
 b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi={readCustomerCountPdf:(filters,options)=>window.preparePdf(filters,options)}' }))
} }] })

test('dialog prepares frozen filters, shares only on a second click and revokes its object URL', async () => {
 const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test' })
 const values = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator, File: dom.window.File, URL: dom.window.URL, IS_REACT_ACT_ENVIRONMENT: true }
 const saved = Object.fromEntries(Object.keys(values).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
 for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { value, configurable: true })
 let resolve, signal, actualFilters, shares = [], revoked = []
 window.preparePdf = (filters, options) => { actualFilters = filters; signal = options.signal; return new Promise(done => { resolve = done }) }
 URL.createObjectURL = () => 'blob:prepared'; URL.revokeObjectURL = value => revoked.push(value)
 navigator.canShare = () => true; navigator.share = data => { shares.push(data); return Promise.reject(Object.assign(Error('cancel'), { name: 'AbortError' })) }
 const mod = { exports: {} }; new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports)
 const { createRoot } = await import('react-dom/client'), root = createRoot(document.querySelector('#root'))
 const filters = { date_from:'2026-10-01', date_to:'2026-10-04', employee:'Mạnh Đạt', total_amount:0 }
 try {
  await act(async () => root.render(React.createElement(mod.exports.default, { filters, onClose: () => {} })))
  assert.deepEqual(actualFilters, filters); assert.equal(shares.length, 0); assert.match(document.body.textContent, /Đang tạo PDF/)
  await act(async () => resolve(new window.Blob(['%PDF-1.4'], { type:'application/pdf' })))
  assert.equal(shares.length, 0, 'preparing never opens the share sheet automatically')
  assert.equal(document.querySelector('a[download]').getAttribute('download'), 'VERA_SoLuongKhach.pdf')
  const button = [...document.querySelectorAll('button')].find(node => node.textContent === 'Chia sẻ qua Zalo')
  await act(async () => button.click())
  assert.equal(shares.length, 1); assert.equal(shares[0].files[0].type, 'application/pdf')
  assert.equal(document.querySelector('[role=alert]'), null, 'cancel is not an error or download')
  await act(async () => root.unmount())
  assert.equal(signal.aborted, true); assert.deepEqual(revoked, ['blob:prepared'])
 } finally {
  dom.window.close()
  for (const [key, descriptor] of Object.entries(saved)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key] }
 }
})
