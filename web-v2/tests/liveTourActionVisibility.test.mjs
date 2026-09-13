import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const result = await build({ entryPoints: ['src/components/LiveTourServiceActions.jsx'], bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic', external: ['react'], loader: { '.css': 'empty' } })
const module = { exports: {} }
new Function('require', 'module', 'exports', result.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
const render = props => renderToStaticMarkup(React.createElement(module.exports.default, { target: 'Nhân viên', ...props }))

test('active service can finish even when a new booking cannot start', () => {
  const html = render({ canStart: false, waiting: 1, doing: 1 })
  assert.match(html, /Hoàn thành/)
  assert.doesNotMatch(html, /Thực hiện/)
  assert.doesNotMatch(render({ canStart: false, waiting: 1 }), /<button/)
})

test('idle → booked → doing → completed exposes only the applicable actions', () => {
  assert.doesNotMatch(render({}), /<button/)
  const waiting = render({ waiting: 1 })
  assert.match(waiting, /Thực hiện/)
  assert.doesNotMatch(waiting, /Hoàn thành/)
  const doing = render({ doing: 1 })
  assert.match(doing, /Hoàn thành/)
  assert.doesNotMatch(doing, /Thực hiện/)
  assert.doesNotMatch(render({ waiting: 0, doing: 0 }), /<button/)
})
test('mixed room supports both actions, busy buttons cannot run again', () => {
  const html = render({ room: true, waiting: 2, doing: 1, busy: true })
  assert.equal((html.match(/<button/g) || []).length, 2)
  assert.equal((html.match(/disabled=""/g) || []).length, 2)
})
