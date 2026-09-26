import LiveTourSearchSelect from './LiveTourSearchSelect'
import { customerOptionMatches } from '../lib/customerSearch'
import { latestCustomerPurchase, comboTicketText } from '../lib/customerComboRows'

export default function ComboCustomerFields({ customers, draft, setDraft, busy }) {
  const available = customers.filter(customer => !customer.deleted_at && latestCustomerPurchase(customer))
  const choose = id => {
    const customer = available.find(row => row.id === id)
    const purchase = latestCustomerPurchase(customer)
    setDraft(current => ({ ...current, customer_id: customer?.id || '', combo_purchase_id: purchase?.id || '',
      customer_name: customer?.name || '', customer_phone: customer?.phone || '', combo_ticket: comboTicketText(purchase) }))
  }
  const type = (field, value) => setDraft(current => ({...current, [field]: value, customer_id:'', combo_purchase_id:'', combo_ticket:''}))
  return <>
    <LiveTourSearchSelect label="Tên khách hàng" placeholder="Tìm tên hoặc số điện thoại" disabled={busy}
      value={draft.customer_id || ''} searchValue={draft.customer_name} onSearch={value => type('customer_name', value)}
      options={available.map(row=>({value:row.id,label:row.name,detail:row.phone}))} filterOption={customerOptionMatches} onChange={choose}/>
    <LiveTourSearchSelect label="Số điện thoại" placeholder="Tìm số điện thoại hoặc tên" disabled={busy} inputMode="tel"
      value={draft.customer_id || ''} searchValue={draft.customer_phone} onSearch={value => type('customer_phone', value)}
      options={available.map(row=>({value:row.id,label:row.phone || row.name,detail:row.name,searchName:row.name,searchPhone:row.phone}))}
      filterOption={(option,query)=>customerOptionMatches({label:option.searchName,detail:option.searchPhone},query)} onChange={choose}/>
    <label>Vé combo<input readOnly value={draft.combo_ticket} placeholder="Tự điền combo mua mới nhất" /></label>
  </>
}
