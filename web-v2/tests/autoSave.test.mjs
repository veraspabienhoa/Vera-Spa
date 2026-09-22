import test from 'node:test'
import assert from 'node:assert/strict'
import React, { act, useRef } from 'react'
import { JSDOM } from 'jsdom'
import useAutoSave from '../src/hooks/useAutoSave.js'

test('autosave waits for complete fields, retains one attempt after failure and accepts the next draft', async () => {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
  globalThis.window = dom.window
  globalThis.document = dom.window.document
  Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.querySelector('#root'))
  const calls = []
  let timer
  window.setTimeout = (callback) => { timer = callback; return 1 }
  window.clearTimeout = () => { timer = undefined }
  function Form({ signature, enabled = true }) {
    const ref = useRef(null)
    useAutoSave({ rootRef: ref, signature, enabled, save: async () => { calls.push(signature) } })
    return React.createElement('form', { ref }, React.createElement('input', { id: 'field' }))
  }
  const render = async (signature, enabled = true) => act(() => root.render(React.createElement(Form, { signature, enabled })))
  const tick = async () => { const callback = timer; timer = undefined; await act(async () => callback?.()) }
  try {
    await render('draft1')
    const input = document.querySelector('#field')
    input.focus()
    await tick()
    assert.deepEqual(calls, [])
    input.setCustomValidity('Incomplete date')
    await act(() => input.blur())
    await tick()
    assert.deepEqual(calls, [])
    input.setCustomValidity('')
    await act(() => { input.focus(); input.blur() })
    await tick()
    assert.deepEqual(calls, ['draft1'])
    // An error leaves the same draft enabled; rerenders must not repeatedly submit it.
    await render('draft1', false)
    await render('draft1')
    await tick()
    assert.deepEqual(calls, ['draft1'])
    await render('draft2')
    await tick()
    assert.deepEqual(calls, ['draft1', 'draft2'])
    await render('draft3', false)
    await tick()
    assert.equal(calls.length, 2)
  } finally {
    await act(() => root.unmount())
    dom.window.close()
    delete globalThis.window
    delete globalThis.document
    delete globalThis.IS_REACT_ACT_ENVIRONMENT
  }
})
