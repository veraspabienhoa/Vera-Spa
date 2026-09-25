import test from 'node:test'
import assert from 'node:assert/strict'
import { refreshAfterLiveTourAction } from '../src/lib/liveTourActionResult.js'

test('confirmed receipt does not wait for board and a failed board cannot reject payment', async () => {
  let fail, reads = 0
  const pending = new Promise((_, reject) => { fail = reject })
  const payment = {ok:true,refresh_board:true,result:{invoice:{id:'invoice',total:350000}}}
  await refreshAfterLiveTourAction(payment, (refresh,quiet) => {
    reads++; assert.equal(refresh,false); assert.equal(quiet,true); return pending
  }, () => assert.fail('Receipt is not a board snapshot'))
  assert.equal(reads,1)
  fail(Error('board timeout'))
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(payment.result.invoice.total,350000)
})

test('board responses update state without an extra request', async () => {
  const board = {records:[],columns:[],revision:8}
  let applied
  await refreshAfterLiveTourAction(board, () => assert.fail('unexpected read'), value => { applied=value })
  assert.equal(applied,board)
})
