import { ArrowDown, ArrowUp, Layers, ListChecks, Plus, Trash2 } from 'lucide-react'
import VeraDateInput from './VeraDateInput'

function Field({ label, children, wide = false }) {
  return <label className={`spa-field ${wide ? 'spa-wide' : ''}`}><span>{label}</span>{children}</label>
}

export function ServiceTypePicker({ onChoose }) {
  return <div className="spa-service-types">
    <button type="button" onClick={() => onChoose('service')}><ListChecks size={30}/><strong>Dịch vụ đơn lẻ</strong><span>Thiết lập số lượt, thời lượng và lộ trình thực hiện.</span></button>
    <button type="button" onClick={() => onChoose('combo')}><Layers size={30}/><strong>Dịch vụ combo</strong><span>Kết hợp các dịch vụ và số lượt sử dụng trong một gói.</span></button>
  </div>
}

export default function ServiceCatalogForm({ kind, form, setForm, services, groups, existing }) {
  const combo = kind === 'combo'
  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }))
  const updateRow = (key, index, patch) => setForm((current) => ({ ...current, [key]: current[key].map((row, i) => i === index ? { ...row, ...patch } : row) }))
  const moveStep = (index, direction) => {
    const steps = [...form.steps]
    ;[steps[index], steps[index + direction]] = [steps[index + direction], steps[index]]
    set('steps', steps)
  }
  const total = form.components.reduce((sum, row) => sum + Number(row.quantity || 0), 0)
  return <>
    <Field label="Tên dịch vụ *" wide><input autoFocus required maxLength={150} value={form.name} placeholder={combo ? 'Nhập tên dịch vụ combo' : 'Nhập tên dịch vụ'} onChange={(event) => set('name', event.target.value)}/></Field>
    <Field label="Nhóm dịch vụ" wide><input list="spa-service-groups" maxLength={120} value={form.group} placeholder="Chọn hoặc nhập nhóm dịch vụ" onChange={(event) => set('group', event.target.value)}/><datalist id="spa-service-groups">{groups.map((group) => <option key={group} value={group}/>)}</datalist></Field>
    <Field label="Giá (đ)"><input type="number" min="0" max="10000000000" step="1" value={form.price} onChange={(event) => set('price', event.target.value)} placeholder="0"/></Field>
    {!combo && <Field label="Số lượt *"><input type="number" required min="1" max="100000" step="1" value={form.sessions} onChange={(event) => set('sessions', event.target.value)}/></Field>}
    <Field label="Ngày áp dụng"><VeraDateInput required={!existing || !form.unlimited} value={form.starts_on} onChange={(event) => set('starts_on', event.target.value)}/></Field>
    {combo ? <div className="spa-wide spa-components-editor"><h3>Dịch vụ thành phần *</h3>
      {form.combo_mode === 'generic' ? <><p>Combo vé hiện có: dùng định mức vé của dịch vụ khi thanh toán.</p><Field label="Tổng số vé"><input type="number" min="1" max="100000" required value={form.tickets} onChange={(event) => set('tickets', event.target.value)}/></Field><button className="secondary-button" type="button" onClick={() => setForm((current) => ({ ...current, combo_mode: 'components', components: [{ service_id: '', quantity: '1' }] }))}>Chọn dịch vụ cụ thể cho combo</button></>
        : <>
          {form.components.map((row, index) => <div className="spa-component-row" key={index}>
            <Field label={`Dịch vụ ${index + 1}`}><select required value={row.service_id} onChange={(event) => { const service = services.find((item) => item.id === event.target.value); updateRow('components', index, { service_id: event.target.value, quantity: service?.sessions || 1 }) }}><option value="">Chọn dịch vụ đơn lẻ</option>{services.map((service) => <option key={service.id} value={service.id} disabled={form.components.some((item, i) => i !== index && item.service_id === service.id)}>{service.name}{service.active === false ? ' · Ngừng sử dụng' : ''}</option>)}</select></Field>
            <Field label="Số lượt"><input type="number" min="1" max="100000" step="1" required value={row.quantity} onChange={(event) => updateRow('components', index, { quantity: event.target.value })}/></Field>
            <button type="button" className="icon-button" disabled={form.components.length <= 1} aria-label={`Bỏ dịch vụ ${index + 1}`} onClick={() => set('components', form.components.filter((_, i) => i !== index))}><Trash2 size={16}/></button>
          </div>)}
          <div className="spa-actions"><button className="secondary-button" type="button" disabled={form.components.length >= Math.min(100, services.length)} onClick={() => set('components', [...form.components, { service_id: '', quantity: '1' }])}><Plus size={15}/> Thêm dịch vụ</button><strong>Tổng: {total.toLocaleString('vi-VN')} lượt</strong></div>
          {!services.length && <p>Tạo dịch vụ đơn lẻ trước khi thêm vào combo.</p>}
        </>}
    </div> : <>
      <div className="spa-wide spa-steps-editor"><h3>Lộ trình thực hiện</h3>{form.steps.map((step, index) => <div className="spa-step-row" key={index}>
        <Field label={`Bước ${index + 1}`}><input required maxLength={160} value={step.name} placeholder="Tên bước thực hiện" onChange={(event) => updateRow('steps', index, { name: event.target.value })}/></Field>
        <Field label="Phút"><input type="number" min="0" max="1440" step="1" value={step.duration} onChange={(event) => updateRow('steps', index, { duration: event.target.value })}/></Field>
        <div className="spa-actions"><button type="button" className="icon-button" aria-label={`Đưa bước ${index + 1} lên`} disabled={index === 0} onClick={() => moveStep(index, -1)}><ArrowUp size={15}/></button><button type="button" className="icon-button" aria-label={`Đưa bước ${index + 1} xuống`} disabled={index === form.steps.length - 1} onClick={() => moveStep(index, 1)}><ArrowDown size={15}/></button><button type="button" className="icon-button" aria-label={`Xóa bước ${index + 1}`} onClick={() => set('steps', form.steps.filter((_, i) => i !== index))}><Trash2 size={15}/></button></div>
      </div>)}<button className="secondary-button" type="button" disabled={form.steps.length >= 50} onClick={() => set('steps', [...form.steps, { name: '', duration: '0' }])}><Plus size={15}/> Thêm lộ trình</button></div>
      <Field label="Thời lượng (phút)"><input type="number" min="0" max="1440" step="1" value={form.duration ?? ''} placeholder="Để trống nếu không giới hạn" onChange={(event) => set('duration', event.target.value)}/></Field>
    </>}
    <div className="spa-wide spa-checks"><strong>Loại sử dụng</strong><label><input type="checkbox" checked={form.unlimited} onChange={(event) => set('unlimited', event.target.checked)}/>Vô thời hạn</label></div>
    {!form.unlimited && <Field label="Ngày hết hạn *"><VeraDateInput required min={form.starts_on} value={form.expires_on} onChange={(event) => set('expires_on', event.target.value)}/></Field>}
    <Field label="Điểm tích lũy"><input type="number" min="0" max="1000000000" step="1" value={form.loyalty_points} onChange={(event) => set('loyalty_points', event.target.value)}/></Field>
    <Field label="Mô tả" wide><textarea rows="3" maxLength={5000} value={form.description} placeholder="Nội dung mô tả" onChange={(event) => set('description', event.target.value)}/></Field>
    {!combo && <details className="spa-wide spa-service-rules"><summary>Quy tắc sử dụng trên Live Tour</summary><div className="spa-form">
      <Field label="Số vé trừ khi dùng combo vé"><input type="number" min="0" max="100000" step="1" required value={form.ticket_units} onChange={(event) => set('ticket_units', event.target.value)}/></Field>
      <Field label="Thời lượng khi khách yêu cầu (phút)"><input type="number" min="0" max="1440" value={form.request_duration ?? ''} onChange={(event) => set('request_duration', event.target.value)}/></Field>
      <div className="spa-checks">{[['private', 'Dịch vụ phòng riêng (PR)'], ['request_eligible', 'Cho phép khách yêu cầu KTV'], ['non_request_eligible', 'Cho phép không yêu cầu KTV']].map(([key, label]) => <label key={key}><input type="checkbox" checked={form[key]} onChange={(event) => set(key, event.target.checked)}/>{label}</label>)}</div>
    </div></details>}
    <div className="spa-wide spa-checks"><label><input type="checkbox" checked={form.active} onChange={(event) => set('active', event.target.checked)}/>Đang sử dụng</label></div>
  </>
}
