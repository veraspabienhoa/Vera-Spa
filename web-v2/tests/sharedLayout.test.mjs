import test from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import { layoutKey, layoutCss } from '../src/lib/sharedLayout.js'
import { transformSync } from '@babel/core'
import layoutIdentity from '../build/layoutIdentity.js'

test('layout identity is unique per menu item and independent of permission-filtered siblings', () => {
  const dom = new JSDOM('<div class="app-shell"><aside class="sidebar" data-vera-node="side"><nav data-vera-node="nav"><a data-vera-node="a" data-vera-item="leave">Lịch nghỉ</a><a data-vera-node="a" data-vera-item="settings">Cài đặt</a></nav></aside></div>')
  const [leave, settings] = dom.window.document.querySelectorAll('a')
  const key = layoutKey(settings, 'settings')
  assert.notEqual(key, layoutKey(leave, 'settings'))
  leave.remove()
  settings.textContent = 'New label'
  assert.equal(key, layoutKey(settings, 'live-tour'))
  dom.window.close()
})

test('layout CSS bounds width to its parent and rejects arbitrary selectors or values', () => {
  const css = layoutCss({ 'l-example': { width: 500, height: 80, order: 2, parent: 'l-parent' }, 'body} *{': { width: 500 }, 'l-bad': { width: '100px;color:red', order: -1 } })
  assert.match(css, /width:min\(500px,100%\)/)
  assert.match(css, /height:auto!important/)
  assert.match(css, /order:2!important/)
  assert.doesNotMatch(css, /color:red|body\}|order:-1/)
})

test('build gives native elements source identities and retains keyed list identities', () => {
  const code = 'const UI = () => <nav>{items.map(item => <button key={item.id}>{item.label}</button>)}</nav>'
  const result = transformSync(code, { filename: '/app/src/components/Example.jsx', parserOpts: { plugins: ['jsx'] }, plugins: [layoutIdentity], configFile: false, babelrc: false }).code
  assert.equal((result.match(/data-vera-node=/g) || []).length, 2)
  assert.match(result, /data-vera-item=\{item.id\}/)
  assert.equal(result, transformSync(code, { filename: '/another/src/components/Example.jsx', parserOpts: { plugins: ['jsx'] }, plugins: [layoutIdentity], configFile: false, babelrc: false }).code)
})

test('source identities survive added whitespace and comments', () => {
  const options = { filename: '/app/src/components/Example.jsx', parserOpts: { plugins: ['jsx'] }, plugins: [layoutIdentity], configFile: false, babelrc: false }
  const source = 'function Example(){return <section className="panel"><button>Lưu</button></section>}'
  const keys = code => [...transformSync(code, options).code.matchAll(/data-vera-node="([^"]+)"/g)].map(match => match[1])
  assert.deepEqual(keys(source), keys('\n// unrelated comment\n\n' + source))
})


test('alignment accepts only safe values and explicit gap overrides row defaults', () => {
  const css=layoutCss({'u-test':{text_align:'right',content_align:'center',justify_content:'space-evenly',align_items:'stretch',rows:2,gap:18}})
  assert.match(css,/text-align:right!important/)
  assert.match(css,/justify-content:space-evenly!important/)
  assert.ok(css.indexOf('gap:18px')>css.indexOf('gap:6px'))
  assert.doesNotMatch(layoutCss({'u-test':{text_align:'left;color:red',gap:-1}}),/color:red|gap:-1/)
})


test('visual styles are scoped, guard disabled states and reject CSS injection', () => {
  const css=layoutCss({'u-test':{appearance:{normal:{background:'#ffffff',gradient:'#f4f7f6',shadow:'raised'},hover:{text:'#14532d'},selected:{background:'#1b5e20'},radius:10,depth:3,hover_lift:2,press_sink:2,glass_blur:8}}})
  assert.match(css,/linear-gradient\(135deg/)
  assert.match(css,/prefers-reduced-motion:reduce/)
  assert.match(css,/:not\(:disabled/)
  assert.match(css,/aria-selected/)
  assert.match(css,/backdrop-filter:blur\(8px\)/)
  const bad=layoutCss({'u-test':{appearance:{normal:{background:'red;display:none',shadow:'url(https://bad)'},radius:900,font_family:'url(https://bad)'}}})
  assert.doesNotMatch(bad,/display:none|https:|900px/)
})

// Free position is independently bounded and cannot inject CSS.
test('free translation is scoped, bounded and composes with appearance transforms',()=>{
 const css=layoutCss({'l-free':{offset_x:-45,offset_y:90},'l-invalid':{offset_x:'1px;color:red',offset_y:9000}})
 assert.match(css,/translate:-45px 90px!important/)
 assert.doesNotMatch(css,/color:red|9000px/)
})

test('font sizes retain fractional and large values while rejecting invalid CSS', () => {
  for (const size of [0, 0.5, 8, 96, 4096]) {
    const css = layoutCss({'l-font':{font_size:size,appearance:{font_size:size,font_style:'italic',font_weight:700,font_family:'serif'}}})
    assert.ok(css.includes(`font-size:${size}px!important`))
    assert.ok(css.includes('font-style:italic!important'))
    assert.ok(css.includes('font-weight:700!important'))
  }
  for (const size of [-1, NaN, Infinity, '12;display:none']) {
    assert.ok(!layoutCss({'l-font':{font_size:size,appearance:{font_size:size,font_style:'bad'}}}).includes('font-size:'))
  }
})
