import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiCustomText from '../components/UiCustomText'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import VeraMoneyInput from '../components/VeraMoneyInput'
const empty = { sku:'', name:'', category:'', unit:'Cái', price:0, active:true, note:'', revision:0 }
export default function ProductSettings() {
  usePageRefresh(() => load(), () => Boolean(busy || form))
  const [products,setProducts]=useState([]), [form,setForm]=useState(null), [query,setQuery]=useState('')
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [notice,setNotice]=useState('')
  const load=async()=>{setBusy(true);setError('');try{setProducts((await veraApi.products()).products)}catch(e){setError(e.message)}finally{setBusy(false)}}
  useEffect(()=>{void load()},[])
  const save=async event=>{event.preventDefault();setBusy(true);setError('');setNotice('');try{
    const result=await veraApi.saveProduct(form)
    setProducts(current=>[...current.filter(p=>p.id!==result.product.id),result.product].sort((a,b)=>a.name.localeCompare(b.name,'vi')))
    setForm(null);setNotice('Đã lưu sản phẩm cho toàn hệ thống.')
  }catch(e){setError(e.message)}finally{setBusy(false)}}
  const choose=value=>{if(form && !window.confirm('Bỏ thay đổi chưa lưu?'))return;setError('');setNotice('');setForm(value)}
  const rows=products.filter(p=>`${p.sku} ${p.name} ${p.category}`.toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi')))
  return <section data-ui-key="u-3e112a1e7a5d" className="panel product-settings"><h2>Cài đặt sản phẩm</h2>
    <div data-ui-key="u-ea49f9ad90b8" className="product-actions"><input aria-label="Tìm sản phẩm" placeholder="Tìm mã, tên, nhóm sản phẩm…" value={query} onChange={e=>setQuery(e.target.value)}/><button data-ui-key="u-8e840b29d46e" className="secondary-button" disabled={busy} onClick={load}><UiCustomText uiKey="u-8e840b29d46e">Làm mới</UiCustomText></button><button data-ui-key="u-55ebe91a50b7" className="primary-button" disabled={busy} onClick={()=>choose({...empty})}><UiCustomText uiKey="u-55ebe91a50b7">Thêm sản phẩm</UiCustomText></button></div>
    <StableFeedback>{error && <p className="error-box" role="alert">{error}</p>}{notice && <p className="success-box" role="status">{notice}</p>}</StableFeedback>
    {form && <form onSubmit={save}><fieldset disabled={busy} className="product-form"><legend>{form.id?'Sửa sản phẩm':'Thêm sản phẩm'}</legend>{[['sku','Mã sản phẩm',60],['name','Tên sản phẩm',150],['category','Nhóm sản phẩm',120],['unit','Đơn vị tính',40]].map(([key,label,maxLength])=><label key={key}>{label}<input required={key!=='category'} maxLength={maxLength} value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}/></label>)}<label>Giá bán (đ)<VeraMoneyInput value={form.price} onChange={e=>setForm({...form,price:e.target.value})}/></label><label className="product-active"><input type="checkbox" checked={form.active} onChange={e=>setForm({...form,active:e.target.checked})}/> Đang sử dụng</label><label className="product-note">Ghi chú<textarea maxLength={2000} value={form.note} onChange={e=>setForm({...form,note:e.target.value})}/></label><div data-ui-key="u-93eb6b1fc2a2" className="product-actions"><button data-ui-key="u-5f5bdc8214a0" type="button" className="secondary-button" onClick={()=>choose(null)}><UiCustomText uiKey="u-5f5bdc8214a0">Hủy</UiCustomText></button><button data-ui-key="u-ea3a0783f6b1" type="submit" className="primary-button"><UiCustomText uiKey="u-ea3a0783f6b1">Lưu sản phẩm</UiCustomText></button></div></fieldset></form>}
    {busy && <p role="status">Đang xử lý…</p>}
    <table data-ui-key="u-6ebc422c36f2"><thead><tr><th data-ui-key="u-d7e78f1d37b8"><UiCustomText uiKey="u-d7e78f1d37b8">Mã / Tên</UiCustomText></th><th data-ui-key="u-695317813227"><UiCustomText uiKey="u-695317813227">Nhóm</UiCustomText></th><th data-ui-key="u-c9cc50401ed5"><UiCustomText uiKey="u-c9cc50401ed5">Đơn vị</UiCustomText></th><th data-ui-key="u-2c422fd7f756"><UiCustomText uiKey="u-2c422fd7f756">Giá bán</UiCustomText></th><th data-ui-key="u-c3c78237e89f"><UiCustomText uiKey="u-c3c78237e89f">Trạng thái</UiCustomText></th><th data-ui-key="u-f0b4be7a6a45"><UiCustomText uiKey="u-f0b4be7a6a45">Sửa</UiCustomText></th></tr></thead><tbody>{rows.map(p=><tr key={p.id}><td><strong>{p.name}</strong><small>{p.sku}</small>{p.note && <small>{p.note}</small>}</td><td>{p.category||'—'}</td><td>{p.unit}</td><td>{Number(p.price).toLocaleString('vi-VN')} đ</td><td>{p.active?'Đang dùng':'Ngừng dùng'}</td><td><button data-ui-key="u-a9cf32424f04" type="button" className="secondary-button" disabled={busy} onClick={()=>choose({...p})}><UiCustomText uiKey="u-a9cf32424f04">Sửa</UiCustomText></button></td></tr>)}</tbody></table>{!busy&&!rows.length&&<p>Chưa có sản phẩm phù hợp.</p>}
  </section>
}
