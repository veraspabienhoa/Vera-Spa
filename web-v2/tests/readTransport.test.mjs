import test from 'node:test'
import assert from 'node:assert/strict'
import { readJsonRequest } from '../src/lib/readTransport.js'

test('read deadline includes response body and never retries a timeout', async () => {
  let calls = 0
  const original = globalThis.fetch
  globalThis.fetch = async (_, {signal}) => {
    calls += 1
    return {json: () => new Promise((resolve,reject) => signal.addEventListener('abort', () => reject(new Error('aborted'))))}
  }
  try {
    await assert.rejects(readJsonRequest('/slow', {}, {timeoutMs:20}), error => error.name === 'TimeoutError')
    assert.equal(calls, 1)
  } finally {globalThis.fetch = original}
})

test('cancelled filter never sends or retries a request', async () => {
  const controller = new AbortController(); controller.abort()
  const original = globalThis.fetch
  globalThis.fetch = () => {throw new Error('must not fetch')}
  try {await assert.rejects(readJsonRequest('/old', {signal:controller.signal}), error => error.name === 'AbortError')}
  finally {globalThis.fetch = original}
})

test('HTTP failure is returned once for the caller to handle without storming server', async () => {
  const original = globalThis.fetch; let calls=0
  globalThis.fetch = async () => { calls+=1; return new Response('{"detail":"busy"}', {status:503}) }
  try {
    const result=await readJsonRequest('/busy')
    assert.equal(result.response.status,503); assert.equal(result.payload.detail,'busy'); assert.equal(calls,1)
  } finally {globalThis.fetch=original}
})
