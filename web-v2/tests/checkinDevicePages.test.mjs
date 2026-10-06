import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { MessageChannel } from 'node:worker_threads'

const built = await build({ stdin: { contents: "import React, { act } from 'react'; import { createRoot } from 'react-dom/client'; import History from './src/pages/CheckinHistoryPage'; import Devices from './src/pages/DevicePage'; window.testAct = act; window.mountPage = kind => { window.pageRoot = createRoot(document.getElementById('root')); window.pageRoot.render(kind === 'history' ? <History user={{ permissions: { device_facegate_mapping_manage: true, device_facegate_ip_manage: true } }} /> : <Devices user={{ permissions: { device_view: true, device_manage: true, device_station_operate: true, device_checkin_confirm: true, device_facegate_ip_manage: true } }} />); };", resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' }, plugins: [{ name: 'mock-api', setup(b) {
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
  assert.equal(button(dom, 'Xuất excel').disabled, false)
  await dom.window.testAct(async () => button(dom, 'Xuất excel').click())
  assert.equal(exported.source, 'facegate_saved')
  await dom.window.testAct(async () => button(dom, 'Hôm qua').click())
  assert.equal(button(dom, 'Xuất excel').disabled, true)
  fail = true; await dom.window.testAct(async () => button(dom, 'Xem lịch sử').click())
  assert.match(dom.window.document.querySelector('[role=alert]').textContent, /Unavailable/)
  assert.equal(button(dom, 'Xuất excel').disabled, true)
})

test('history reloads the selected dates directly from the FaceGate device', async (context) => {
  const queries = []
  const dom = await page('history', { checkinHistory: async query => {
    queries.push(query)
    return { records: [{ event_id: 27, occurred_at: '2026-10-02T09:15:00+07:00' }], options: { statuses: ['1'], types: ['0'] } }
  } }, context)
  await dom.window.testAct(async () => button(dom, 'Tải lại dữ liệu từ máy Face ID').click())
  assert.equal(queries.length, 1)
  assert.equal(queries[0].source, 'facegate')
  assert.ok(queries[0].start)
  assert.ok(queries[0].end)
  assert.match(dom.window.document.querySelector('.checkin-history-page').textContent, /đọc trực tiếp từ máy/)
  assert.equal(button(dom, 'Tải lại dữ liệu từ máy Face ID').disabled, false)
})

test('history follows the six-field order and reloads without updating device IP', async (context) => {
  let writes = 0
  let queried
  const dom = await page('history', {
    deviceRegistry: async () => { throw Error('History must not read registry') },
    saveDeviceRegistry: async () => { writes += 1 },
    checkinHistory: async query => { queried = query; return { records: [], options: { statuses: [], types: [] } } },
  }, context)
  const labels = [...dom.window.document.querySelectorAll('.checkin-filter-details > label')].map(el => el.firstChild.textContent)
  assert.deepEqual(labels, ['Ngày cụ thể', 'Nguồn dữ liệu', 'Loại sự kiện', 'Tên / mã nhân viên', 'Mã sự kiện', 'Trạng thái'])
  assert.doesNotMatch(dom.window.document.querySelector('.checkin-filters').textContent, /IP Face ID/)
  await dom.window.testAct(async () => button(dom, 'Tải lại dữ liệu từ máy Face ID').click())
  assert.equal(writes, 0)
  assert.equal(queried.source, 'facegate')
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


test('history typing suggests employee names/codes and event IDs, with independent clear buttons', async context => {
  const queries = []
  const dom = await page('history', { checkinHistory: async query => {
    queries.push(query)
    return { records: [{ event_id: 80351, employee_name: 'Mạnh Đạt', employee_code: '42', device_name: 'Vu Manh Dat', occurred_at: '2026-10-06T10:10:43+07:00' }], options: { statuses: [], types: [] } }
  } }, context)
  const doc = dom.window.document
  const input = async (node, value) => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(node, value)
    await dom.window.testAct(() => node.dispatchEvent(new dom.window.Event('input', { bubbles: true })))
  }
  const employee = doc.querySelector('[aria-label="Tên / mã nhân viên"]')
  await input(employee, '42')
  await dom.window.testAct(async () => { await new Promise(resolve => dom.window.setTimeout(resolve, 230)) })
  assert.equal(queries.length, 1); assert.equal(queries[0].employee, '')
  const choice = [...doc.querySelectorAll('[role=option]')].find(node => node.textContent.includes('Mạnh Đạt'))
  assert.ok(choice)
  await dom.window.testAct(() => choice.click()); assert.equal(employee.value, 'Mạnh Đạt')
  const eventId = doc.querySelector('[aria-label="Mã sự kiện"]')
  await input(eventId, '803')
  assert.ok([...doc.querySelectorAll('[role=option]')].some(node => node.textContent.includes('80351')))
  await dom.window.testAct(() => doc.querySelector('[aria-label="Clear Mã sự kiện"]').click())
  assert.equal(eventId.value, ''); assert.equal(employee.value, 'Mạnh Đạt')
  await dom.window.testAct(() => doc.querySelector('[aria-label="Clear Tên / mã nhân viên"]').click())
  assert.equal(employee.value, ''); assert.equal(doc.querySelector('[role=listbox]'), null)
  assert.equal(queries.length, 1)
})


test('history reports configured attendance source without claiming every log is payroll eligible',async context=>{
 let policy={source:'facegate',effective_date:'2026-09-29'}
 const dom=await page('history',{checkinHistory:async()=>({records:[],attendance_policy:policy})},context)
 const reload=async()=>dom.window.testAct(async()=>button(dom,'Xem lịch sử').click())
 await reload()
 assert.match(dom.window.document.body.textContent,/FaceGate là nguồn chấm công từ 29-09-2026/)
 assert.match(dom.window.document.body.textContent,/số sự kiện ở đây không phải số ngày công/)
 assert.doesNotMatch(dom.window.document.body.textContent,/chưa dùng tính công/)
 policy={source:'timesoft'};await reload()
 assert.match(dom.window.document.body.textContent,/Nguồn tính công hiện tại là TimeSoft/)
 policy={source:'unknown'};await reload()
 assert.match(dom.window.document.body.textContent,/Xem nguồn tính công hiện tại tại Quản lý thiết bị/)
})
