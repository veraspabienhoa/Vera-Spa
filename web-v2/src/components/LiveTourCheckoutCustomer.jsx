import LiveTourSearchSelect from './LiveTourSearchSelect'
import { customerMatches } from '../lib/customerSearch'

export default function LiveTourCheckoutCustomer({ customers, form, setForm, disabled }) {
  const options = customers.map((customer) => ({
    value: String(customer.id || customer._id || customer.customer_id || ''),
    label: customer.name || customer.customer_name || '',
    detail: customer.phone || customer.customer_phone || '',
  })).filter((option) => option.value)
  const choose = (id) => {
    const customer = options.find((option) => option.value === id)
    setForm((current) => ({ ...current, customer_id: id,
      customer_name: customer?.label || '', phone: customer?.detail || '',
      combo_purchase_id: '', payment_method: current.payment_method === 'COMBO' ? 'TIỀN MẶT' : current.payment_method }))
  }
  const type = (field, query) => setForm((current) => ({ ...current, customer_id: '',
    // When replacing a linked customer, never keep the previous person's other field.
    ...(current.customer_id ? { customer_name: '', phone: '' } : {}), [field]: query,
    combo_purchase_id: '', payment_method: current.payment_method === 'COMBO' ? 'TIỀN MẶT' : current.payment_method }))
  return <>
    <LiveTourSearchSelect label="Khách hàng" value={form.customer_id} searchValue={form.customer_name}
      options={options} disabled={disabled} placeholder="Tìm tên hoặc nhập khách mới" emptyLabel="Khách lẻ"
      filterOption={(option, query) => customerMatches({ name: option.label, phone: option.detail }, query)}
      onSearch={(query) => type('customer_name', query)} onChange={choose}/>
    <LiveTourSearchSelect label="Điện thoại" value={form.customer_id} searchValue={form.phone}
      options={options.map((option) => ({ ...option, label: option.detail || 'Chưa có SĐT', detail: option.label }))}
      disabled={disabled} placeholder="Tìm theo số điện thoại" emptyLabel="Khách lẻ" inputMode="tel"
      filterOption={(option, query) => customerMatches({ name: option.detail, phone: option.label }, query)}
      onSearch={(query) => type('phone', query)} onChange={choose}/>
  </>
}
