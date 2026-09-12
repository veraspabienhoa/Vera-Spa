import LiveTourCheckoutCustomer from './LiveTourCheckoutCustomer'
import LiveTourSearchSelect from './LiveTourSearchSelect'

export default function LiveTourComboImportFields({ customers, combos, form, setForm }) {
  const selected = combos.find(combo => String(combo.id) === form.combo_id)
  const parts = selected?.components || []
  const multiple = parts.length > 1
  const setBalance = (id, value) => setForm(current => {
    const balances = { ...current.component_remaining, [id]: value }
    return { ...current, component_remaining: balances, remaining: String(Object.values(balances).reduce((sum, count) => sum + Number(count || 0), 0)) }
  })
  return <>
    <LiveTourCheckoutCustomer customers={customers} form={form} setForm={setForm} customerRequired/>
    <LiveTourSearchSelect label="Combo" placeholder="Gõ để tìm và chọn combo…" required value={form.combo_id}
      options={combos.map(combo => ({ value: String(combo.id), label: combo.name,
        detail: `${combo.tickets ?? 0} lượt · ${Number(combo.price || 0).toLocaleString('vi-VN')} đ` }))}
      onChange={comboId => setForm(current => ({ ...current, combo_id: comboId, remaining: '', component_remaining: {} }))}/>
    <label className="live-tour-field"><span>{multiple ? 'Tổng số lượt còn lại' : 'Số lượt còn lại'}</span>
      <input type="number" min="1" step="1" value={form.remaining} readOnly={multiple} required
        onChange={event => setForm(current => ({ ...current, remaining: event.target.value }))}/></label>
    {multiple && parts.map(part => <label className="live-tour-field" key={part.service_id}><span>{part.service_name} · lượt còn lại</span>
      <input type="number" min="0" step="1" required value={form.component_remaining?.[part.service_id] ?? ''}
        onChange={event => setBalance(part.service_id, event.target.value)}/></label>)}
    <label className="live-tour-field wide"><span>Ghi chú</span><textarea value={form.note} onChange={event => setForm(current => ({ ...current, note: event.target.value }))}/></label>
  </>
}
