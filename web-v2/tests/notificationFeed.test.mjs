import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'

const built = await build({entryPoints:['src/lib/notificationFeed.js'],bundle:true,write:false,platform:'node',format:'cjs',plugins:[{name:'api',setup(b){b.onResolve({filter:/^\.\/api$/},()=>({path:'api',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const veraApi={notificationFeed(){throw Error("unused")}}'}))}}]})
const module={exports:{}}
new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
const {createNotificationFeed}=module.exports
const tick=()=>new Promise(resolve=>setImmediate(resolve))

test('inbox and popup share one poller; sign-out drops late responses and cached account data',async()=>{
  let starts=0, stops=0
  const requests=[], valuesA=[], valuesB=[]
  const feed=createNotificationFeed(()=>new Promise(resolve=>requests.push(resolve)),(load,options)=>{
    starts++;assert.equal(options.interval,60000);void load()
    return {refresh:load,stop(){stops++}}
  })
  const leaveA=feed.subscribe(value=>valuesA.push(value))
  const leaveB=feed.subscribe(value=>valuesB.push(value))
  assert.equal(starts,1);assert.equal(requests.length,1)
  requests[0]({inbox:[{id:1}],popup:[]});await tick()
  assert.equal(valuesA.length,1);assert.equal(valuesB.length,1)
  const pending=feed.refresh();leaveA();assert.equal(stops,0);leaveB();assert.equal(stops,1)
  const newAccount=[];const leaveNew=feed.subscribe(value=>newAccount.push(value))
  requests[1]({inbox:[{id:'private-old-account'}]});await pending
  assert.deepEqual(newAccount,[])
  requests[2]({inbox:[{id:2}]});await tick()
  assert.deepEqual(newAccount,[{inbox:[{id:2}]}]);leaveNew()
})
