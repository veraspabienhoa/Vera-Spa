import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import { headerColumnMap, resizeColumnPair, startTableColumnResize } from '../src/lib/tableColumnResize.js'

function fixture({ grouped = false, scale = 1, colgroup = false, identity = '', saved = null } = {}) {
  const head = grouped ? '<tr><th rowspan="2">Nhân viên</th><th colspan="2">Tháng 10</th></tr><tr><th>01</th><th>02</th></tr>' : '<tr><th>A</th><th>B</th><th>C</th></tr>'
  const dom = new JSDOM(`<table style="width:400px">${colgroup ? '<colgroup><col style="width:25%"><col style="width:30%"><col style="width:45%"></colgroup>' : ''}<thead>${head}</thead><tbody><tr><td><input value="Không thay đổi"></td><td>120</td><td>180</td></tr></tbody></table>`, { pretendToBeVisual: true, url: 'https://example.test' })
  const { window: win } = dom, doc = win.document, table = doc.querySelector('table')
  if (identity) table.dataset.tableResizeKey = identity
  if (saved) for (const [key,value] of saved) win.localStorage.setItem(key,value)
  Object.defineProperty(table, 'offsetWidth', { get: () => 400 })
  table.getBoundingClientRect = () => ({ width: 400 * scale, left: 0, right: 400 * scale })
  const widths = () => {
    const cols = [...table.querySelectorAll('col')]
    return cols.length === 3 && cols.every(col => col.style.width.endsWith('%')) ? cols.map(col => parseFloat(col.style.width) * 4) : [100, 120, 180]
  }
  for (const item of headerColumnMap(table).cells) item.cell.getBoundingClientRect = () => {
    const ws = widths(), left = ws.slice(0, item.start).reduce((a, b) => a + b, 0) * scale
    const width = ws.slice(item.start, item.end).reduce((a, b) => a + b, 0) * scale
    return { left, right: left + width, width }
  }
  const stop = startTableColumnResize(doc)
  function pointer(type, x, target = doc, id = 1) {
    const event = new win.Event(type, { bubbles: true, cancelable: true })
    Object.assign(event, { clientX: x, button: 0, pointerId: id }); target.dispatchEvent(event)
  }
  return { win, doc, table, widths, pointer, stop: () => { stop(); win.close() } }
}

test('adjacent columns compensate exactly, including narrow columns and extreme drags', () => {
  for (const original of [[100,120,180], [18,20,500]]) for (const delta of [-10000,-8,0,40,10000]) {
    const result = resizeColumnPair(original, 0, delta)
    assert.equal(result.reduce((a,b)=>a+b), original.reduce((a,b)=>a+b))
    assert.equal(result[2], original[2]); assert.ok(result[0] > 0 && result[1] > 0)
  }
})

test('grouped headers resolve employee rowspan plus individual day columns', () => {
  const f = fixture({ grouped: true })
  assert.equal(headerColumnMap(f.table).count, 3)
  assert.deepEqual(headerColumnMap(f.table).boundaries.map(item => item.cell.textContent), ['Nhân viên','01'])
  assert.equal(f.table.querySelectorAll('.vera-column-resize-handle').length, 2)
  f.stop()
})

for (const scale of [1, .85, .75]) test(`pointer drag preserves table width and data at scale ${scale}`, () => {
  const f = fixture({ scale }), grip = f.table.querySelector('.vera-column-resize-handle')
  f.pointer('pointerdown', 100 * scale, grip)
  f.pointer('pointermove', 140 * scale)
  assert.deepEqual(f.widths(), [140,80,180]); assert.equal(f.table.style.width, '400px')
  f.pointer('pointermove', 9999, f.doc, 2) // Other fingers cannot change this drag.
  assert.deepEqual(f.widths(), [140,80,180])
  f.pointer('pointerup', 140 * scale)
  assert.equal(f.doc.querySelector('input').value, 'Không thay đổi')
  assert.equal(f.doc.body.classList.contains('vera-column-resizing'), false)
  f.stop()
})

test('cancel restores original colgroup, styles and listener state', () => {
  const f = fixture({ colgroup: true }), original = f.table.getAttribute('style')
  f.pointer('pointerdown',100,f.table.querySelector('.vera-column-resize-handle')); f.pointer('pointermove',150)
  f.pointer('pointercancel',150)
  assert.deepEqual(f.widths(),[100,120,180]); assert.equal(f.table.getAttribute('style'), original)
  assert.equal(f.table.classList.contains('vera-columns-sized'), false)
  f.stop(); assert.equal(f.table.querySelectorAll('col').length,3)
})

test('keyboard resizes; Escape cancels drag without closing the caller dialog', () => {
  const f = fixture(), grip = f.table.querySelector('.vera-column-resize-handle')
  grip.dispatchEvent(new f.win.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}))
  assert.ok(f.widths().every((value,index)=>Math.abs(value-[108,112,180][index])<1e-6))
  f.pointer('pointerdown',100,grip); f.pointer('pointermove',150)
  let escaped = false; f.doc.addEventListener('keydown',()=>{escaped=true})
  grip.dispatchEvent(new f.win.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))
  assert.equal(escaped,false); assert.ok(f.widths().every((value,index)=>Math.abs(value-[108,112,180][index])<1e-6)); f.stop()
})

test('dynamically mounted dialog tables get grips and unmount safely during a drag', async () => {
  const f = fixture(), dialog = f.doc.createElement('dialog')
  dialog.innerHTML = '<table><thead><tr><th>X</th><th>Y</th></tr></thead></table>'; f.doc.body.append(dialog)
  await new Promise(resolve => f.win.setTimeout(resolve,35))
  assert.equal(dialog.querySelectorAll('.vera-column-resize-handle').length,1)
  f.pointer('pointerdown',100,f.table.querySelector('.vera-column-resize-handle')); f.table.remove()
  await new Promise(resolve => f.win.setTimeout(resolve,35))
  assert.equal(f.doc.body.classList.contains('vera-column-resizing'),false)
  f.stop()
})

test('viewport resize releases fixed pixels so existing responsive CSS can fit again', () => {
  const f = fixture();f.pointer('pointerdown',100,f.table.querySelector('.vera-column-resize-handle'));f.pointer('pointermove',140);f.pointer('pointerup',140)
  f.win.dispatchEvent(new f.win.Event('resize'))
  assert.equal(f.table.classList.contains('vera-columns-sized'),false)
  assert.equal(f.table.querySelector('colgroup'),null);f.stop()
})

test('React-style header replacement installs one set of grips and restores sizing', async () => {
  const f=fixture(); f.pointer('pointerdown',100,f.table.querySelector('.vera-column-resize-handle'));f.pointer('pointermove',140);f.pointer('pointerup',140)
  f.table.tHead.innerHTML='<tr><th>Updated</th><th>Second</th></tr>'
  await new Promise(resolve=>f.win.setTimeout(resolve,35))
  assert.equal(f.table.querySelectorAll('.vera-column-resize-handle').length,1)
  assert.equal(f.table.querySelector('colgroup'),null)
  assert.equal(f.doc.querySelector('input').value,'Không thay đổi');f.stop()
})

const savedWidths = f => Object.entries(f.win.localStorage)
test('completed drag survives fresh document and viewport resize, separately per table', () => {
  const first=fixture({identity:'training-trained'})
  first.pointer('pointerdown',100,first.table.querySelector('.vera-column-resize-handle'));first.pointer('pointermove',140);first.pointer('pointerup',140)
  const saved=savedWidths(first);assert.equal(saved.length,1);first.stop()
  const next=fixture({identity:'training-trained',saved})
  assert.deepEqual(next.widths(),[140,80,180])
  next.win.dispatchEvent(new next.win.Event('resize'))
  assert.deepEqual(next.widths(),[140,80,180]);next.stop()
  const other=fixture({identity:'training-untrained',saved});assert.deepEqual(other.widths(),[100,120,180]);other.stop()
})
test('keyboard persists but canceled drag never overwrites saved widths', () => {
  const f=fixture({identity:'keyboard'}),grip=f.table.querySelector('.vera-column-resize-handle')
  grip.dispatchEvent(new f.win.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}))
  const saved=savedWidths(f)
  f.pointer('pointerdown',100,grip);f.pointer('pointermove',160);f.pointer('pointercancel',160)
  assert.deepEqual(savedWidths(f),saved);f.stop()
  const next=fixture({identity:'keyboard',saved})
  assert.ok(next.widths().every((w,i)=>Math.abs(w-[108,112,180][i])<1e-6));next.stop()
})
test('corrupt saved preference is ignored without breaking resize', () => {
  const f=fixture({identity:'broken'})
  f.pointer('pointerdown',100,f.table.querySelector('.vera-column-resize-handle'));f.pointer('pointerup',100)
  const saved=savedWidths(f).map(([key])=>[key,'[null,-1,2]']);f.stop()
  const next=fixture({identity:'broken',saved});assert.deepEqual(next.widths(),[100,120,180]);next.stop()
})
