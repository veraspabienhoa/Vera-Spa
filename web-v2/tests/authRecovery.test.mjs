import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const built = await build({ entryPoints: ['src/App.jsx'], bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime'], plugins: [{ name: 'fixtures', setup(b) {
  b.onResolve({ filter: /^\.\// }, args => args.kind === 'entry-point' ? undefined : ({ path: args.path, namespace: 'fixture' }))
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, args => ({ loader: 'js', contents:
    args.path.endsWith('/api') ? 'export const veraApi = { me: () => globalThis.authFixture.me() };' :
    args.path.endsWith('/supabase') ? 'export const isAuthConfigured = true; export const getCurrentSession = async () => globalThis.authFixture.session; export const onVeraAuthStateChange = () => () => {}; export const signOutVera = async () => { globalThis.authFixture.signouts++; };' :
    args.path.endsWith('/pushNotifications') ? 'export const ensureGrantedPushSubscription = async () => {};' :
    `export default function Stub() { return ${JSON.stringify(args.path.endsWith('/AppShell') ? 'BUSINESS' : args.path.endsWith('/LoginPage') ? 'LOGIN' : '')}; }`,
  }))
} }] })

test('503 preserves the session and gates business pages; retry recovers; 401 signs out', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' })
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'authFixture']
  const previous = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  const fixture = { session: { access_token: 'test', user: { id: 'u' } }, signouts: 0, me: async () => { throw Object.assign(new Error('PostgreSQL unavailable'), { status: 503 }) } }
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true, authFixture: fixture })) Object.defineProperty(globalThis, key, { value, configurable: true })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.getElementById('root'))
  try {
    await act(async () => root.render(React.createElement(module.exports.default)))
    assert.equal(fixture.signouts, 0)
    assert.match(document.body.textContent, /PostgreSQL unavailable/)
    assert.doesNotMatch(document.body.textContent, /BUSINESS/)
    fixture.me = async () => ({ employee_username: 'test', role: 'admin' })
    await act(async () => document.querySelector('button').click())
    assert.match(document.body.textContent, /BUSINESS/)
    fixture.me = async () => { throw Object.assign(new Error('expired'), { status: 401 }) }
    await act(async () => root.render(React.createElement(module.exports.default, { key: 'new' })))
    assert.equal(fixture.signouts, 1)
    assert.match(document.body.textContent, /LOGIN/)
  } finally {
    await act(async () => root.unmount())
    dom.window.close()
    for (const [key, value] of Object.entries(previous)) { if (value) Object.defineProperty(globalThis, key, value); else delete globalThis[key] }
  }
})
