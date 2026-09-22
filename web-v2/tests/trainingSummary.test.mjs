import test from 'node:test'
import assert from 'node:assert/strict'
import { trainingDailySummary } from '../src/lib/trainingSummary.js'
test('Multiple sessions are summed by date without losing daily evaluation detail',()=>{
 const days=trainingDailySummary([{id:1,training_date:'2026-09-22',start_time:'09:00:00',end_time:'10:30:00',notes:'Tốt'}, {id:2,training_date:'2026-09-22',start_time:'14:00',end_time:'15:15'}, {id:3,training_date:'2026-09-21',start_time:'08:00',end_time:'09:00'}])
 assert.equal(days[0].minutes,165);assert.equal(days[0].sessions.length,2);assert.equal(days[0].sessions[0].notes,'Tốt');assert.equal(days[1].minutes,60)
})
test('Empty report and malformed time never invent hours',()=>{
 assert.deepEqual(trainingDailySummary([]),[])
 assert.equal(trainingDailySummary([{training_date:'2026-09-22',start_time:'bad',end_time:'09:00'}])[0].minutes,0)
})
