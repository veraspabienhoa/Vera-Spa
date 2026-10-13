import test from 'node:test'
import assert from 'node:assert/strict'
import { violationExportRows } from '../src/lib/scheduleTableRows.js'

test('violation Excel keeps current approved-late status separate from original evidence', () => {
 const row={employee_name:'Lan',violation_date:'2026-10-06',reason:'Đi trễ HC',amount:7500,note:'Original 15 minutes, 2×',hc_late_approval_eligible:true,hc_late_approved:true,hc_late_minutes:15}
 const exported=violationExportRows([row])
 assert.equal(exported[0][3],15)
 assert.equal(exported[0][4],7500)
 assert.match(exported[0][5],/^Đi trễ có phép/)
 assert.doesNotMatch(exported[0][5],/Mức theo đơn giá ghi nhận/)
 assert.match(exported[0][5],/Original 15 minutes, 2×/)
 assert.equal(exported[1][4],7500)
 const manual=violationExportRows([{...row,hc_late_approval_eligible:false}])
 assert.equal(manual[0][5],row.note)
 assert.equal(row.note,'Original 15 minutes, 2×')
})
