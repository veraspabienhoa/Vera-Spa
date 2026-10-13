import test from 'node:test'
import assert from 'node:assert/strict'
import { orderedBookingRooms, bookingRoomState } from '../src/lib/liveTourRooms.js'

test('booking uses configured area and bed order instead of raw or alphabetical room order', () => {
  const rooms=[{id:'a',name:'1.1'},{id:'b',name:'16.1'},{id:'c',name:'1.2'},{id:'d',name:'2.1'}]
  const areas=[{id:'vip',beds:[{id:'b'}]},{id:'two',beds:[{id:'d'}]},{id:'one',beds:[{id:'c'},{id:'a'}]}]
  const sorted=orderedBookingRooms(rooms,areas)
  assert.deepEqual(sorted.map(r=>r.name),['16.1','2.1','1.2','1.1'])
  assert.deepEqual(bookingRoomState(sorted,[],[],'','').options.map(r=>r.value),['16.1','2.1','1.2','1.1'])
  assert.deepEqual(rooms.map(r=>r.id),['a','b','c','d'])
  assert.deepEqual(orderedBookingRooms(rooms).map(r=>r.id),['a','b','c','d'])
  assert.deepEqual(orderedBookingRooms(rooms,[{beds:[{id:'d'}]}]).map(r=>r.id),['d','a','b','c'])
})
