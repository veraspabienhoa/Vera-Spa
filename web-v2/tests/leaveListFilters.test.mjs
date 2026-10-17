import test from 'node:test'
import assert from 'node:assert/strict'
import { matchesLeaveDetails } from '../src/lib/leaveListFilters.js'
import { approvedLeaveStatus } from '../src/lib/approvedLeaveFilters.js'
test('leave filters combine reason, type and details without accents',()=>{
 const row={leave_reason:'Nghỉ Phép năm',leave_type:'Phép năm',detail:'Về quê Đồng Nai'}
 assert.equal(matchesLeaveDetails(row,{leave_reason:'phep',leave_type:'phep nam',detail:'dong nai'}),true)
 assert.equal(matchesLeaveDetails(row,{leave_reason:'khong',detail:'que'}),false)
 assert.equal(matchesLeaveDetails(row,{}),true)
})
test('resignation is completed from its effective Vietnam date',()=>{
 const row={request_type:'Nghỉ việc',start_date:'2026-10-17'}
 assert.equal(approvedLeaveStatus(row,'2026-10-16').id,'resignation')
 assert.equal(approvedLeaveStatus(row,'2026-10-17').id,'completed')
})
