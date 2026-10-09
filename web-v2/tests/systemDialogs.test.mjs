import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const built = await build({ stdin: { contents: `import * as dialogs from './src/lib/systemDialogs'; import {startSystemFeedback} from './src/lib/systemFeedback';Object.assign(window, dialogs, {startSystemFeedback});`, resolveDir: process.cwd(), loader: 'js' }, bundle: true, write: false, format: 'iife' })
const setup = html => {
  const dom = new JSDOM(html || '<button id="opener">Mở</button>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  dom.window.eval(built.outputFiles[0].text)
  return dom
}
const settle = w => new Promise(resolve => w.setTimeout(resolve, 0))
const top = w => [...w.document.querySelectorAll('.system-dialog')].at(-1)
const choose = (w, yes) => top(w).querySelector(yes ? '.primary-button' : '.secondary-button').click()

test('confirmation waits for an explicit answer and Escape cannot close the underlying form', async () => {
  const dom = setup(), w = dom.window
  try {
    const opener = w.document.querySelector('#opener'); opener.focus()
    let writes = 0, escapedForm = 0
    w.document.addEventListener('keydown', event => { if (event.key === 'Escape') escapedForm++ })
    const remove = async () => { if (await w.confirmDialog('Xóa bộ phận?')) writes++ }
    const first = remove(); await settle(w)
    assert.equal(writes, 0)
    assert.equal(top(w).getAttribute('role'), 'alertdialog')
    assert.equal(w.document.activeElement.textContent, 'Hủy', 'destructive confirmation defaults to cancel')
    w.document.activeElement.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await first
    assert.equal(writes, 0); assert.equal(escapedForm, 0); assert.equal(w.document.activeElement, opener)
    const second = remove(); choose(w, true); await second
    assert.equal(writes, 1); assert.equal(top(w), undefined); assert.equal(w.document.body.style.overflow, '')
  } finally { w.clearSystemDialogs(); w.close() }
})

test('prompt distinguishes empty input from cancellation and treats messages as text', async () => {
  const dom = setup(), w = dom.window
  try {
    let response = w.promptDialog('<img src=x onerror=alert(1)>\nLý do:', 'mẫu')
    assert.equal(top(w).querySelector('img'), null)
    const input = top(w).querySelector('input'); assert.equal(input.value, 'mẫu'); input.value = ''
    input.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    assert.equal(await response, '')
    response = w.promptDialog('Nhập lại'); choose(w, false); assert.equal(await response, null)
  } finally { w.clearSystemDialogs(); w.close() }
})

test('notices queue without truncation, child confirmations retain their live parent and cleanup cancels decisions', async () => {
  const dom = setup(), w = dom.window
  try {
    const content = w.document.createElement('div'); content.innerHTML = '<button id="retry">Thử lại</button>'
    const first = w.showSystemDialog({ message: 'Đầu tiên', content })
    for (let i = 0; i < 12; i++) w.showSystemDialog({ message: `Thông báo ${i}` })
    assert.equal(w.document.querySelectorAll('.system-dialog').length, 1)
    const retry = content.querySelector('button'); retry.focus()
    const decision = w.confirmDialog('Tiếp tục?'); assert.equal(w.document.querySelectorAll('.system-dialog').length, 2)
    choose(w, false); assert.equal(await decision, false)
    assert.equal(w.document.activeElement, retry); assert.equal(w.document.body.style.overflow, 'hidden')
    first.close()
    for (let i = 0; i < 12; i++) { assert.equal(top(w).querySelector('p').textContent, `Thông báo ${i}`); choose(w, true) }
    assert.equal(top(w), undefined); assert.equal(w.document.body.style.overflow, '')
    w.showSystemDialog({ message: 'Phiên cũ' }); w.showSystemDialog({ message: 'Chờ' })
    const pending = w.confirmDialog('Xóa?'); w.clearSystemDialogs()
    assert.equal(await pending, false); assert.equal(top(w), undefined); assert.equal(w.document.body.style.overflow, '')
  } finally { w.clearSystemDialogs(); w.close() }
})

test('feedback covers initial render, retries and text mutations without duplicate inline messages or loading dialogs', async () => {
  const dom = setup('<div class="stable-feedback"><p role="status">Đang tải…</p></div><div class="error-box">Mã bộ phận đã tồn tại.</div><p role="status">12 kết quả</p>'), w = dom.window
  const stop = w.startSystemFeedback()
  try {
    const source = w.document.querySelector('.error-box')
    assert.ok(source.hasAttribute('data-feedback-presented'))
    assert.equal(top(w).querySelector('p').textContent, 'Mã bộ phận đã tồn tại.')
    source.firstChild.data = 'Mã bộ phận đã tồn tại.'; await settle(w)
    choose(w, true); assert.equal(top(w), undefined)
    source.textContent = ''; await settle(w)
    source.textContent = 'Mã bộ phận đã tồn tại.'; await settle(w)
    assert.ok(top(w), 'a repeated attempt after clearing feedback must be visible')
    choose(w, true)
    let retries = 0
    source.textContent = 'Mạng gián đoạn. '
    const retry = w.document.createElement('button'); retry.textContent = 'Thử lại'; retry.onclick = () => retries++
    source.append(retry); await settle(w)
    assert.equal(top(w).querySelector('p').textContent, 'Mạng gián đoạn.')
    top(w).querySelector('.secondary-button').click(); assert.equal(retries, 1)
    assert.equal(top(w), undefined, 'loading and result counts never become notifications')
  } finally { stop(); w.close() }
})

test('dismissing a live notification waits for its owner; an acknowledgement failure can still be shown', async () => {
  const dom = setup(), w = dom.window
  const stop = w.startSystemFeedback()
  try {
    const content = w.document.createElement('div'); let requests = 0
    const notice = w.showSystemDialog({ content, onDismiss: () => { requests++ } })
    choose(w, true); assert.equal(requests, 1); assert.ok(top(w))
    const error = w.document.createElement('p'); error.setAttribute('role', 'alert'); error.textContent = 'Không thể ghi nhận đã xem.'; content.append(error)
    await settle(w)
    assert.equal(w.document.querySelectorAll('.system-dialog').length, 2)
    choose(w, true); assert.ok(top(w)); notice.close(); assert.equal(top(w), undefined)
  } finally { stop(); w.close() }
})

test('all browser alerts, confirms and prompts use the shared asynchronous modal API', () => {
  function inspect(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) inspect(path)
      else if (/\.(js|jsx)$/.test(path)) assert.doesNotMatch(readFileSync(path, 'utf8'), /\bwindow\.(alert|confirm|prompt)\s*\(/, path)
    }
  }
  inspect('src')
})


test('required form fields use one modal, retain native validity and focus the first invalid field', async () => {
  const dom = setup('<form><label>Mã bộ phận<input required name="code"></label><input required name="name"></form>'), w = dom.window
  const stop = w.startSystemFeedback()
  try {
    assert.equal(w.document.querySelector('form').checkValidity(), false)
    assert.equal(w.document.querySelectorAll('.system-dialog').length, 1)
    assert.match(top(w).textContent, /Vui lòng nhập mã bộ phận/)
    choose(w, true); await settle(w)
    assert.equal(w.document.activeElement.name, 'code')
    const source = w.document.createElement('p'); source.className = 'error-box'; source.textContent = 'Thử lại'; w.document.body.append(source)
    await settle(w); choose(w, true)
    source.className = 'normal-content'; await settle(w)
    assert.equal(source.hasAttribute('data-feedback-presented'), false, 'React can reuse the node for ordinary page content')
  } finally { stop(); w.close() }
})


test('CCCD and salary advance feedback share the modal and legacy banner timers cannot dismiss it', async () => {
  const dom = setup('<p class="vera-cccd-target-status">Đang nhận dạng thông tin từ ảnh CCCD…</p><p class="advance-ledger-message"></p>'), w = dom.window
  const stop = w.startSystemFeedback()
  try {
    assert.equal(top(w), undefined)
    const source = w.document.querySelector('.advance-ledger-message')
    source.className = 'advance-ledger-message show success'; source.textContent = 'Đã lưu khoản ứng lương.'
    await settle(w); assert.match(top(w).className, /system-dialog-success/)
    source.className = 'advance-ledger-message'; await settle(w)
    assert.match(top(w).textContent, /Đã lưu khoản ứng lương/, 'the old banner timeout does not close the modal')
    choose(w, true)
    const cccd = w.document.querySelector('.vera-cccd-target-status')
    cccd.className = 'vera-cccd-target-status error'; cccd.textContent = 'Không nhận dạng được thông tin CCCD.'
    await settle(w); assert.match(top(w).className, /system-dialog-error/)
    choose(w, true)
    cccd.className = 'vera-cccd-target-status ok'; cccd.textContent = 'Đã gắn thông tin.'
    await settle(w); assert.match(top(w).className, /system-dialog-success/)
  } finally { stop(); w.close() }
})
