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
 assert.equal(doc.querySelectorAll('thead th').length,4)
 assert.deepEqual([...doc.querySelectorAll('tbody tr')].map(tr=>[...tr.children].map(td=>td.textContent)),[['1','A','1','B'],['2','C','','']])
 assert.equal(doc.querySelector('tfoot').textContent,'Tổng2 nhân viênTổng1 nhân viên')
 assert.equal(render([]).querySelector('tfoot').textContent,'Tổng0 nhân viênTổng0 nhân viên')
})
