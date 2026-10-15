import { useState } from 'react'
import VeraDateInput from './VeraDateInput'
import TrainingReportFiles from './TrainingReportFiles'

import { contractPeriod } from '../lib/laborContractPeriod'

export default function LaborReportFiles({ scope, ...props }) {
  const [months, setMonths] = useState('1')
  const [dates, setDates] = useState(() => contractPeriod())
  const [valid, setValid] = useState({ contract_signed: true, contract_end: true })
  const [prepared, setPrepared] = useState(null)
  const changeDate = (key, value) => { setPrepared(null); setDates(current => ({ ...current, [key]: value })) }
  return <>
    <form className="labor-report-options" onSubmit={event => { event.preventDefault(); if (valid.contract_signed && valid.contract_end) setPrepared({ ...scope, filters: { ...scope.filters, ...dates } }) }}>
      <label>Số tháng<input type="number" min="1" max="120" step="1" required value={months} onChange={event => {
        const value = event.target.value; setMonths(value); setPrepared(null)
        if (Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= 120) { setDates(contractPeriod(Number(value))); setValid({ contract_signed: true, contract_end: true }) }
      }}/></label>
      <label>Ngày ký hợp đồng<VeraDateInput required value={dates.contract_signed} onChange={event => changeDate('contract_signed', event.target.value)} onDraftValidity={value => { setPrepared(null); setValid(current => ({ ...current, contract_signed: value })) }}/></label>
      <label>Ngày hết hạn hợp đồng<VeraDateInput required min={dates.contract_signed} value={dates.contract_end} onChange={event => changeDate('contract_end', event.target.value)} onDraftValidity={value => { setPrepared(null); setValid(current => ({ ...current, contract_end: value })) }}/></label>
      <button type="submit" className="primary-button" disabled={!valid.contract_signed || !valid.contract_end || !dates.contract_signed || dates.contract_end < dates.contract_signed}>Tạo PDF và PNG</button>
    </form>
    {prepared && <TrainingReportFiles scope={prepared} {...props}/>}
  </>
}
