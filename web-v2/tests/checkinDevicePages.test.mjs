import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { MessageChannel } from 'node:worker_threads'

const built = await build({ stdin: { contents: "import React, { act } from 'react'; import { createRoot } from 'react-dom/client'; import History from './src/pages/CheckinHistoryPage'; import Devices from './src/pages/DevicePage'; window.testAct = act; window.mountPage = kind => { window.pageRoot = createRoot(document.getElementById('root')); window.pageRoot.render(kind === 'history' ? <History user={{ permissions: { device_facegate_mapping_manage: true } }} /> : <Devices user={{ permissions: { device_view: true, device_manage: true, device_station_operate: true, device_checkin_confirm: true, device_facegate_ip_manage: true } }} />); };", resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' }, plugins: [{ name: 'mock-api', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'mock' }))
  b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: 'export const veraApi = window.testApi;', loader: 'js' }))
} }] })
async function page(kind, api, context) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  const channels = []
  dom.window.MessageChannel = class extends MessageChannel {
    constructor() { super(); channels.push(this) }
  }
  context.after(async () => {
    try { if (dom.window.pageRoot) await dom.window.testAct(async () => dom.window.pageRoot.unmount()) }
    finally { for (const channel of channels) { channel.port1.close(); channel.port2.close() }; dom.window.close() }
  })
  dom.window.IS_REACT_ACT_ENVIRONMENT = true
  dom.window.testApi = api
  dom.window.HTMLElement.prototype.scrollIntoView = () => {}
  dom.window.eval(built.outputFiles[0].text)
  await dom.window.testAct(async () => dom.window.mountPage(kind))
  return dom
}
function button(dom, label) { return [...dom.window.document.querySelectorAll('button')].find(el => el.textContent.trim() === label) }

test('history exports applied filters, blocks stale export, and survives query failure', async (context) => {
  let exported
  let fail = false
  const dom = await page('history', { checkinHistory: async () => { if (fail) throw Error('Unavailable'); return { records: [{ event_id: 1, occurred_at: '2026-09-23T10:00:00+07:00' }], options: { statuses: [], types: [] } } }, exportCheckinHistory: async q => { exported = q } }, context)
  await dom.window.testAct(async () => button(dom, 'Xem lịch sử').click())
  assert.equal(button(dom, 'Xuất Excel').disabled, false)
  await dom.window.testAct(async () => button(dom, 'Xuất Excel').click())
  assert.equal(exported.source, 'facegate_saved')
  await dom.window.testAct(async () => button(dom, 'Hôm qua').click())
  assert.equal(button(dom, 'Xuất Excel').disabled, true)
  fail = true; await dom.window.testAct(async () => button(dom, 'Xem lịch sử').click())
  assert.match(dom.window.document.querySelector('[role=alert]').textContent, /Unavailable/)
  assert.equal(button(dom, 'Xuất Excel').disabled, true)
})

test('device page retries initial failure and can submit a new device without losing configured device', async (context) => {
  let fail = true, saved
  const data = { revision: 3, devices: [{ id: 'facegate-current', name: 'FaceGate', kind: 'faceid', adapter: 'facegate_server', enabled: true, connection: 'network' }], kinds: { faceid: 'FaceID', printer: 'Máy in' }, connections: { network: 'LAN', usb: 'USB' }, adapters: { facegate_server: { label: 'FaceGate', configured: true }, pending: { label: 'Chờ tích hợp' } } }
  const dom = await page('devices', { deviceRegistry: async () => { if(fail) throw Error('Unavailable'); return data }, saveDeviceRegistry: async body => { saved = body; return { ...data, devices: body.devices, revision: 4 } } }, context)
  assert.match(dom.window.document.querySelector('[role=alert]')?.textContent || '', /Unavailable/)
  fail = false; await dom.window.testAct(async () => button(dom, 'Tải lại danh sách').click())
  await dom.window.testAct(async () => button(dom, 'Thêm thiết bị').click())
  const input = dom.window.document.querySelector('.device-editor input')
  Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, 'Máy thử nghiệm')
  await dom.window.testAct(async () => input.dispatchEvent(new dom.window.Event('input', { bubbles: true })))
  await dom.window.testAct(async () => button(dom, 'Lưu thiết bị').click())
  assert.equal(saved.expected_revision, 3)
  assert.equal(saved.devices.length, 2)
  assert.equal(saved.devices[1].name, 'Máy thử nghiệm')
  assert.equal(saved.devices[1].adapter, 'pending')
})
