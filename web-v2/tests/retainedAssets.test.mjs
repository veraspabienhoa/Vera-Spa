import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { build } from 'vite'
import retainAssets from '../build/retainAssets.js'
import { isPageLoadFailure, hasNewPageBuild } from '../src/lib/pageLoadFailure.js'

test('real build retains old dependency graph and CSS without renewing expired files', async () => {
 const root = await mkdtemp(join(tmpdir(), 'vera-assets-')), now = 1800000000000
 const previous = join(root, 'previous')
 try {
  await mkdir(join(previous, 'assets'), { recursive: true })
  for (const [name, content] of Object.entries({ 'Page-old.js': 'import "./shared-old.js"', 'shared-old.js': 'export const v=1', 'Page-old.css': 'body{}', 'expired.js': 'old', 'private.js.map': 'source' })) await writeFile(join(previous, 'assets', name), content)
  await writeFile(join(previous, 'asset-history.json'), JSON.stringify({ 'assets/expired.js': now - 8 * 86400000, 'assets/Page-old.js': now - 86400000 }))
  await writeFile(join(root, 'index.html'), '<script type="module" src="/main.js"></script>')
  await writeFile(join(root, 'main.js'), 'console.log("current")')
  const { output } = await build({ root, configFile: false, logLevel: 'silent', plugins: [retainAssets({ previousDir: previous, now })], build: { write: false } })
  const files = new Map(output.map(file => [file.fileName, file]))
  assert.equal(String(files.get('assets/Page-old.js').source), 'import "./shared-old.js"')
  assert.ok(files.has('assets/shared-old.js')); assert.ok(files.has('assets/Page-old.css'))
  assert.equal(files.has('assets/expired.js'), false); assert.equal(files.has('assets/private.js.map'), false)
  const history = JSON.parse(files.get('asset-history.json').source)
  assert.equal(history['assets/Page-old.js'], now - 86400000)
 } finally { await rm(root, { recursive: true, force: true }) }
})
test('module failures and new builds are distinguished from render errors and offline checks', async () => {
 for (const message of ['Failed to fetch dynamically imported module', 'Importing a module script failed.', 'Unable to preload CSS for /assets/page.css']) assert.equal(isPageLoadFailure(Error(message)), true)
 assert.equal(isPageLoadFailure(Error('Cannot read properties of undefined')), false)
 const browser = { location: { href: 'https://example.test/' }, document: { querySelectorAll: () => [{ src: 'https://example.test/assets/index-old.js' }] } }
 const response = entry_script => async () => ({ ok: true, json: async () => ({ entry_script }) })
 assert.equal(await hasNewPageBuild(browser, response('/assets/index-new.js')), true)
 assert.equal(await hasNewPageBuild(browser, response('/assets/index-old.js')), false)
 assert.equal(await hasNewPageBuild(browser, response('https://evil.test/a.js')), false)
 assert.equal(await hasNewPageBuild(browser, async () => { throw Error('offline') }), false)
})
