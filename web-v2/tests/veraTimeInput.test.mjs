import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built = await build({stdin:{contents:`import React,{act,useState} from 'react';import {createRoot} from 'react-dom/client';import Time from './src/components/VeraTimeInput';function App(){const [value,set]=useState('22:30');return <Time value={value} required onChange={e=>{window.saved=e.target.value;set(e.target.value)}}/>}const root=createRoot(document.getElementById('root'));window.act=act;window.mount=()=>act(()=>root.render(<App/>));window.unmount=()=>act(()=>root.unmount());`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'}})
test('time supports typing, rejects partial/stale values, and picks any minute in 24-hour format',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true});const w=dom.window;w.IS_REACT_ACT_ENVIRONMENT=true;w.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
 try {w.eval(built.outputFiles[0].text);await w.mount();const input=w.document.querySelector('input');
 const type=async value=>w.act(()=>{Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new w.Event('input',{bubbles:true}))})
 await type('0715');assert.equal(w.saved,'07:15');assert.equal(input.value,'07:15')
 await type('23:17');assert.equal(w.saved,'23:17');assert.equal(input.checkValidity(),true)
 await type('23:');assert.equal(w.saved,'');assert.equal(input.checkValidity(),false)
 await type('24:00');assert.equal(w.saved,'');assert.equal(input.checkValidity(),false)
 await type('00:00');assert.equal(w.saved,'00:00')
 await w.act(()=>w.document.querySelector('button').click());const selects=w.document.querySelectorAll('select');
 await w.act(()=>{selects[1].value='59';selects[1].dispatchEvent(new w.Event('change',{bubbles:true}))});assert.equal(w.saved,'00:59');assert.equal(input.value,'00:59')
 } finally {await w.unmount();w.close()}
})
