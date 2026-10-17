import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { JSDOM } from 'jsdom'
test('weekly shift table has four columns, independent numbering and totals including fixed staff',async()=>{
 const built=await build({entryPoints:['src/components/WeeklyShiftTable.jsx'],bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',external:['react','react/jsx-runtime']})
 const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
 const render=rows=>new JSDOM(renderToStaticMarkup(React.createElement(mod.exports.default,{rows}))).window.document
 const doc=render([{name:'A',current:'Ca 1',fixed:true},{name:'B',current:'Ca 2'},{name:'C',current:'Ca 1'},{name:'D',current:'Chưa xếp'}])
 const tables=doc.querySelectorAll('table')
 assert.equal(tables.length,2)
 assert.equal(tables[0].querySelectorAll('thead tr:first-child th').length,4)
 assert.deepEqual([...tables[0].querySelectorAll('tbody tr')].map(tr=>[...tr.children].map(td=>td.textContent)),[['1','C','1','B']])
 assert.deepEqual([...tables[1].querySelectorAll('tbody tr')].map(tr=>[...tr.children].map(td=>td.textContent)),[['1','A','','']])
 assert.equal(tables[0].querySelector('.weekly-shift-totals').textContent,'Tổng1 nhân viênTổng1 nhân viên')
 assert.equal(tables[1].querySelector('.weekly-shift-totals').textContent,'Tổng1 nhân viênTổng0 nhân viên')
 assert.equal(doc.querySelectorAll('tfoot').length,0)
 assert.equal(render([]).querySelector('.weekly-shift-totals').textContent,'Tổng0 nhân viênTổng0 nhân viên')
})
