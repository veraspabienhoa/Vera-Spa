import test from 'node:test'
import assert from 'node:assert/strict'
import { flowDrop } from '../src/lib/layoutFlowDrop.js'
const box = (x,y) => ({getBoundingClientRect:()=>({left:x,top:y,right:x+80,bottom:y+40,width:80,height:40})})
test('inserts across wrapped rows and in whitespace using visible row geometry',()=>{
 const a=box(0,0),b=box(100,0),c=box(0,60),d=box(100,60), peers=[a,b,c,d]
 assert.equal(flowDrop(peers,90,20).before,b)
 assert.equal(flowDrop(peers,5,75).before,c)
 assert.equal(flowDrop(peers,90,75).before,d)
 assert.equal(flowDrop(peers,200,75).before,null)
 assert.equal(flowDrop(peers,200,20).before,c)
 assert.deepEqual(flowDrop(peers,5,75).line,{x:0,y:60,width:2,height:40})
})
test('vertical groups and empty destinations',()=>{
 const a=box(0,0),b=box(0,60)
 assert.equal(flowDrop([a,b],40,50,true).before,b)
 assert.deepEqual(flowDrop([],0,0),{before:null,line:null})
})
