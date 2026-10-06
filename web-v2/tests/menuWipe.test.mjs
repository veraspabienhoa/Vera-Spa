import test from 'node:test'
import assert from 'node:assert/strict'
import React, { act, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { JSDOM } from 'jsdom'
import useMenuWipe from '../src/lib/useMenuWipe.js'

test('mobile reveal follows horizontal drag, settles, and preserves native gestures', async t => {
  const dom = new JSDOM('<div id="root"></div>', { pretendToBeVisual: true })
  globalThis.window = dom.window; globalThis.document = dom.window.document; globalThis.IS_REACT_ACT_ENVIRONMENT = true
  let mobile = true, clicks = 0
  window.matchMedia = () => ({ matches: mobile })
  function Shell() {
    const ref = useRef(null), [open, setOpen] = useState(false)
    useMenuWipe(ref, open, setOpen)
    return React.createElement('div', { ref, 'data-open': String(open) },
      React.createElement('aside', { className: 'sidebar' }), React.createElement('input'),
      React.createElement('button', { onClick: () => clicks++ }, 'Page action'))
  }
  const root = createRoot(document.getElementById('root'))
  t.after(async () => { await act(() => root.unmount()); dom.window.close() })
  await act(() => root.render(React.createElement(Shell)))
  const shell = document.querySelector('[data-open]')
  shell.querySelector('.sidebar').getBoundingClientRect = () => ({ width: 300 })
  const touch = async (type, x, y = 100, target = shell) => {
    const event = new window.Event(type, { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'touches', { value: type === 'touchend' || type === 'touchcancel' ? [] : [{ identifier: 1, clientX: x, clientY: y }] })
    await act(() => target.dispatchEvent(event)); return event
  }
  await touch('touchstart', 15); assert.equal((await touch('touchmove', 155)).defaultPrevented, true)
  assert.equal(shell.style.getPropertyValue('--menu-offset'), '140px')
  assert.ok(shell.classList.contains('menu-dragging'))
  await touch('touchend', 155); assert.equal(shell.dataset.open, 'true')
  await act(() => shell.querySelector('button').click()); assert.equal(clicks, 0)
  await touch('touchstart', 250); await touch('touchmove', 100); await touch('touchend', 100)
  assert.equal(shell.dataset.open, 'false')
  // A short drag returns closed; cancel restores the current settled state.
  await touch('touchstart', 10); await touch('touchmove', 40); await touch('touchend', 40)
  assert.equal(shell.dataset.open, 'false')
  await touch('touchstart', 10); await touch('touchmove', 200); await touch('touchcancel', 200)
  assert.equal(shell.dataset.open, 'false'); assert.equal(shell.style.getPropertyValue('--menu-offset'), '')
  await touch('touchstart', 10); assert.equal((await touch('touchmove', 15, 190)).defaultPrevented, false)
  await touch('touchend', 15, 190); assert.equal(shell.dataset.open, 'false')
  await touch('touchstart', 100); assert.equal((await touch('touchmove', 270)).defaultPrevented, false)
  await touch('touchend', 270); assert.equal(shell.dataset.open, 'false')
  const input = shell.querySelector('input')
  await touch('touchstart', 10, 100, input); await touch('touchmove', 220, 100, input); await touch('touchend', 220, 100, input)
  assert.equal(shell.dataset.open, 'false')
  mobile = false; await touch('touchstart', 10); await touch('touchmove', 240); await touch('touchend', 240)
  assert.equal(shell.dataset.open, 'false')
})
