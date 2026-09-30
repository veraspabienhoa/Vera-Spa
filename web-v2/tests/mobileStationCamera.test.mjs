import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'

const built = await build({
  stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Panel from './src/pages/MobileStationPanel';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=()=>act(async()=>root.render(<Panel registry={{revision:1,devices:[]}} canRegister={false}/>));window.unmount=()=>act(async()=>root.unmount());`, resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' },
  plugins: [{ name: 'api', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'mock' }))
    b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: 'export const veraApi={mobileStationEvents:async()=>({records:[]})}' }))
  } }],
})

test('switching front and rear cameras stops the previous stream and mirrors the front preview', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window
  const requests = []
  w.IS_REACT_ACT_ENVIRONMENT = true
  w.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  w.HTMLMediaElement.prototype.play = async () => {}
  Object.defineProperty(w.navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: async constraints => {
    const request = { mode: constraints.video.facingMode.ideal, stopped: false }
    requests.push(request)
    return { getTracks: () => [{ stop: () => { request.stopped = true } }] }
  } } })
  try {
    w.eval(built.outputFiles[0].text)
    await w.mount()
    const button = label => [...w.document.querySelectorAll('button')].find(node => node.textContent.trim() === label)
    assert.equal(button('Camera sau').getAttribute('aria-pressed'), 'true')
    await w.act(async () => button('Bật camera').click())
    assert.deepEqual(requests.map(item => item.mode), ['environment'])
    await w.act(async () => button('Camera trước').click())
    assert.deepEqual(requests.map(item => item.mode), ['environment', 'user'])
    assert.equal(requests[0].stopped, true)
    assert.equal(button('Camera trước').getAttribute('aria-pressed'), 'true')
    assert.equal(w.document.querySelector('video').style.transform, 'scaleX(-1)')
    await w.act(async () => button('Tắt camera').click())
    assert.equal(requests[1].stopped, true)
    assert.equal(w.document.querySelector('video'), null)
  } finally { if (w.unmount) await w.unmount(); w.close() }
})
