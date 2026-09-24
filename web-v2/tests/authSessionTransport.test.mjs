import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import { build } from 'esbuild'

const SESSION_KEY = 'vera-v2-api-auth-session'
const built = await build({
  stdin: { contents: "export * from './src/lib/supabase'; export { veraApi, isApiConfigured } from './src/lib/api';", resolveDir: process.cwd() },
  bundle: true, write: false, platform: 'node', format: 'cjs',
  define: { 'import.meta.env': 'fixtureEnv' },
  plugins: [{ name: 'no-external-auth', setup(b) {
    b.onResolve({ filter: /^@supabase\/supabase-js$/ }, () => ({ path: 'sdk', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const createClient = () => { throw new Error("Must not use Supabase Auth"); };' }))
  } }],
})

const session = (expiresIn = 3600, suffix = 'old') => ({
  access_token: `access-${suffix}`, refresh_token: `refresh-${suffix}`,
  expires_at: Math.floor(Date.now() / 1000) + expiresIn, user: { id: 'employee-test' },
})
const json = (status, payload) => new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })
function fixture({ initial = session(), env = { VITE_VERA_API_BASE_URL: 'https://api.veraspa.vn' }, fetch, fastTimers = false } = {}) {
  const storage = new Map(initial ? [[SESSION_KEY, JSON.stringify(initial)]] : [])
  const events = []
  const context = vm.createContext({
    module: { exports: {} }, fixtureEnv: env, fetch, Headers, AbortController, URLSearchParams,
    setTimeout: fastTimers ? (callback) => setTimeout(callback, 1) : setTimeout, clearTimeout,
    window: { localStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) }, addEventListener() {} },
  })
  context.exports = context.module.exports
  vm.runInContext(built.outputFiles[0].text, context)
  const api = context.module.exports
  api.onVeraAuthStateChange(event => events.push(event))
  return { ...api, storage, events }
}

for (const base of [undefined, '   ', ' https://staging.example.test/// ']) {
  test(`login and profile verification share normalized API base: ${JSON.stringify(base)}`, async () => {
    const urls = []
    const f = fixture({ initial: null, env: { VITE_VERA_API_BASE_URL: base }, fetch: async url => {
      urls.push(url)
      return json(200, url.endsWith('/login') ? session() : { employee_username: 'test' })
    } })
    assert.equal(f.isApiConfigured, true)
    await f.signInWithVeraPassword('test', 'test-password')
    await f.veraApi.me()
    const expected = base?.trim() ? 'https://staging.example.test' : 'https://api.veraspa.vn'
    assert.deepEqual(urls, [`${expected}/v2/auth/login`, `${expected}/v2/me`])
  })
}

for (const status of [429, 500, 502, 503, 504]) {
  test(`refresh HTTP ${status} preserves credentials and succeeds after recovery`, async () => {
    let recovered = false
    const f = fixture({ initial: session(-10), fetch: async () => recovered ? json(200, session(3600, 'new')) : json(status, { detail: 'temporarily unavailable' }) })
    await assert.rejects(f.getCurrentSession(), error => error.status === status)
    assert.equal(JSON.parse(f.storage.get(SESSION_KEY)).refresh_token, 'refresh-old')
    assert.deepEqual(f.events, [])
    recovered = true
    assert.equal((await f.getCurrentSession()).access_token, 'access-new')
  })
}

test('network refresh failure preserves stored credentials', async () => {
  const f = fixture({ fetch: async () => { throw new TypeError('Failed to fetch') } })
  await assert.rejects(f.refreshCurrentSession())
  assert.ok(f.storage.has(SESSION_KEY))
  assert.deepEqual(f.events, [])
})

for (const status of [401, 403]) {
  test(`confirmed refresh rejection ${status} clears even a not-yet-expired access token`, async () => {
    const f = fixture({ initial: session(60), fetch: async () => json(status, { detail: 'revoked' }) })
    assert.equal(await f.getCurrentSession(), null)
    assert.equal(f.storage.has(SESSION_KEY), false)
    assert.deepEqual(f.events, ['SIGNED_OUT'])
  })
}

test('profile 401 followed by refresh 503 propagates 503 without signing out', async () => {
  let calls = 0
  const f = fixture({ fastTimers: true, fetch: async url => {
    calls++
    return url.endsWith('/refresh') ? json(503, { detail: 'temporary outage' }) : json(401, { detail: 'access expired' })
  } })
  await assert.rejects(f.veraApi.me(), error => error.status === 503)
  assert.equal(calls, 2)
  assert.ok(f.storage.has(SESSION_KEY))
  assert.deepEqual(f.events, [])
})

test('profile retries once with the rotated token after access 401', async () => {
  const tokens = []
  const f = fixture({ fetch: async (url, options) => {
    if (url.endsWith('/refresh')) return json(200, session(3600, 'new'))
    tokens.push(options.headers.get('Authorization'))
    return tokens.length === 1 ? json(401, {}) : json(200, { employee_username: 'test' })
  } })
  assert.equal((await f.veraApi.me()).employee_username, 'test')
  assert.deepEqual(tokens, ['Bearer access-old', 'Bearer access-new'])
})

test('malformed successful refresh cannot replace a saved session', async () => {
  const f = fixture({ fetch: async () => json(200, {}) })
  await assert.rejects(f.refreshCurrentSession(), error => error.status === 502)
  assert.equal(JSON.parse(f.storage.get(SESSION_KEY)).refresh_token, 'refresh-old')
})

for (const operation of ['login', 'refresh', 'profile']) {
  test(`${operation} has a bounded timeout without deleting credentials`, async () => {
    const f = fixture({ fastTimers: true, fetch: (_url, options) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
    }) })
    const pending = operation === 'login' ? f.signInWithVeraPassword('test', 'test-password') : operation === 'refresh' ? f.refreshCurrentSession() : f.veraApi.me()
    let watchdog
    try {
      await assert.rejects(Promise.race([pending, new Promise((_resolve, reject) => { watchdog = setTimeout(() => reject(new Error('No request deadline')), 200) })]), error => error.code === 'VERA_API_TIMEOUT')
      assert.ok(f.storage.has(SESSION_KEY))
    } finally { clearTimeout(watchdog) }
  })
}

test('late refresh after logout cannot restore a session', async () => {
  let finish
  const f = fixture({ fetch: url => url.endsWith('/refresh') ? new Promise(resolve => { finish = resolve }) : Promise.resolve(json(200, {})) })
  const pending = f.refreshCurrentSession()
  await f.signOutVera()
  finish(json(200, session(3600, 'new')))
  assert.equal(await pending, null)
  assert.equal(f.storage.has(SESSION_KEY), false)
})

test('concurrent refresh calls share one request', async () => {
  let calls = 0
  const f = fixture({ fetch: async () => { calls++; return json(200, session(3600, 'new')) } })
  const results = await Promise.all([f.refreshCurrentSession(), f.refreshCurrentSession()])
  assert.equal(calls, 1)
  assert.ok(results.every(value => value.access_token === 'access-new'))
})

test('a late rejected refresh cannot clear a newer login', async () => {
  let finish
  const f = fixture({ fetch: url => url.endsWith('/refresh') ? new Promise(resolve => { finish = resolve }) : Promise.resolve(json(200, session(3600, 'new'))) })
  const pending = f.refreshCurrentSession()
  await f.signInWithVeraPassword('test', 'test-password')
  finish(json(401, { detail: 'old token rejected' }))
  assert.equal((await pending).refresh_token, 'refresh-new')
  assert.equal(JSON.parse(f.storage.get(SESSION_KEY)).refresh_token, 'refresh-new')
  assert.deepEqual(f.events, ['SIGNED_IN'])
})

test('valid access token remains usable during proactive refresh outage', async () => {
  const f = fixture({ initial: session(60), fetch: async () => json(503, {}) })
  assert.equal((await f.getCurrentSession()).access_token, 'access-old')
  assert.ok(f.storage.has(SESSION_KEY))
})

test('successful non-JSON profile response is recoverable, not an auth rejection', async () => {
  const f = fixture({ fetch: async () => new Response('<html>proxy</html>', { status: 200 }) })
  await assert.rejects(f.veraApi.me(), error => error.status === 502)
  assert.ok(f.storage.has(SESSION_KEY))
})

test('timeout also bounds a stalled response body', async () => {
  const f = fixture({ fastTimers: true, fetch: async (_url, options) => ({
    ok: true, status: 200, json: () => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
    }),
  }) })
  await assert.rejects(f.refreshCurrentSession(), error => error.code === 'VERA_API_TIMEOUT')
  assert.ok(f.storage.has(SESSION_KEY))
})

test('image download refreshes rejected access once and uses the new token', async () => {
  const tokens = []
  const f = fixture({ fetch: async (url, options) => {
    if (url.endsWith('/refresh')) return json(200, session(3600, 'new'))
    tokens.push(options.headers.get('Authorization'))
    return tokens.length === 1 ? json(401, { detail: 'expired' }) : new Response('bitmap', { headers: { 'Content-Type': 'image/bmp' } })
  } })
  const blob = await f.veraApi.facegateCaptureImage({ file_type: 2, file_index: 1, file_position: 1, time: '2026-09-23/18:16:43' })
  assert.equal(blob.type, 'image/bmp')
  assert.deepEqual(tokens, ['Bearer access-old', 'Bearer access-new'])
})

test('binary refresh 503 preserves session and is not hidden by original 401', async () => {
  let calls = 0
  const f = fixture({ fetch: async url => { calls++; return url.endsWith('/refresh') ? json(503, { detail: 'temporary' }) : json(401, {}) } })
  await assert.rejects(f.veraApi.facegateCaptureImage({}), error => error.status === 503)
  assert.equal(calls, 2)
  assert.ok(f.storage.has(SESSION_KEY))
})
