import { BellRing, GripVertical, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import './NotificationSettingsPage.css'

const normalized = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g,'d').toLowerCase()
function Recipients({ options, selected, onChange }) {
  const [search,setSearch] = useState('')
  const filtered=options.filter(item=>normalized(`${item.name} ${item.username} ${item.role}`).includes(normalized(search)))
  return <fieldset className="notification-recipients"><legend>Người nhận · đã chọn {selected.length}</legend>
    <input aria-label="Tìm người nhận" placeholder="Tìm tên hoặc tài khoản…" value={search} onChange={event=>setSearch(event.target.value)}/>
    <div className="notification-selected">{options.filter(item=>selected.includes(item.id)).map(item=><button type="button" key={item.id} onClick={()=>onChange(selected.filter(id=>id!==item.id))}>{item.name} ×</button>)}</div>
    <div className="notification-recipient-list">{filtered.map(item=><label key={item.id}><input type="checkbox" checked={selected.includes(item.id)} onChange={event=>onChange(event.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/><span>{item.name}<small>{item.username} · {item.role}</small></span></label>)}{!filtered.length && <small>Không tìm thấy tài khoản.</small>}</div>
  </fieldset>
}
export default function NotificationSettingsPage({ user }) {
  const [data,setData]=useState({settings:[],recipients:[],channels:[],revision:0})
  const [tasks,setTasks]=useState([]), [query,setQuery]=useState(''), [taskQuery,setTaskQuery]=useState('')
  const [editor,setEditor]=useState(null),[draft,setDraft]=useState(null)
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
  const dragged=useRef(null)
  const admin=String(user?.role || '').toLowerCase()==='admin'
  const reload=async()=>{setData(await veraApi.notificationSettings())}
  useEffect(()=>{let active=true;Promise.all([veraApi.notificationSettings(),admin?veraApi.notificationTasks():Promise.resolve({tasks:[]})]).then(([settings,result])=>{if(active){setData(settings);setTasks(result.tasks || [])}}).catch(err=>{if(active)setError(err.message)});return()=>{active=false}},[admin])
  const perform=async action=>{
    if(busy)return
    setBusy(true);setError('');setNotice('')
    try{const result=await action();setData(result);setEditor(null);setDraft(null);setNotice('Đã lưu cấu hình thông báo.');window.dispatchEvent(new CustomEvent('vera-notification-settings-changed'))}
    catch(err){setError(err.message || 'Không lưu được cấu hình.')}finally{setBusy(false)}
  }
  const open=item=>{setEditor(item?.key || 'new');setDraft({label:item?.label || '',source_key:item?.source_key || '',enabled:item?.enabled ?? true,recipients:item?.recipients || [],channels:item?.channels?.length?item.channels:['in_app']});setTaskQuery('');setError('')}
  const reorder=(source,target)=>{
    if(!source || source===target || busy)return
    const keys=data.settings.map(item=>item.key), from=keys.indexOf(source), to=keys.indexOf(target)
    if(from<0 || to<0)return
    keys.splice(to,0,...keys.splice(from,1))
    void perform(()=>veraApi.orderNotifications({keys,revision:data.revision}))
  }
  const visible=data.settings.filter(item=>normalized(`${item.label} ${item.description}`).includes(normalized(query)))
  return <div className="notification-settings-page">
    <header className="panel notification-settings-head"><BellRing/><div><h2>THÔNG BÁO</h2><p>Chọn người nhận, kênh gửi và sắp xếp các thông báo của hệ thống.</p></div></header>
    {error && <div className="error-box" role="alert">{error} <button disabled={busy} onClick={()=>{void reload().then(()=>{setError('');setEditor(null)}).catch(err=>setError(err.message))}}>Tải lại cấu hình</button></div>}
    {notice && <p role="status">{notice}</p>}
    <div className="notification-settings-toolbar"><label><Search size={16}/><input aria-label="Tìm thông báo" placeholder="Tìm thông báo…" value={query} onChange={event=>setQuery(event.target.value)}/></label>{admin && <button type="button" disabled={busy} onClick={()=>open(null)}>+ Tạo thông báo</button>}</div>
    {editor && draft && <section className="panel notification-editor" aria-label={editor==='new'?'Tạo thông báo':'Cấu hình thông báo'}>
      <h3>{editor==='new'?'Tạo thông báo mới':draft.label}</h3>
      {editor==='new' && <><label>Tên thông báo<input maxLength={120} value={draft.label} onChange={event=>setDraft({...draft,label:event.target.value})}/></label>
        <label>Tìm tác vụ<input aria-label="Tìm tác vụ" value={taskQuery} onChange={event=>setTaskQuery(event.target.value)} placeholder="Tìm module, thao tác, thông báo…"/></label>
        <label>Tác vụ kích hoạt<select aria-label="Tác vụ kích hoạt" value={draft.source_key} onChange={event=>{const task=tasks.find(item=>item.key===event.target.value);setDraft({...draft,source_key:event.target.value,label:draft.label || task?.label?.slice(0,120) || ''})}}><option value="">Chọn tác vụ…</option>{tasks.filter(item=>item.key===draft.source_key || normalized(`${item.label} ${item.group} ${item.description}`).includes(normalized(taskQuery))).map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label><small>Thông báo tác vụ được tạo sau khi API báo thành công. Nội dung mặc định không đính kèm dữ liệu nghiệp vụ.</small></>}
      <Recipients options={data.recipients || []} selected={draft.recipients} onChange={recipients=>setDraft({...draft,recipients})}/>
      <fieldset><legend>Kênh thông báo</legend>{(data.channels || []).map(channel=><label className="notification-channel" key={channel.key}><input type="checkbox" checked={draft.channels.includes(channel.key)} onChange={event=>setDraft({...draft,channels:event.target.checked?[...draft.channels,channel.key]:draft.channels.filter(key=>key!==channel.key)})}/>{channel.label}</label>)}<small>Kênh đẩy cần người nhận bật thông báo trên thiết bị. Nếu chưa sẵn sàng, hệ thống giữ hàng đợi và thử lại.</small></fieldset>
      <div className="notification-settings-toolbar"><button type="button" disabled={busy || !draft.recipients.length || !draft.channels.length || (editor==='new' && (!draft.label.trim() || !draft.source_key))} onClick={()=>perform(()=>editor==='new'?veraApi.createNotification({...draft,revision:data.revision}):veraApi.updateNotificationSetting(editor,{...draft,revision:data.revision}))}>Lưu thông báo</button><button disabled={busy} onClick={()=>{setEditor(null);setDraft(null)}}>Hủy</button>{editor!=='new' && !data.settings.find(item=>item.key===editor)?.custom && <button disabled={busy} onClick={()=>perform(()=>veraApi.updateNotificationSetting(editor,{enabled:draft.enabled,reset_routing:true,revision:data.revision}))}>Khôi phục người nhận/kênh mặc định</button>}</div>
    </section>}
    <small>Kéo tay nắm để sắp xếp; dùng ↑ / ↓ trên điện thoại hoặc bàn phím. Thứ tự được lưu cho toàn hệ thống.</small>
    <section className="notification-settings-grid">{visible.map(item=>{const index=data.settings.findIndex(row=>row.key===item.key);return <article className="notification-setting-card" key={item.key} onDragOver={event=>{if(admin && !busy){event.preventDefault();event.currentTarget.classList.add('drag-over')}}} onDragLeave={event=>event.currentTarget.classList.remove('drag-over')} onDrop={event=>{event.preventDefault();event.currentTarget.classList.remove('drag-over');reorder(dragged.current,item.key);dragged.current=null}}>
      <div className="notification-card-order"><button type="button" aria-label={`Kéo ${item.label}`} draggable={admin && !busy && !editor} disabled={!admin || busy || Boolean(editor)} onDragStart={event=>{dragged.current=item.key;event.dataTransfer.setData('text/plain',item.key);event.dataTransfer.effectAllowed='move'}} onDragEnd={()=>{dragged.current=null;document.querySelectorAll('.notification-setting-card.drag-over').forEach(node=>node.classList.remove('drag-over'))}}><GripVertical size={18}/></button><span>{index+1}</span><button type="button" aria-label={`Đưa ${item.label} lên`} disabled={!admin || busy || Boolean(editor) || index===0} onClick={()=>reorder(item.key,data.settings[index-1].key)}>↑</button><button type="button" aria-label={`Đưa ${item.label} xuống`} disabled={!admin || busy || Boolean(editor) || index===data.settings.length-1} onClick={()=>reorder(item.key,data.settings[index+1].key)}>↓</button></div>
      <div><h3>{item.label}</h3><p>{item.description}</p><small>Người nhận: {item.routed?item.recipients?.map(id=>data.recipients.find(person=>person.id===id)?.name || 'Tài khoản không còn hoạt động').join(', '):item.audience}</small><small>Kênh: {item.routed?item.channels?.map(key=>data.channels.find(channel=>channel.key===key)?.label).join(', '):item.channel}</small></div>
      <div className="notification-card-actions"><button type="button" aria-pressed={item.enabled} disabled={!admin || busy || Boolean(editor)} onClick={()=>perform(()=>veraApi.updateNotificationSetting(item.key,{enabled:!item.enabled,revision:data.revision}))}>{item.enabled?'Đang bật':'Đã tắt'}</button>{admin && <button type="button" disabled={busy} onClick={()=>open(item)}>Người nhận / Kênh</button>}</div>
    </article>})}</section>
    {!visible.length && <p>Chưa có thông báo phù hợp.</p>}
  </div>
}
