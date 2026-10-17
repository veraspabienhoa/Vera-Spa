import test from 'node:test'
import assert from 'node:assert/strict'
import { preservePayrollEdits } from '../src/lib/payrollDraftEdits.js'
const fields=['Tiền ứng lương','Tích lũy']
const net=r=>({...r,net:r['Tiền Lương']-r['Tiền ứng lương']-r['Tích lũy']})
const fresh={start:'2026-10-01',end:'2026-10-15',rows:[{'Tên Hệ thống':'A','Tiền Lương':2000,'Tiền ứng lương':100,'Tích lũy':500}]}
test('recalculation retains explicit zero and edited amount while updating source earnings',()=>{
 const previous={...fresh,rows:[{...fresh.rows[0],'Tiền Lương':1000,__manual_overrides:{'Tiền ứng lương':0,'Tích lũy':200}}]}
 const result=preservePayrollEdits(fresh,previous,fields,net)
 assert.equal(result.rows[0].net,1800)
 assert.equal(result.rows[0]['Tiền Lương'],2000)
 assert.equal(fresh.rows[0]['Tích lũy'],500)
})
test('untouched fields refresh; edits never cross periods or employee identities',()=>{
 const previous={...fresh,rows:[{...fresh.rows[0],__manual_overrides:{}}]}
 assert.equal(preservePayrollEdits(fresh,previous,fields,net).rows[0].net,1400)
 previous.rows[0].__manual_overrides={'Tích lũy':0}
 assert.equal(preservePayrollEdits(fresh,{...previous,start:'2026-09-01'},fields,net).rows[0].net,1400)
 previous.rows[0]['Tên Hệ thống']='B'
 assert.equal(preservePayrollEdits(fresh,previous,fields,net).rows[0].net,1400)
})
test('legacy snapshots retain saved editable amounts',()=>{
 const previous={...fresh,rows:[{...fresh.rows[0],'Tích lũy':0}]}
 assert.equal(preservePayrollEdits(fresh,previous,fields,net).rows[0]['Tích lũy'],0)
})
