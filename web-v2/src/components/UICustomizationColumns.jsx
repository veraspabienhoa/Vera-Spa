import { useEffect, useState } from 'react'
export default function UICustomizationColumns({ page, items, onChange }) {
  const [tables,setTables]=useState([])
  useEffect(()=>{
    const read=()=>setTables([...document.querySelectorAll('.main-area table')].map((table,index)=>({
      key:table.dataset.uiKey||String(index),name:table.getAttribute('aria-label')||table.querySelector('caption')?.textContent||`Bảng ${index+1}`,
      columns:[...table.querySelectorAll('thead tr:first-child th')].filter(th=>th.dataset.uiKey).map(th=>({key:th.dataset.layoutKey||th.dataset.uiKey,label:th.textContent?.trim()||'Cột chọn',width:Math.round(th.getBoundingClientRect().width)})),
    })).filter(table=>table.columns.length))
    read()
  },[page])
  return <section className="appearance-card"><h2>Bảng trong trang đang mở</h2>
    {!tables.length && <p>Mở trang có bảng dữ liệu rồi chọn Chỉnh bố cục để chỉnh độ rộng cột của trang đó.</p>}
    {tables.map(table=><div key={table.key}><strong>{table.name}</strong><div className="appearance-grid">{table.columns.map((column,index)=><label key={`${column.key}-${index}`} className="appearance-field"><span>{column.label}</span><input type="number" min="32" max="600" placeholder={String(column.width)} value={items[column.key]?.width??''} onChange={event=>onChange(column.key,event.target.value===''?undefined:Number(event.target.value))}/></label>)}</div><button type="button" onClick={()=>table.columns.forEach(column=>onChange(column.key,undefined))}>Vừa màn hình / Khôi phục độ rộng</button></div>)}
  </section>
}
