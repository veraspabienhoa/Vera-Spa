import { useEffect, useRef, useState } from 'react'
import EmployeeProfileModal from './EmployeeProfileModal'
import VeraDateInput from './VeraDateInput'
import { veraApi } from '../lib/api'
import { formatVeraDateTime } from '../lib/veraDate'
import { TOUR_DATE_PRESETS, tourDateRange } from '../lib/liveTourFilters'
import { allowedTourPresets } from '../lib/liveTourDatePermissions'
import { invoiceMoneyValues } from '../lib/liveTourInvoiceMoney'
import './LiveTourInvoiceExport.css'

const serviceLabel = row => (row.entries || []).map(e=>e.service).filter(Boolean).join(' · ') || row.service || row.services || 'Dịch vụ'
const money = value => Number(value || 0).toLocaleString('vi-VN') + ' đ'
export default function LiveTourInvoiceExport({ datePolicy, onClose }) {
  const allowed = allowedTourPresets(datePolicy, 'invoices')
  const [preset, setPreset] = useState(allowed.includes('today') ? 'today' : allowed[0] || '')
  const [from, setFrom] = useState(tourDateRange('today').date_from)
  const [to, setTo] = useState(tourDateRange('today').date_to)
  const [search, setSearch] = useState(''), [searchBy, setSearchBy] = useState('bill_no')
  const [page, setPage] = useState(1), [pages, setPages] = useState(1)
  const [rows, setRows] = useState([]), [selected, setSelected] = useState({})
  const [service, setService] = useState(true), [tip, setTip] = useState(true)
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [preview, setPreview] = useState(null)
  const urls = useRef([]), alive = useRef(true)
  useEffect(() => { const createdUrls = urls.current; alive.current = true; return () => { alive.current = false; createdUrls.forEach(URL.revokeObjectURL) } }, [])
  const valid = allowed.includes(preset) && (preset !== 'custom' || (from && to && from <= to))
  useEffect(() => {
    setSelected({}); setPreview(null); setPage(1)
  }, [preset, from, to])
  useEffect(() => {
    const controller = new AbortController()
    setRows([]); setLoading(true); setError('')
    const timer = setTimeout(() => {
      if (!valid) { setLoading(false); return }
      veraApi.liveTourCollection('invoices', { preset, ...(preset === 'custom' ? { date_from: from, date_to: to } : {}), [searchBy]: search, page, page_size: 25 }, { signal: controller.signal })
        .then(result => { if (!controller.signal.aborted) { setRows(result.data?.state?.invoices || []); setPages(result.pages || 1) } })
        .catch(err => { if (!controller.signal.aborted) setError(err.message) })
        .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [preset, from, to, searchBy, search, page, valid])
  const choose = (invoice, checked) => {
    setPreview(null)
    setSelected(old => { const next = { ...old }; if (checked) { if (Object.keys(next).length >= 50) return old; next[invoice.id] = invoice } else delete next[invoice.id]; return next })
  }
  const exportFile = async (format, action) => {
    setBusy(true); setError('')
    try {
      const blob = await veraApi.exportSelectedInvoices(format, { ids: Object.keys(selected), service, tip, preset, date_from: preset === 'custom' ? from : '', date_to: preset === 'custom' ? to : '' })
      if (!alive.current) return
      const url = URL.createObjectURL(blob); urls.current.push(url)
      if (action === 'download') { const a = document.createElement('a'); a.href = url; a.download = `VERA_HoaDon.${format}`; document.body.append(a); a.click(); a.remove() }
      else setPreview({ url, format, print: action === 'print' })
    } catch (err) { if (alive.current) setError(err.message) }
    finally { if (alive.current) setBusy(false) }
  }
  const count = Object.keys(selected).length
  const chosen = Object.values(selected)
  const sums = chosen.reduce((sum, row) => { const v = invoiceMoneyValues(row); return {service:sum.service+v.service, discount:sum.discount+v.discount, tip:sum.tip+v.tip, total:sum.total+v.total} }, {service:0,discount:0,tip:0,total:0})
  const disabled = busy || !valid || !count || (!service && !tip)
  return <EmployeeProfileModal className="invoice-export-modal" labelledBy="invoice-export-title" onClose={onClose} busy={busy}>
    <header><h2 id="invoice-export-title">Xuất hóa đơn</h2><button type="button" onClick={onClose} disabled={busy}>Đóng</button></header>
    <div className="invoice-export-layout"><div className="invoice-export-selection">
    <div className="invoice-export-tools">
      <label>Thời gian<select value={preset} disabled={busy} onChange={e => setPreset(e.target.value)}>{TOUR_DATE_PRESETS.filter(([id]) => allowed.includes(id)).map(([id,label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      {preset === 'custom' && <><label>Từ ngày<VeraDateInput value={from} onChange={e=>setFrom(e.target.value)} disabled={busy}/></label><label>Đến ngày<VeraDateInput value={to} onChange={e=>setTo(e.target.value)} disabled={busy}/></label></>}
      <label>Tìm theo<select value={searchBy} disabled={busy} onChange={e=>{setSearchBy(e.target.value);setPage(1)}}><option value="bill_no">Mã hóa đơn</option><option value="customer">Khách hàng</option></select></label>
      <label>Tìm kiếm<input value={search} disabled={busy} placeholder="Nhập mã hóa đơn hoặc tên khách…" onChange={e=>{setSearch(e.target.value);setPage(1)}}/></label>
    </div>
    <div className="invoice-export-options"><label><input type="checkbox" checked={service} disabled={busy} onChange={e=>{setService(e.target.checked);setPreview(null)}}/> Dịch vụ</label><label><input type="checkbox" checked={tip} disabled={busy} onChange={e=>{setTip(e.target.checked);setPreview(null)}}/> Tiền tip</label></div>
    {!valid && <p role="alert">Chọn khoảng ngày hợp lệ trong phạm vi được cấp quyền.</p>}
    {!service && !tip && <p role="alert">Chọn ít nhất Dịch vụ hoặc Tiền tip.</p>}
    {error && <p role="alert" data-system-feedback>{error}</p>}
    <div className="invoice-export-table"><table><thead><tr><th><input aria-label="Chọn tất cả hóa đơn trang này" type="checkbox" disabled={busy || loading || !rows.length} checked={rows.length > 0 && rows.every(row=>selected[row.id])} onChange={e=>rows.forEach(row=>choose(row,e.target.checked))}/></th><th>Mã hóa đơn</th><th>Ngày</th><th>Khách hàng</th>{service && <><th>Dịch vụ</th><th>Tiền dịch vụ</th><th>Giảm giá</th></>}{tip && <th>Tiền tip</th>}<th>Tổng tiền đã chọn</th></tr></thead><tbody>{rows.map(row=>{
      const values = invoiceMoneyValues(row)
      return <tr key={row.id}><td><input type="checkbox" aria-label={`Chọn ${row.bill_no}`} checked={Boolean(selected[row.id])} disabled={busy || (!selected[row.id] && count>=50)} onChange={e=>choose(row,e.target.checked)}/></td><td>{row.bill_no}</td><td>{formatVeraDateTime(row.effective_at || row.recorded_at || row.created_at)}</td><td>{row.customer_name || 'Khách lẻ'}</td>{service && <><td>{serviceLabel(row)}</td><td>{money(values.service)}</td><td>{money(values.discount)}</td></>}{tip && <td>{money(values.tip)}</td>}<td>{money(service ? values.total-(tip ? 0 : values.tip) : tip ? values.tip : 0)}</td></tr>
    })}</tbody></table></div>
    {loading ? <p role="status">Đang tải hóa đơn…</p> : !rows.length && <p>Không có hóa đơn phù hợp.</p>}
    <div className="invoice-export-tools"><button disabled={busy || loading || page<=1} onClick={()=>setPage(page-1)}>Trang trước</button><span>Trang {page}/{pages}</span><button disabled={busy || loading || page>=pages} onClick={()=>setPage(page+1)}>Trang sau</button><strong>Đã chọn {count}/50 hóa đơn</strong><button disabled={busy || !count} onClick={()=>{setSelected({});setPreview(null)}}>Bỏ chọn tất cả</button></div>
    <footer className="invoice-export-tools">{[['pdf','print','In'],['pdf','view','Xem PDF'],['pdf','download','Tải PDF'],['png','view','Xem PNG'],['png','download','Tải PNG']].map(([format,action,label])=><button type="button" key={label} disabled={disabled} onClick={()=>exportFile(format,action)}>{label}</button>)}{busy && <span role="status">Đang tạo hóa đơn…</span>}</footer>
    </div><aside className="invoice-export-receipt-panel">
      <h3>Xem trước hóa đơn gộp ({count} hóa đơn)</h3>
      {!count ? <p>Chọn hóa đơn bên trái để xem trước.</p> : <article className="invoice-export-receipt">
        <h2>VERA SPA</h2><p>193 Trương Định, Tam Hiệp, Đồng Nai</p><h3>HÓA ĐƠN DỊCH VỤ</h3>
        <div className="invoice-export-receipt-scroll"><table><thead><tr><th>STT</th><th>{service ? 'Dịch vụ' : 'Nội dung'}</th><th>Thành tiền</th></tr></thead><tbody>{chosen.map((row,index)=>{const v=invoiceMoneyValues(row);return <tr key={row.id}><td>{index+1}</td><td>{service ? serviceLabel(row) : 'Tiền tip'}</td><td>{money(service ? v.total-(tip ? 0 : v.tip) : tip ? v.tip : 0)}</td></tr>})}</tbody></table></div>
        <dl>{service && <><dt>Tiền dịch vụ</dt><dd>{money(sums.service)}</dd><dt>Giảm giá</dt><dd>{money(sums.discount)}</dd></>}{tip && <><dt>Tiền tip</dt><dd>{money(sums.tip)}</dd></>}<dt><strong>Tổng tiền</strong></dt><dd><strong>{money(service ? sums.total-(tip ? 0 : sums.tip) : tip ? sums.tip : 0)}</strong></dd></dl>
      </article>}
    {preview && <section className="invoice-export-preview"><h3>Xem trước</h3>{preview.format === 'png' ? <img src={preview.url} alt="Các hóa đơn đã chọn"/> : <><iframe title="Xem hóa đơn PDF" src={preview.url} onLoad={e=>{if(preview.print) { try { e.currentTarget.contentWindow.focus();e.currentTarget.contentWindow.print() } catch { setError('Hãy mở PDF và chọn In trong trình xem của thiết bị.') } }}}/><a href={preview.url} target="_blank" rel="noopener noreferrer">Mở PDF để xem / in trên thiết bị</a></>}</section>}
    </aside></div>
  </EmployeeProfileModal>
}
