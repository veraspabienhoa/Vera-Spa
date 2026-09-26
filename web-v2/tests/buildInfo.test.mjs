import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { build } from 'vite'
import buildInfo from '../build/buildInfo.js'

test('a real Vite build stamps the commit and the hashed entry used by HTML', async () => {
  const root = await mkdtemp(join(tmpdir(), 'vera-build-info-'))
  const revision = 'a'.repeat(40)
  try {
    await writeFile(join(root, 'index.html'), '<div id="root"></div><script type="module" src="/main.js"></script>')
    await writeFile(join(root, 'main.js'), 'document.getElementById("root").textContent="VERA"')
    const { output } = await build({ root, configFile: false, logLevel: 'silent', plugins: [buildInfo(revision)], build: { write: false } })
    const info = JSON.parse(output.find(item => item.fileName === 'build-info.json').source)
    const html = output.find(item => item.fileName === 'index.html').source
    assert.equal(info.revision, revision)
    assert.ok(output.some(item => item.type === 'chunk' && item.isEntry && `/${item.fileName}` === info.entry_script))
    assert.ok(html.includes(`src="${info.entry_script}"`))
    assert.deepEqual(Object.keys(info).sort(), ['entry_script', 'revision'])
  } finally { await rm(root, { recursive: true, force: true }) }
})
