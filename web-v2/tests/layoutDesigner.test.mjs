import test from 'node:test'
import { readFileSync } from 'node:fs'
const registry = JSON.parse(readFileSync(new URL('../../vera_ui_registry.json', import.meta.url)))
const labelKey = Object.keys(registry).find(key => registry[key].tag === 'button' && registry[key].label && !registry[key].locked)
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const built = await build({ entryPoints: [fileURLToPath(new URL('../src/components/LayoutDesigner.jsx', import.meta.url))], bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime'], loader: { '.css': 'empty' }, plugins: [{ name: 'api', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi=globalThis.__layoutApi', loader: 'js' }))
} }] })

test('Admin drags within a group, saves desktop only, and another user receives the layout without edit controls', async () => {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true, url:'https://test.invalid' })
  const names = ['window','document','navigator','getComputedStyle','MutationObserver','localStorage','IS_REACT_ACT_ENVIRONMENT','__layoutApi']
  const previous = Object.fromEntries(names.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const key of ['window','document','navigator','getComputedStyle','MutationObserver','localStorage']) Object.defineProperty(globalThis,key,{ value: key === 'window' ? dom.window : dom.window[key], configurable:true })
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  let server = { revision: 0, layout: { desktop: {}, mobile: { 'l-mobile': { width: 80 } } } }, actionCalls = 0
  const writes = []
  globalThis.__layoutApi = { uiLayout: async () => structuredClone(server), saveUiLayout: async body => { writes.push(body); server = { revision: 1, layout: { ...server.layout, [body.device]: body.items } }; return structuredClone(server) } }
  const module = { exports: {} }
  new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
  const Designer = module.exports.default
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.querySelector('#root'))
  let closeCalls = 0
  const screen = (role, open = false) => React.createElement('div', { className:'app-shell' }, React.createElement('nav',{ className:'page-content','data-vera-node':'nav',style:{display:'flex'} }, ['first','second'].map(id => React.createElement('button',{ key:id, id,'data-ui-key':id === 'first' ? labelKey : undefined,'data-vera-node':'button','data-vera-item':id,onClick:()=>actionCalls++ },id))),React.createElement(Designer,{user:{role},page:'settings',open,onClose:()=>{closeCalls++;root.render(screen(role,false))}}))
  const click = async text => act(async () => [...document.querySelectorAll('.layout-designer button')].find(el=>el.textContent.includes(text)).click())
  try {
    await act(async()=>root.render(screen('admin')))
    assert.equal(document.querySelector('.layout-designer'),null,'closed by default')
    await act(async()=>root.render(screen('admin',true)))
    const panel=document.querySelector('.layout-designer')
    panel.getBoundingClientRect=()=>({width:360,height:500,left:10,top:10})
    await act(()=>document.querySelector('[aria-label="Di chuyển bảng công cụ"]').dispatchEvent(new window.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true})))
    assert.equal(JSON.parse(localStorage.getItem('vera-layout-panel-frame-v1')).left,15)
    await act(()=>document.querySelector('[aria-label="Kéo đổi kích thước bảng công cụ"]').dispatchEvent(new window.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,shiftKey:true})))
    assert.equal(JSON.parse(localStorage.getItem('vera-layout-panel-frame-v1')).width,380)
    await click('Chỉnh giao diện')
    const first=document.querySelector('#first'), second=document.querySelector('#second')
    document.elementFromPoint=()=>second
    await act(()=>first.dispatchEvent(new window.MouseEvent('pointerdown',{bubbles:true,clientX:1,clientY:1})))
    await act(()=>first.click())
    assert.equal(actionCalls,0,'editing must not trigger business actions')
    await act(()=>document.dispatchEvent(new window.MouseEvent('pointerup',{bubbles:true,clientX:100,clientY:1})))
    await click('Lưu cho tất cả')
    assert.equal(writes.length,1)
    assert.equal(writes[0].device,'desktop')
    assert.equal(writes[0].items[first.dataset.layoutKey].order,1)
    assert.equal(writes[0].items[second.dataset.layoutKey].order,0)
    assert.deepEqual(server.layout.mobile,{'l-mobile':{width:80}})
    await click('Hiệu ứng')
    await click('Chỉnh giao diện')
    await act(()=>first.dispatchEvent(new window.MouseEvent('pointerdown',{bubbles:true,clientX:1,clientY:1})))
    await click('Mẫu xanh 3D')
    assert.match(document.querySelector('style').textContent,/linear-gradient/)
    await click('Lưu cho tất cả')
    assert.equal(writes.at(-1).items[labelKey].appearance.depth,3)
    assert.deepEqual(server.layout.mobile,{'l-mobile':{width:80}})
    await click('Tên hiển thị')
    await click('Chỉnh giao diện')
    await act(()=>first.dispatchEvent(new window.MouseEvent('dblclick',{bubbles:true})))
    let editor=document.querySelector('[aria-label="Sửa tên trực tiếp"]')
    assert.ok(editor)
    editor.value='Tên mới'
    await act(()=>editor.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true})))
    assert.equal(document.querySelector('[aria-label="Sửa tên trực tiếp"]'),null)
    await act(()=>first.dispatchEvent(new window.MouseEvent('dblclick',{bubbles:true})))
    editor=document.querySelector('[aria-label="Sửa tên trực tiếp"]')
    editor.value='Tên dùng chung'
    await act(()=>editor.blur())
    await click('Lưu cho tất cả')
    assert.equal(writes.at(-1).items[labelKey].label,'Tên dùng chung')
    assert.equal(actionCalls,0)
    assert.deepEqual(server.layout.mobile,{'l-mobile':{width:80}})
    await click('Thêm / Xóa')
    await click('Chỉnh giao diện')
    await click('Thêm text')
    await act(()=>new Promise(resolve=>setTimeout(resolve,50)))
    const custom=document.querySelector('.layout-custom-text')
    assert.ok(custom)
    assert.equal(document.querySelector('textarea').value,'Nội dung mới')
    await click('Lưu cho tất cả')
    const customKey=Object.keys(writes.at(-1).items).find(key=>key.startsWith('l-custom-'))
    assert.equal(writes.at(-1).items[customKey].custom_kind,'text')
    await click('Chỉnh giao diện')
    await act(()=>custom.dispatchEvent(new window.MouseEvent('pointerdown',{bubbles:true,clientX:1,clientY:1})))
    window.confirm=()=>true
    await click('Xóa box/text')
    assert.equal(document.querySelector('.layout-custom-text'),null)
    await click('Lưu cho tất cả')
    assert.equal(writes.at(-1).items[customKey],undefined)
    await click('Đóng')
    assert.equal(closeCalls,1)
    assert.equal(document.querySelector('.layout-designer'),null)
    await act(()=>first.click())
    assert.equal(actionCalls,1,'closing restores business clicks')
    Object.defineProperty(window,'innerWidth',{value:390,configurable:true})
    await act(()=>window.dispatchEvent(new window.Event('resize')))
    await act(async()=>root.render(screen('admin',true)))
    assert.equal(document.querySelector('[aria-label="Chế độ giao diện"]').value,'desktop')
    await click('Đóng')
    assert.equal(document.querySelector('.layout-designer'),null)
    Object.defineProperty(window,'innerWidth',{value:1024,configurable:true})
    await act(()=>window.dispatchEvent(new window.Event('resize')))
    window.matchMedia=()=>({matches:true,addEventListener(){},removeEventListener(){}})
    await act(()=>window.dispatchEvent(new window.Event('resize')))
    await act(async()=>root.render(screen('admin',true)))
    assert.equal(document.querySelector('[aria-label="Chế độ giao diện"]').value,'desktop','Desktop remains default on resize and touch screens')
    await act(async()=>root.render(screen('nhanvien',true)))
    assert.equal(document.querySelector('.layout-designer'),null)
    assert.match(document.querySelector('style').textContent,/order:1!important/)
  } finally {
    await act(()=>root.unmount());dom.window.close()
    for(const [key,value]of Object.entries(previous)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key]}
  }
})
