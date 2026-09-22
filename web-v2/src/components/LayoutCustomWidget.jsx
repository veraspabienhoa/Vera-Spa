import VeraDateInput from './VeraDateInput'
import UiToolbar from './UiToolbar'
import { customKinds, isCustomContainer } from '../lib/layoutSelection'
import { formatVeraDate } from '../lib/veraDate'

const parseCustomTable = text => String(text || 'Cột 1 | Cột 2\nDữ liệu 1 | Dữ liệu 2').split('\n').slice(0,101).map(line=>line.split('|').slice(0,12).map(cell=>cell.trim()))
export default function LayoutCustomWidget({ id, item, editing, destination, items, values, applied, onValue, onApply }) {
  const kind=item.custom_kind,label=item.custom_text || customKinds[kind]
  const props={'data-ui-key':id,'data-ui-origin':destination || 'l-custom-root','data-layout-key':id,'data-layout-editable':editing?'true':'false',className:`layout-custom-${kind}`,'aria-label':`${customKinds[kind]} tùy chỉnh`}
  if(isCustomContainer(item))return <UiToolbar {...props}><span className="layout-custom-caption">{label}</span></UiToolbar>
  if(kind==='text')return <div {...props}>{item.custom_text || (editing?'Text mới — nhập nội dung':'')}</div>
  if(kind==='table'){
    const [headers,...rows]=parseCustomTable(item.custom_text)
    const filters=Object.entries(items).filter(([,control])=>control.custom_target===id && ['search','dropdown','date'].includes(control.custom_kind) && !control.hidden)
    const hasApply=Object.values(items).some(control=>control.custom_target===id && control.custom_kind==='filter' && !control.hidden)
    const state=hasApply?applied:values
    const shown=rows.filter(row=>filters.every(([key,control])=>{
      const value=state[key];if(!value)return true
      const needle=(control.custom_kind==='date'?formatVeraDate(value):value).toLocaleLowerCase('vi')
      return control.custom_kind==='search'?row.join(' ').toLocaleLowerCase('vi').includes(needle):row.some(cell=>cell.toLocaleLowerCase('vi')===needle)
    }))
    return <div {...props}><table><thead><tr>{headers.map((h,i)=><th key={i}>{h}</th>)}</tr></thead><tbody>{shown.map((row,i)=><tr key={i}>{headers.map((_,j)=><td key={j}>{row[j] || ''}</td>)}</tr>)}</tbody></table>{!shown.length && <small>Không có dữ liệu phù hợp.</small>}</div>
  }
  if(kind==='search')return <div {...props}><input aria-label={label} placeholder={label} type="search" value={values[id] || ''} onChange={e=>onValue(id,e.target.value)}/></div>
  if(kind==='dropdown')return <div {...props}><select aria-label={label} value={values[id] || ''} onChange={e=>onValue(id,e.target.value)}><option value="">{label}</option>{[...new Set((item.custom_options || 'Lựa chọn 1\nLựa chọn 2').split('\n').map(v=>v.trim()).filter(Boolean))].map(value=><option key={value} value={value}>{value}</option>)}</select></div>
  if(kind==='date')return <div {...props}><VeraDateInput aria-label={label} value={values[id] || ''} onChange={e=>onValue(id,e.target.value)}/></div>
  return <div {...props}><button type="button" disabled={!item.custom_target} onClick={()=>onApply(item.custom_target)}>{label || 'Lọc'}</button></div>
}
