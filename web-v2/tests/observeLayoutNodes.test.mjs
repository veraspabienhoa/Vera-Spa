import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import { observeLayoutNodes } from '../src/lib/observeLayoutNodes.js'

test('identity observer processes inserted subtrees, not unrelated timer text or the entire board',async()=>{
 const dom=new JSDOM('<main>'+Array.from({length:1000},(_,i)=>`<button data-ui-key="u-${i}">0</button>`).join('')+'</main>',{pretendToBeVisual:true})
 const root=dom.window.document.querySelector('main'),calls=[]
 const stop=observeLayoutNodes(root,nodes=>calls.push(nodes),dom.window)
 try{
  assert.equal(calls[0].length,1000)
  root.firstChild.textContent='1'
  await new Promise(resolve=>dom.window.setTimeout(resolve,30))
  assert.equal(calls.length,1)
  const next=dom.window.document.createElement('section');next.innerHTML='<button data-ui-key="new">New</button>'
  root.appendChild(next)
  await new Promise(resolve=>dom.window.setTimeout(resolve,30))
  assert.equal(calls.length,2);assert.equal(calls[1].length,1)
  assert.equal(calls[1][0].dataset.uiKey,'new')
  const inspector=dom.window.document.createElement('div');inspector.className='layout-designer';inspector.innerHTML='<button data-ui-key="private">Tool</button>';root.appendChild(inspector)
  await new Promise(resolve=>dom.window.setTimeout(resolve,30))
  assert.equal(calls.length,2)
 }finally{stop();dom.window.close()}
})
