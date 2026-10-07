import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'

const bundle = await build({ stdin: { contents: "import {startScopedReconciler} from './src/lib/scopedReconciler';window.start=startScopedReconciler", resolveDir: process.cwd() }, bundle: true, write: false, format: 'iife' })
test('compatibility helpers ignore other pages, coalesce edits, and disconnect removed roots', async () => {
  const dom = new JSDOM('<body><main></main></body>', { runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window, frames = new Map()
  let frameId = 0, calls = 0
  w.requestAnimationFrame = fn => { frames.set(++frameId, fn); return frameId }
  w.cancelAnimationFrame = id => frames.delete(id)
  w.setInterval = () => { throw Error('No idle polling') }
  const flush = async () => {
    await new Promise(resolve => setImmediate(resolve))
    const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn())
    await new Promise(resolve => setImmediate(resolve))
  }
  w.eval(bundle.outputFiles[0].text)
  const stop = w.start('.profile', () => {
    calls++
    w.document.querySelector('.profile')?.classList.add('ready')
  }, ['class'])
  try {
    w.document.querySelector('main').innerHTML = '<table><tr><td>Unrelated page</td></tr></table>'
    await flush(); assert.equal(calls, 0)
    const root = w.document.createElement('section'); root.className = 'profile'; w.document.body.append(root)
    await flush(); assert.equal(calls, 1)
    assert.equal(frames.size, 0, 'own DOM edits cannot create a reconciliation loop')
    root.innerHTML = '<input><span>One</span>'
    root.querySelector('input').dispatchEvent(new w.Event('input', { bubbles: true }))
    root.querySelector('input').dispatchEvent(new w.Event('change', { bubbles: true }))
    await flush(); assert.equal(calls, 2)
    root.remove(); await flush()
    root.append(w.document.createElement('span')); await flush(); assert.equal(calls, 2)
    stop(); w.document.body.append(root); await flush(); assert.equal(calls, 2)
  } finally { stop(); w.close() }
})
