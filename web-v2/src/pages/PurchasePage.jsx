import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { veraApi } from '../lib/api'
import VeraDateInput from '../components/VeraDateInput'
import VeraMoneyInput from '../components/VeraMoneyInput'
import UiToolbar from '../components/UiToolbar'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'
import './PurchasePage.css'

const money = value => `${Number(value || 0).toLocaleString('vi-VN', { maximumFractionDigits: 2 })}đ`
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const presets = [['all','Tất cả'],['yesterday','Hôm qua'],['today','Hôm nay'],['last_week','Tuần trước'],['this_week','Tuần này'],['last_month','Tháng trước'],['this_month','Tháng này'],['custom','Tùy chỉnh']]
const blank = () => ({ purchase_date: today(), item: '', quantity: 1, unit_price: '', note: '' })
const filtersEmpty = { date: '', item: '', amount: '', note: '', entered: '', user: '' }

function Modal({ title, busy, close, children }) {
  const ref = useRef(null), state = useRef({ busy, close })
  state.current = { busy, close }
  useEffect(() => {
    const node = ref.current, opener = document.activeElement, overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'; node.showModal()
    const cancel = event => { event.preventDefault(); if (!state.current.busy) state.current.close() }
    node.addEventListener('cancel', cancel)
    return () => { node.removeEventListener('cancel', cancel); node.close(); document.body.style.overflow = overflow; opener?.focus() }
  }, [])
  return createPortal(<dialog className="purchase-modal" ref={ref} aria-labelledby="purchase-modal-title">
    <header><h2 id="purchase-modal-title">{title}</h2><button disabled={busy} onClick={close} aria-label="Đóng">✕</button></header>{children}
  </dialog>, document.body)
}

export default function PurchasePage({ user }) {
  const admin = user?.role === 'admin'
  const [data,setData] = useState({ rows: [], permissions: {} }), [error,setError] = useState(''), [message,setMessage] = useState('')
  const [preset,setPreset] = useState('this_month'), [start,setStart] = useState(today()), [end,setEnd] = useState(today())
  const [filters,setFilters] = useState(filtersEmpty), [selected,setSelected] = useState([]), [busy,setBusy] = useState(false)
  const [editor,setEditor] = useState(null), [draft,setDraft] = useState([]), [modalError,setModalError] = useState(''), [history,setHistory] = useState(null)
  const [reload,setReload] = useState(0), [loading,setLoading] = useState(true)
  const importInput = useRef(null), importMode = useRef('append'), requestId = useRef('')
  const params = useMemo(() => ({ preset, ...(preset === 'custom' ? { start, end } : {}) }), [preset,start,end])
  useEffect(() => {
    let active = true
    setLoading(true); setError(''); setSelected([])
    veraApi.purchases(params).then(result => { if (active) setData(result) }).catch(e => { if (active) { setError(e.message); setData({ rows: [], permissions: {} }) } }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [params,reload])
  const rows = data.rows.filter(row => (!filters.date || row.purchase_date === filters.date)
    && row.item.toLocaleLowerCase('vi').includes(filters.item.toLocaleLowerCase('vi'))
    && (!filters.amount || String(row.amount).includes(filters.amount))
    && row.note.toLocaleLowerCase('vi').includes(filters.note.toLocaleLowerCase('vi'))
    && (!filters.entered || (row.entered_at && new Intl.DateTimeFormat('en-CA',{ timeZone:'Asia/Ho_Chi_Minh' }).format(new Date(row.entered_at)) === filters.entered))
    && row.entered_by.toLocaleLowerCase('vi').includes(filters.user.toLocaleLowerCase('vi')))
  const picked = rows.filter(row => selected.includes(row.id))
  const allowed = key => admin || data.permissions[`purchase_${key}`] === true
  const editable = row => admin || (row.entered_at && new Intl.DateTimeFormat('en-CA',{ timeZone:'Asia/Ho_Chi_Minh' }).format(new Date(row.entered_at)) === today())
  function open(row) {
    setEditor(row || {}); setDraft(row ? [{ ...row }] : [blank()]); setModalError(''); requestId.current = crypto.randomUUID()
  }
  async function save(event) {
    event.preventDefault(); setBusy(true); setModalError('')
    try {
      if (editor.id) await veraApi.editPurchase(editor.id, { ...draft[0], quantity: String(draft[0].quantity), revision: editor.revision })
      else await veraApi.createPurchases({ request_id: requestId.current, rows: draft })
      setEditor(null); setReload(n => n+1); setMessage('Đã lưu mua hàng trên server.')
    } catch(e) { setModalError(e.message) } finally { setBusy(false) }
  }
  async function run(action) {
    setBusy(true); setError(''); setMessage('')
    try { await action() } catch(e) { setError(e.message) } finally { setBusy(false) }
  }
  async function remove() {
    if (!window.confirm(`Xóa ${picked.length} dòng đã chọn?`)) return
    await run(async () => {
      try { for (const row of picked) await veraApi.deletePurchase(row.id,row.revision) }
      finally { setReload(n => n+1) }
    })
  }
  function chooseImport(mode) {
    if (mode === 'replace' && !window.confirm('Thay toàn bộ dữ liệu Nhập mua bằng file được chọn? Dữ liệu cũ được lưu trong lịch sử.')) return
    importMode.current = mode; importInput.current.click()
  }
  async function importFile(event) {
    const file = event.target.files[0]; event.target.value = ''; if (!file) return
    await run(async () => {
      const result = await veraApi.importPurchases(file,importMode.current)
      setMessage(`Đã xử lý ${result.source_rows} dòng; thêm mới ${result.inserted}, đã có ${result.skipped}. Tổng file: ${money(result.total)}.`)
      setReload(n => n+1)
    })
  }
  const filter = (key,value) => setFilters(old => ({ ...old,[key]:value }))
  return <section className="purchase-page" data-ui-key="page:purchases">
    <h1>Nhập mua</h1>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <div className="purchase-filters">
      <label>Thời gian<select value={preset} onChange={e=>setPreset(e.target.value)}>{presets.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      <label>Từ ngày<VeraDateInput value={preset === 'custom' ? start : data.start || ''} onChange={e=>{ setStart(e.target.value); if (preset !== 'custom' && data.end) setEnd(data.end); setPreset('custom') }} /></label>
      <label>Đến ngày<VeraDateInput value={preset === 'custom' ? end : data.end || ''} onChange={e=>{ setEnd(e.target.value); if (preset !== 'custom' && data.start) setStart(data.start); setPreset('custom') }} /></label>
      <label>Ngày mua<VeraDateInput value={filters.date} onChange={e=>filter('date',e.target.value)} /></label>
      <label>Hàng hóa<input value={filters.item} onChange={e=>filter('item',e.target.value)} placeholder="Tìm hàng hóa" /></label>
      <label>Thành tiền<input value={filters.amount} onChange={e=>filter('amount',e.target.value)} placeholder="Tìm số tiền" /></label>
      <label>Ghi chú / Người đặt<input value={filters.note} onChange={e=>filter('note',e.target.value)} /></label>
      <label>Ngày nhập<VeraDateInput value={filters.entered} onChange={e=>filter('entered',e.target.value)} /></label>
      <label>Người nhập<input value={filters.user} onChange={e=>filter('user',e.target.value)} /></label>
    </div>
    <UiToolbar layoutKey="purchases:periods">{presets.slice(0,-1).map(([key,label])=><button key={key} className={preset===key?'active':''} onClick={()=>setPreset(key)}>{label}</button>)}<button onClick={()=>setFilters(filtersEmpty)}>Xóa lọc chi tiết</button></UiToolbar>
    <UiToolbar layoutKey="purchases:actions">
      <strong>Tổng mua: {money(rows.reduce((sum,row)=>sum+Number(row.amount),0))} · {rows.length} dòng</strong>
      {allowed('create') && <button disabled={busy || loading} onClick={()=>open()}>Nhập mua hàng</button>}
      {allowed('edit') && <button disabled={busy || loading || picked.length!==1 || !editable(picked[0])} onClick={()=>open(picked[0])}>Sửa dòng đã chọn</button>}
      {allowed('delete') && <button disabled={busy || loading || !picked.length || !picked.every(editable)} onClick={remove}>Xóa dòng đã chọn</button>}
      {admin && <><button disabled={busy} onClick={()=>chooseImport('append')}>Import thêm mới</button><button disabled={busy} onClick={()=>chooseImport('replace')}>Import thay toàn bộ</button><button disabled={busy} onClick={()=>run(async()=>setHistory((await veraApi.purchaseAudit()).rows))}>Lịch sử</button></>}
      <button disabled={busy || loading} onClick={()=>run(()=>veraApi.exportPurchases(params))}>Xuất Excel theo thời gian</button><button disabled={busy} onClick={()=>setReload(n=>n+1)}>Làm mới</button>
    </UiToolbar>
    <input ref={importInput} hidden type="file" accept=".xlsb,.xlsx" onChange={importFile} />
    {loading ? <p role="status">Đang tải…</p> : <div className="purchase-table"><table><thead><tr>{['Chọn','Ngày mua','Chi tiết hàng hóa','Số lượng','Đơn giá','Thành tiền','Ghi chú / Người đặt','Ngày nhập','Giờ nhập','Người nhập'].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>
      {rows.map(row=><tr key={row.id}><td><input type="checkbox" aria-label={`Chọn ${row.item}`} checked={selected.includes(row.id)} onChange={e=>setSelected(old=>e.target.checked?[...old,row.id]:old.filter(id=>id!==row.id))} /></td>
        <td>{formatVeraDate(row.purchase_date)}</td><td>{row.item}</td><td>{row.quantity}</td><td>{money(row.unit_price)}</td><td>{money(row.amount)}</td><td>{row.note}</td><td>{row.entered_at ? new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(row.entered_at)).replaceAll('/','-') : '—'}</td><td>{row.entered_at ? new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(row.entered_at)) : '—'}</td><td>{row.entered_by || '—'}</td></tr>)}
      {!rows.length && <tr><td colSpan={10}>Không có dữ liệu trong khoảng đang chọn.</td></tr>}
    </tbody></table></div>}
    {editor && <Modal title={editor.id?'Sửa mua hàng':'Nhập mua hàng'} busy={busy} close={()=>setEditor(null)}><form onSubmit={save}>
      {modalError && <p role="alert">{modalError}</p>}
      {draft.map((row,index)=><div className="purchase-entry" key={index}>
        {['purchase_date','item','quantity','unit_price','amount','note'].map((key,i)=><label key={key}>{['Ngày mua hàng','Chi tiết hàng hóa','Số lượng','Đơn giá','Thành tiền','Ghi chú / Người đặt mua hàng'][i]}
          {key==='amount' ? (editor.id ? <VeraMoneyInput value={row.amount} disabled={busy} required onChange={e=>setDraft(old=>old.map((entry,n)=>n===index?{...entry,amount:e.target.value}:entry))} /> : <output>{money(Number(row.quantity)*Number(row.unit_price))}</output>) : (()=>{
            const props={ value:row[key], required:key!=='note', disabled:busy, onChange:e=>setDraft(old=>old.map((entry,n)=>n===index?{...entry,[key]:e.target.value,...(editor.id && ['quantity','unit_price'].includes(key) ? {amount:Math.round(Number(key==='quantity'?e.target.value:entry.quantity)*Number(key==='unit_price'?e.target.value:entry.unit_price)*100)/100} : {})}:entry)) }
            return key==='purchase_date'?<VeraDateInput {...props}/>:key==='unit_price'?<VeraMoneyInput {...props} max={100000000000}/>:<input {...props} type={key==='quantity' && !editor.id?'number':'text'} min={key==='quantity'?'0.0001':undefined} step={key==='quantity'?'0.0001':undefined} maxLength={key==='item'?2000:4000}/>
          })()}</label>)}
        {draft.length>1 && <button type="button" disabled={busy} onClick={()=>setDraft(old=>old.filter((_,n)=>n!==index))}>Bỏ dòng</button>}
      </div>)}
      <footer>{!editor.id && <button type="button" disabled={busy || draft.length>=100} onClick={()=>setDraft(old=>[...old,blank()])}>Thêm dòng</button>}<button disabled={busy} type="submit">{busy?'Đang lưu…':editor.id?'Lưu thay đổi':'Thêm hàng'}</button><button type="button" disabled={busy} onClick={()=>setEditor(null)}>Hủy</button></footer>
    </form></Modal>}
    {history && <Modal title="Lịch sử mua hàng (500 thao tác gần nhất)" busy={false} close={()=>setHistory(null)}>{history.length?history.map(row=><details key={row.id}><summary>{formatVeraDateTime(row.created_at)} · {row.actor} · {row.action} · #{row.entry_id}</summary><pre>{JSON.stringify({truoc:row.before_payload,sau:row.after_payload},null,2)}</pre></details>):<p>Chưa có thao tác sửa/xóa.</p>}</Modal>}
  </section>
}
