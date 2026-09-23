import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const built = await build({ entryPoints: ['src/components/EmployeeProfileModal.jsx'], bundle: true, write: false,
  platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react-dom', 'react/jsx-runtime'],
  loader: { '.css': 'empty' } })

test('profile modal uses a portal, locks scrolling and restores focus when closed', async () => {
  const dom = new JSDOM('<body><button id="edit">Sửa</button><main></main></body>', { pretendToBeVisual: true })
  globalThis.window = dom.window
  globalThis.document = dom.window.document
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const { createRoot } = await import('react-dom/client')
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
  const root = createRoot(document.querySelector('main'))
  const opener = document.querySelector('#edit')
  opener.focus()
  let closes = 0
  const render = (busy) => root.render(React.createElement(module.exports.default, { busy, onClose: () => { closes++ } },
    React.createElement('h2', { id: 'employee-profile-modal-title' }, 'SỬA HỒ SƠ')))
  try {
    await act(() => render(false))
    const dialog = document.querySelector('[role="dialog"]')
    assert.ok(dialog)
    assert.equal(document.querySelector('main').contains(dialog), false)
    assert.equal(document.body.style.overflow, 'hidden')
    assert.equal(document.activeElement, dialog)
    await act(() => dialog.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    assert.equal(closes, 1)
    await act(() => render(true))
    await act(() => dialog.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    assert.equal(closes, 1, 'Escape must not interrupt a save')
    await act(() => root.unmount())
    assert.equal(document.body.style.overflow, '')
    assert.equal(document.activeElement, opener)
  } finally { dom.window.close() }
})
