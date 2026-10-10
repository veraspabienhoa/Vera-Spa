// Offline synthetic interaction benchmark, not browser paint or API latency.
// Run from web-v2: node scripts/benchmark-date-input.mjs <baseline-git-ref>
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { performance } from 'node:perf_hooks'
import { build } from 'esbuild'
import React, { act, useState } from 'react'
import { JSDOM } from 'jsdom'

const baseline = process.argv[2] || 'origin/main'
const sourcePath = 'web-v2/src/components/VeraDateInput.jsx'
const sources = {
  baseline: execFileSync('git', ['show', `${baseline}:${sourcePath}`], { encoding: 'utf8' }),
  candidate: readFileSync('src/components/VeraDateInput.jsx', 'utf8'),
}
const dom = new JSDOM('<body><div id="root"></div><button id="outside">Outside</button></body>', { pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
globalThis.fetch = () => { throw new Error('Network is forbidden in this benchmark') }
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
const sampleCount = 30, syntheticCallbackMs = 6
const results = {}
for (const [label, contents] of Object.entries(sources)) {
  const built = await build({ stdin: { contents, resolveDir: `${process.cwd()}/src/components`, loader: 'jsx' },
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'] })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const DateInput = module.exports.default
  const result = {}
  for (const interaction of ['open_unchanged_date', 'type_then_blur']) {
    let callbacks = 0, explicitPickerOpens = 0
    const samples = [], root = createRoot(document.querySelector('#root'))
    function Form() {
      const [value, setValue] = useState('2026-10-10')
      return React.createElement(DateInput, { value, onChange: event => {
        callbacks++
        // Fixed simulated synchronous consumer cost, identical on both builds.
        const until = performance.now() + syntheticCallbackMs
        while (performance.now() < until) { /* synthetic work */ }
        setValue(event.target.value)
      } })
    }
    await act(() => root.render(React.createElement(Form)))
    const input = document.querySelector('input[type="text"]'), picker = document.querySelector('input[type="date"]')
    picker.showPicker = () => { explicitPickerOpens++ }
    for (let i = 0; i < sampleCount; i++) {
      await act(() => input.focus())
      const start = performance.now()
      if (interaction === 'type_then_blur') {
        await act(() => {
          Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, i % 2 ? '10102026' : '11102026')
          input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
        })
        await act(() => document.querySelector('#outside').focus())
      } else await act(() => { picker.focus(); picker.click() })
      samples.push(performance.now() - start)
    }
    samples.sort((a, b) => a - b)
    result[interaction] = { samples: sampleCount, callbacks, explicitPickerOpens,
      medianMs: +samples[Math.floor(sampleCount / 2)].toFixed(2), p95Ms: +samples[Math.floor(sampleCount * .95)].toFixed(2) }
    await act(() => root.unmount())
  }
  results[label] = result
}
dom.window.close()
console.log(JSON.stringify({ environment: 'Node + jsdom, no native popup rendering or network', baseline, syntheticCallbackMs, results }, null, 2))
