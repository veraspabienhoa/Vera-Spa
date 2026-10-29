import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const require = createRequire(import.meta.url)
const built = await build({ entryPoints: ['src/components/RevenueEntryWindowPermission.jsx'], bundle:true, write:false, platform:'node', format:'cjs', jsx:'automatic', external:['react','react/jsx-runtime'] })
test('date-scope control offers all five choices, custom input, and preserves disabled state', async () => {
  const dom = new JSDOM('<body><div id="root"></div></body>')
  const names=['window','document','navigator','IS_REACT_ACT_ENVIRONMENT']
  const original=Object.fromEntries(names.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]))
  for(const [name,value] of Object.entries({window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true})) Object.defineProperty(globalThis,name,{configurable:true,writable:true,value})
  let root
  try {
    const module={exports:{}}
    new Function('require','module','exports',built.outputFiles[0].text)(require,module,module.exports)
    const {createRoot}=await import('react-dom/client')
    root=createRoot(document.getElementById('root'))
    const changes=[]
    const Component=module.exports.default
    await act(async()=>root.render(React.createElement(Component,{value:null,onChange:value=>changes.push(value)})))
    const select=document.querySelector('select')
    assert.deepEqual([...select.options].map(x=>x.value),['3','5','7','custom','all'])
    await act(async()=>{select.value='5';select.dispatchEvent(new window.Event('change',{bubbles:true}))})
    assert.equal(changes.at(-1),5)
    await act(async()=>{select.value='custom';select.dispatchEvent(new window.Event('change',{bubbles:true}))})
    assert.equal(changes.at(-1),1)
    assert.equal(document.querySelector('input[type="number"]').min,'1')
    await act(async()=>root.render(React.createElement(Component,{value:11,onChange:value=>changes.push(value),disabled:true})))
    assert.equal(document.querySelector('input[type="number"]').value,'11')
    assert.ok(document.querySelector('select').disabled)
  } finally {
    if(root) await act(async()=>root.unmount())
    dom.window.close()
    for(const name of names){if(original[name])Object.defineProperty(globalThis,name,original[name]);else delete globalThis[name]}
  }
})
