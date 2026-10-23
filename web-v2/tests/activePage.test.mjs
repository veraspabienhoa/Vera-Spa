import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import { readActivePage, rememberActivePage, forgetActivePage } from '../src/lib/activePage.js'
const pages = new Set(['live-tour', 'training', 'quang-ngai'])
test('reload retains the tab page while other tabs and accounts stay independent', () => {
  const a = new JSDOM('', { url:'https://example.test' }), b = new JSDOM('', { url:'https://example.test' })
  const user = { id:'admin' }, other = { id:'director' }
  try {
    rememberActivePage(user, 'training', pages, a.window)
    assert.equal(readActivePage(user, pages, a.window), 'training')
    assert.equal(readActivePage(user, pages, b.window), 'live-tour')
    rememberActivePage(user, 'quang-ngai', pages, b.window)
    rememberActivePage(other, 'quang-ngai', pages, a.window)
    a.window.localStorage.setItem('vera-v2-active-page:admin', 'live-tour')
    a.window.dispatchEvent(new a.window.StorageEvent('storage'))
    assert.equal(readActivePage(user, pages, a.window), 'training')
    assert.equal(readActivePage(other, pages, a.window), 'quang-ngai')
    forgetActivePage(user, a.window)
    assert.equal(readActivePage(user, pages, a.window), 'live-tour')
    assert.equal(readActivePage(other, pages, a.window), 'quang-ngai')
  } finally { a.window.close(); b.window.close() }
})
test('invalid pages and inaccessible storage fall back safely', () => {
  const target = { sessionStorage:{ getItem:()=> 'unknown', setItem(){throw Error('blocked')}, removeItem(){throw Error('blocked')} } }
  assert.equal(readActivePage({id:'admin'}, pages, target), 'live-tour')
  assert.doesNotThrow(()=>rememberActivePage({id:'admin'}, 'training', pages, target))
  assert.doesNotThrow(()=>forgetActivePage({id:'admin'}, target))
})
