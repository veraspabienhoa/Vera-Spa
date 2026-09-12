import ClearableSearchInput from '../components/ClearableSearchInput'
import { searchTextMatches } from '../lib/searchText'
import { customerMatches } from '../lib/customerSearch'
import LiveTourCustomerDialog from '../components/LiveTourCustomerDialog'
import { Download, GripVertical, History, Plus, RefreshCw, Save, Settings2, Trash2, Users, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { catalogPayload, newCatalogForm } from '../lib/serviceCatalog'
import ServiceCatalogForm, { ServiceTypePicker } from '../components/ServiceCatalogForm'
import './SpaManagementPage.css'

const money = (value) => Number(value || 0).toLocaleString('vi-VN') + ' ₫'
const areaLabels = { room: 'Phòng', bed: 'Giường', table: 'Bàn' }
const blankArea = () => ({ name: '', kind: 'room', beds: [{ name: 'Giường 1' }] })

function Editor({ title, onClose, busy, children }) {
  const dialog = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    dialog.current.showModal()
    return () => previous?.focus?.()
  }, [])
  return <dialog ref={dialog} className="spa-editor" aria-label={title} onCancel={(event) => { event.preventDefault(); if (!busy) onClose() }}>
    <div className="spa-editor-heading"><h2>{title}</h2><button className="icon-button" type="button" aria-label="Đóng" disabled={busy} onClick={onClose}><X size={20}/></button></div>
    {children}
  </dialog>
}

function Field({ label, children }) {
  return <label className="spa-field"><span>{label}</span>{children}</label>
}

function CustomerHistory({ value }) {
  const canPaid = value.capabilities?.paid_invoice_view !== false
  const canPending = value.capabilities?.pending_view !== false && value.capabilities?.invoice_view !== false
  return <div className="spa-history">
    <div className="spa-summary">{canPaid && <><span>{value.summary.invoice_count} hóa đơn</span><span>Đã thanh toán: <strong>{money(value.summary.total_revenue)}</strong></span></>}<span>Combo còn: <strong>{value.summary.combo_remaining_units} vé</strong></span></div>
    {canPaid ? <><h3>Dịch vụ đã sử dụng</h3>
    <div className="responsive-data-table"><table><thead><tr><th>Ngày / hóa đơn</th><th>Dịch vụ</th><th>Nhân viên</th><th>Vị trí</th><th>Giá dịch vụ</th></tr></thead><tbody>{value.services.map((item) => <tr key={item.id}><td>{item.business_date}<small>{item.bill_no}</small></td><td>{item.service}</td><td>{item.employee_name}</td><td>{item.room}</td><td>{money(item.price)}</td></tr>)}</tbody></table></div>
    {!value.services.length && <p>Chưa có dịch vụ đã thanh toán.</p>}</> : <p>Chưa được cấp quyền xem hóa đơn đã thanh toán.</p>}
    <h3>Combo đã mua</h3>
    <div className="spa-card-grid">{value.combo_purchases.map((item, index) => <article className="spa-card" key={item.id || index}><strong>{item.combo_name}</strong><span>{item.purchased_at || item.created_at || item.lk}</span><span>Đã dùng {item.used || 0} / {item.total || 0} {item.component_balances ? 'lượt' : 'vé'} · Còn {item.remaining || 0} {item.component_balances ? 'lượt' : 'vé'}</span>{item.component_balances?.map((part) => <span key={part.service_id}>{part.service_name}: còn {part.remaining} / {part.total} lượt</span>)}{item.unlimited === false && item.expires_on && <small>Hạn dùng: {item.expires_on.split('-').reverse().join('/')}</small>}</article>)}</div>
    {!value.combo_purchases.length && <p>Chưa mua combo.</p>}
    {canPending ? <><h3>Chờ thanh toán ({value.pending.length})</h3>
    {value.pending.map((item) => <p key={item.id}>{item.created_at} · {(item.entries || []).map((entry) => entry.service).join(', ')}</p>)}</> : <p>Chưa được cấp quyền xem hóa đơn chờ thanh toán.</p>}
  </div>
}

export default function SpaManagementPage({ user, mode }) {
  const customersPage = mode === 'customers'
  const allowed = user?.role === 'admin' || user?.permissions?.[customersPage ? 'live_tour_customers_view' : 'live_tour_admin'] === true
  const canEditCustomer = user?.role === 'admin' || user?.permissions?.live_tour_customers_edit === true
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [tab, setTab] = useState('services')
  const [search, setSearch] = useState('')
  const [serviceFilter, setServiceFilter] = useState('all')
  const [customerContext, setCustomerContext] = useState(null)
  const canCreateCustomer = user?.role === 'admin' || user?.permissions?.live_tour_payment === true
  const canCustomer = feature => user?.role === 'admin' || user?.permissions?.[`live_tour_${feature}`] === true
  const [editor, setEditor] = useState(null)
  const [form, setForm] = useState({})
  const requests = useRef(new Map())
  const running = useRef(false)
  const pointerDrag = useRef(null)
  const [draggingKey, setDraggingKey] = useState('')
  const [dragOverKey, setDragOverKey] = useState('')
  const read = useCallback(() => customersPage ? veraApi.spaCustomers() : veraApi.spaSettings(), [customersPage])

  useEffect(() => {
    if (!allowed) return undefined
    let active = true
    setBusy(true)
    read().then((result) => { if (active) setData(result) }).catch((err) => { if (active) setError(err.message) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [allowed, read])

  const refresh = async () => {
    if (busy || running.current) return
    setBusy(true); setError('')
    try { setData(await read()) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const openEditor = (kind, item) => {
    setError(''); setNotice('')
    setForm(kind === 'customer' ? { customer_id: item?.id || '', customer_name: item?.name || '', customer_phone: item?.phone || '' }
      : kind === 'area' ? structuredClone(item || blankArea()) : newCatalogForm(kind, item))
    setEditor({ kind, existing: Boolean(item) })
  }

  const mutate = async (action, payload, _ids, options) => {
    if (running.current || data?.revision == null) return
    running.current = true
    setBusy(true); setError(''); setNotice('')
    // Retry the same intent with the same key if the response was lost.
    const signature = JSON.stringify([action, payload])
    if (!requests.current.has(signature)) requests.current.set(signature, crypto.randomUUID())
    try {
      const result = await veraApi.liveTourAction({ action, payload, expected_revision: options?.expectedRevision ?? data.revision, idempotency_key: requests.current.get(signature) })
      requests.current.delete(signature)
      setData(customersPage ? { revision: result.revision, customers: result.customers, can_export: result.capabilities.export }
        : { revision: result.revision, services: result.services, combos: result.combo_catalog, service_areas: result.service_areas })
      setEditor(null)
      setNotice('Đã lưu thay đổi.')
      return result
    } catch (err) {
      let message = err.message || 'Không lưu được thay đổi.'
      if (err.status === 409 && /Live Tour đã thay đổi ở thiết bị khác/i.test(message)) {
        try { setData(await read()); message = 'Dữ liệu đã thay đổi ở thiết bị khác. Đã tải bản mới nhất; hãy kiểm tra lại nội dung rồi bấm Lưu.' }
        catch { message += ' Không tải được bản mới nhất; hãy thử Làm mới.' }
      }
      setError(message)
    } finally { running.current = false; setBusy(false) }
  }

  const submit = (event) => {
    event.preventDefault()
    if (editor.kind === 'customer') void mutate('customer_upsert', form)
    if (editor.kind === 'area') void mutate('service_area_upsert', { id: form.id, name: form.name, kind: form.kind, beds: form.beds })
    if (['service', 'combo'].includes(editor.kind)) void mutate(editor.kind === 'combo' ? 'combo_upsert' : 'service_upsert', catalogPayload(editor.kind, form, editor.existing))
  }

  const remove = (kind, item) => {
    if (window.confirm(`Xóa ${kind === 'area' ? 'khu vực' : 'dịch vụ'} “${item.name}”${kind === 'area' && item.kind === 'room' ? ' cùng các giường bên trong' : ''}?`)) void mutate(kind === 'area' ? 'service_area_delete' : kind === 'combo' ? 'combo_delete' : 'service_delete', { id: item.id })
  }

  const history = async (customer) => {
    setBusy(true); setError('')
    try { const value = await veraApi.liveTourCustomerHistory(customer.id); setEditor({ kind: 'history', value }) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const exportCustomers = async () => {
    setBusy(true); setError('')
    try { await veraApi.exportLiveTourExcel('customers') }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }))
  const services = data?.services || []
  const catalogItems = [...services.map((item) => ({ ...item, catalog_kind: 'service' })), ...(data?.combos || []).map((item) => ({ ...item, catalog_kind: 'combo' }))]
    .map((item, sourceIndex) => ({ ...item, sourceIndex }))
    .sort((left, right) => {
      const leftOrder = Number(left.display_order)
      const rightOrder = Number(right.display_order)
      if (Number.isFinite(leftOrder) && Number.isFinite(rightOrder)) return leftOrder - rightOrder
      if (Number.isFinite(leftOrder)) return -1
      if (Number.isFinite(rightOrder)) return 1
      return left.sourceIndex - right.sourceIndex
    })
  const groups = [...new Set(catalogItems.map((item) => item.group).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'))
  const rows = (customersPage ? data?.customers : tab === 'services' ? catalogItems : data?.service_areas) || []
  const filtered = rows.filter((item) => (customersPage ? customerMatches(item, search) : searchTextMatches([item.name, item.group], search)) && (customersPage || tab !== 'services' || serviceFilter === 'all' || item.catalog_kind === serviceFilter))
  const title = customersPage ? 'Khách hàng' : 'Cài đặt'
  const addKind = customersPage ? 'customer' : tab === 'services' ? 'choose-service' : 'area'
  const editTitle = editor?.kind === 'choose-service' ? 'Chọn loại dịch vụ' : editor?.kind === 'history' ? `Lịch sử · ${editor.value.customer.name}` : `${editor?.existing ? 'Sửa' : 'Thêm'} ${editor?.kind === 'customer' ? 'khách hàng' : editor?.kind === 'area' ? 'khu vực dịch vụ' : editor?.kind === 'combo' ? 'dịch vụ combo' : 'dịch vụ đơn lẻ'}`
  const rowKey = (item) => tab === 'services' ? `${item.catalog_kind}:${item.id}` : String(item.id)
  const saveOrder = (sourceKey, targetKey) => {
    if (!sourceKey || !targetKey || sourceKey === targetKey) return
    const allRows = tab === 'services' ? catalogItems : (data?.service_areas || [])
    const orderedIds = allRows.map(rowKey)
    const from = orderedIds.indexOf(sourceKey)
    const target = orderedIds.indexOf(targetKey)
    if (from < 0 || target < 0) return
    const [moved] = orderedIds.splice(from, 1)
    const targetAfterRemoval = orderedIds.indexOf(targetKey)
    orderedIds.splice(from < target ? targetAfterRemoval + 1 : targetAfterRemoval, 0, moved)
    void mutate('settings_reorder', { scope: tab === 'services' ? 'catalog' : 'service_areas', ordered_ids: orderedIds })
  }
  const finishDrag = (sourceKey, targetKey) => {
    setDraggingKey(''); setDragOverKey(''); pointerDrag.current = null
    saveOrder(sourceKey, targetKey)
  }
  const dragProps = (item, baseClass = '') => {
    const key = rowKey(item)
    return {
      draggable: !busy,
      'data-sort-key': key,
      className: `${baseClass} ${draggingKey === key ? 'spa-sort-dragging' : ''} ${dragOverKey === key && draggingKey !== key ? 'spa-sort-over' : ''}`.trim(),
      onDragStart: (event) => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', key); setDraggingKey(key) },
      onDragOver: (event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; setDragOverKey(key) },
      onDrop: (event) => { event.preventDefault(); finishDrag(event.dataTransfer.getData('text/plain') || draggingKey, key) },
      onDragEnd: () => { setDraggingKey(''); setDragOverKey('') },
    }
  }
  const handlePointerDown = (event, item) => {
    if (busy || event.pointerType === 'mouse') return
    event.preventDefault()
    pointerDrag.current = { pointerId: event.pointerId, sourceKey: rowKey(item), targetKey: rowKey(item) }
    event.currentTarget.setPointerCapture(event.pointerId)
    setDraggingKey(rowKey(item))
  }
  const handlePointerMove = (event) => {
    const active = pointerDrag.current
    if (!active || active.pointerId !== event.pointerId) return
    event.preventDefault()
    const targetKey = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-sort-key]')?.dataset.sortKey
    if (targetKey) { active.targetKey = targetKey; setDragOverKey(targetKey) }
  }
  const handlePointerUp = (event) => {
    const active = pointerDrag.current
    if (!active || active.pointerId !== event.pointerId) return
    finishDrag(active.sourceKey, active.targetKey)
  }
  const cancelPointerDrag = () => { pointerDrag.current = null; setDraggingKey(''); setDragOverKey('') }
  const handleSortKey = (event, item) => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return
    event.preventDefault()
    const index = filtered.findIndex((row) => rowKey(row) === rowKey(item))
    const neighbor = filtered[index + (event.key === 'ArrowUp' ? -1 : 1)]
    if (neighbor) saveOrder(rowKey(item), rowKey(neighbor))
  }

  if (!allowed) return <div className="error-box" role="alert">Tài khoản chưa được cấp quyền mở {title}.</div>

  return <div className="feature-page spa-management">
    <div className="page-heading"><div><span className="eyebrow">{customersPage ? <Users size={14}/> : <Settings2 size={14}/>} VERA SPA</span><h1>{title}</h1><p>{customersPage ? 'Hồ sơ khách hàng, lịch sử dịch vụ và số vé combo còn lại.' : 'Quản lý dịch vụ và vị trí phục vụ dùng chung với Live Tour.'}</p></div><button className="secondary-button" onClick={refresh} disabled={busy}><RefreshCw size={16}/> Làm mới</button></div>
    {error && !editor && <div className="error-box" role="alert">{error}</div>}
    {notice && <div className="success-box" role="status">{notice}</div>}
    {!customersPage && <div className="spa-tabs" role="tablist" aria-label="Cài đặt"><button role="tab" aria-selected={tab === 'services'} aria-controls="spa-settings-content" id="spa-services-tab" disabled={busy} onClick={() => { setTab('services'); setSearch('') }}>Cài đặt dịch vụ</button><button role="tab" aria-selected={tab === 'areas'} aria-controls="spa-settings-content" id="spa-areas-tab" disabled={busy} onClick={() => { setTab('areas'); setSearch('') }}>Cài đặt khu vực dịch vụ</button></div>}
    <section className="panel spa-content" id="spa-settings-content" role={customersPage ? undefined : 'tabpanel'} aria-labelledby={customersPage ? undefined : `spa-${tab}-tab`}>
      {!customersPage && tab === 'services' && <div className="spa-service-filters" aria-label="Lọc loại dịch vụ">{[['all', 'Tất cả'], ['service', 'Dịch vụ đơn lẻ'], ['combo', 'Dịch vụ combo']].map(([value, label]) => <button type="button" className="secondary-button" aria-pressed={serviceFilter === value} key={value} onClick={() => setServiceFilter(value)}>{label}</button>)}</div>}
      <div className="spa-toolbar"><ClearableSearchInput type="search" aria-label="Tìm kiếm" placeholder={customersPage ? 'Tìm tên hoặc số điện thoại…' : 'Tìm theo tên…'} value={search} onChange={(event) => setSearch(event.target.value)}/><span>{filtered.length} / {rows.length}</span><div className="spa-actions">{customersPage && data?.can_export && <button className="secondary-button" disabled={busy} onClick={exportCustomers}><Download size={16}/> Xuất Excel</button>}<button className="primary-button" disabled={busy || !data || (customersPage && !canCreateCustomer)} onClick={() => openEditor(addKind)}><Plus size={16}/> Thêm {customersPage ? 'khách hàng' : tab === 'services' ? 'dịch vụ' : 'khu vực'}</button></div></div>
      {busy && !data && <p role="status">Đang tải dữ liệu…</p>}
      {data && !filtered.length && <p className="spa-empty">{rows.length ? 'Không có kết quả phù hợp.' : 'Chưa có dữ liệu. Bấm Thêm để tạo mới.'}</p>}
      {customersPage ? <div className="responsive-data-table"><table><thead><tr><th>Khách hàng</th><th>Điện thoại</th><th>Combo còn lại</th><th>Thao tác</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><strong>{item.name || 'Chưa có tên'}</strong></td><td>{item.phone || '—'}</td><td>{(item.combo_purchases || []).reduce((sum, purchase) => sum + Number(purchase.remaining || 0), 0)} vé</td><td><div className="spa-actions"><button className="secondary-button" disabled={busy || !canEditCustomer} onClick={() => { setError(''); setCustomerContext({ customer: item, mode: 'edit', revision: data.revision }) }}>Sửa</button>{canCustomer('customers_delete') && <button className="secondary-button danger-button" disabled={busy} onClick={() => { setError(''); setCustomerContext({ customer: item, mode: 'delete', revision: data.revision }) }}>Xóa</button>}
      {(item.combo_purchases || []).map(purchase => <span key={purchase.id}>{purchase.combo_name} · {purchase.remaining} vé {canCustomer('customer_combo_edit') && <button className="text-button" disabled={busy} onClick={() => { setError(''); setCustomerContext({ customer: item, purchase, mode: 'edit', revision: data.revision }) }}>Sửa combo</button>}{canCustomer('customer_combo_delete') && <button className="text-button" disabled={busy} onClick={() => { setError(''); setCustomerContext({ customer: item, purchase, mode: 'delete', revision: data.revision }) }}>Xóa combo</button>}</span>)}
      <button className="secondary-button" disabled={busy} onClick={() => history(item)}><History size={14}/> Lịch sử</button></div></td></tr>)}</tbody></table></div>
        : tab === 'services' ? <div className="responsive-data-table"><table><thead><tr><th aria-label="Sắp xếp"></th><th>Dịch vụ / nhóm</th><th>Loại dịch vụ</th><th>Thời lượng / thành phần</th><th>Giá</th><th>Số lượt</th><th>Thao tác</th></tr></thead><tbody>{filtered.map((item) => <tr key={`${item.catalog_kind}:${item.id}`} {...dragProps(item)}>
          <td><span className="spa-drag-handle" role="button" tabIndex={busy ? -1 : 0} aria-label={`Kéo để sắp xếp ${item.name}`} title="Giữ và kéo để thay đổi vị trí" onKeyDown={(event) => handleSortKey(event, item)} onPointerDown={(event) => handlePointerDown(event, item)} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={cancelPointerDrag}><GripVertical size={19}/></span></td>
          <td><strong>{item.name}</strong>{item.private && <span className="spa-badge">PR</span>}<small>{item.group || 'Chưa phân nhóm'}</small>{item.active === false && <small>Ngừng sử dụng</small>}{item.expires_on && item.unlimited === false && <small>Hết hạn: {item.expires_on.split('-').reverse().join('/')}</small>}</td>
          <td><span className="spa-badge">{item.catalog_kind === 'combo' ? 'Combo' : 'Đơn lẻ'}</span></td>
          <td>{item.catalog_kind === 'combo' ? item.components?.length ? <ul className="spa-component-summary">{item.components.map((part) => <li key={part.service_id}>{services.find((service) => service.id === part.service_id)?.name || part.service_name} × {part.quantity} lượt</li>)}</ul> : 'Combo vé hiện có' : item.duration == null ? 'Không giới hạn' : `${item.duration} phút`}</td>
          <td>{money(item.price)}</td><td>{item.catalog_kind === 'combo' ? item.tickets : item.sessions ?? 1}</td>
          <td><div className="spa-actions"><button className="secondary-button" disabled={busy} onClick={() => openEditor(item.catalog_kind, item)}>Sửa</button><button className="secondary-button danger-button" disabled={busy} onClick={() => remove(item.catalog_kind, item)}><Trash2 size={14}/> Xóa</button></div></td>
        </tr>)}</tbody></table></div>
          : <div className="spa-card-grid spa-settings-list">{filtered.map((item) => <article key={item.id} {...dragProps(item, 'spa-card')}><div className="spa-card-heading spa-area-summary"><span className="spa-drag-handle" role="button" tabIndex={busy ? -1 : 0} aria-label={`Kéo để sắp xếp ${item.name}`} title="Giữ và kéo để thay đổi vị trí" onKeyDown={(event) => handleSortKey(event, item)} onPointerDown={(event) => handlePointerDown(event, item)} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={cancelPointerDrag}><GripVertical size={19}/></span><h3>{item.kind === 'room' && !/^(phòng|vip)\s/i.test(item.name) ? `Phòng ${item.name}` : item.name}</h3>{item.kind === 'room' ? <><span>- {item.beds.length} giường:</span><ul className="spa-bed-list">{item.beds.map((bed) => <li key={bed.id}>{bed.name}{bed.active === false ? ' · Ngừng sử dụng' : ''}</li>)}</ul></> : <span>{areaLabels[item.kind]}</span>}</div><div className="spa-actions"><button className="secondary-button" disabled={busy} onClick={() => openEditor('area', item)}>Sửa</button><button className="secondary-button danger-button" disabled={busy} onClick={() => remove('area', item)}><Trash2 size={14}/> Xóa</button></div></article>)}</div>}
    </section>
    {customerContext && <LiveTourCustomerDialog context={customerContext} busy={busy} error={error} onAction={mutate} onClose={() => setCustomerContext(null)}/>}
    {editor && <Editor title={editTitle} onClose={() => { setEditor(null); setError('') }} busy={busy}>
      {error && <div className="error-box" role="alert">{error}</div>}
      {editor.kind === 'choose-service' ? <ServiceTypePicker onChoose={(kind) => openEditor(kind)}/> : editor.kind === 'history' ? <CustomerHistory value={editor.value}/> : <form onSubmit={submit}><fieldset disabled={busy} className="spa-form">
        {editor.kind === 'customer' && <><Field label="Tên khách hàng"><input required maxLength={150} value={form.customer_name} onChange={(event) => set('customer_name', event.target.value)}/></Field><Field label="Số điện thoại"><input type="tel" maxLength={30} value={form.customer_phone} onChange={(event) => set('customer_phone', event.target.value)}/></Field></>}
        {['service', 'combo'].includes(editor.kind) && <ServiceCatalogForm kind={editor.kind} form={form} setForm={setForm} services={services} groups={groups} existing={editor.existing}/>}
        {editor.kind === 'area' && <>
          <Field label="Loại khu vực"><select value={form.kind} onChange={(event) => set('kind', event.target.value)}>{Object.entries(areaLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <Field label={`Tên ${areaLabels[form.kind].toLowerCase()}`}><input required maxLength={100} value={form.name} onChange={(event) => set('name', event.target.value)}/></Field>
          {form.kind === 'room' && <div className="spa-beds-editor"><h3>Giường trong phòng ({form.beds.length})</h3>{form.beds.map((bed, index) => <div className="spa-bed-row" key={bed.id || index}><input aria-label={`Tên giường ${index + 1}`} required maxLength={100} value={bed.name} onChange={(event) => set('beds', form.beds.map((value, i) => i === index ? { ...value, name: event.target.value } : value))}/><button className="icon-button" type="button" aria-label={`Bỏ giường ${index + 1}`} disabled={form.beds.length <= 1} onClick={() => set('beds', form.beds.filter((_, i) => i !== index))}><Trash2 size={16}/></button></div>)}<button className="secondary-button" type="button" disabled={form.beds.length >= 100} onClick={() => { let n = form.beds.length + 1; while (form.beds.some((bed) => bed.name === `Giường ${n}`)) n += 1; set('beds', [...form.beds, { name: `Giường ${n}` }]) }}><Plus size={14}/> Thêm giường</button></div>}
        </>}
        <div className="spa-editor-footer"><button className="secondary-button" type="button" onClick={() => setEditor(null)}>Hủy</button><button className="primary-button" type="submit"><Save size={16}/>{busy ? 'Đang lưu…' : editor.existing ? 'Lưu thay đổi' : 'Thêm mới'}</button></div>
      </fieldset></form>}
    </Editor>}
  </div>
}
