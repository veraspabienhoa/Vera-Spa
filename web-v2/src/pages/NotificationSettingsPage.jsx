import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import { BellRing, GripVertical, Search, Smartphone } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import './NotificationSettingsPage.css'
import NotificationEditorDialog from '../components/NotificationEditorDialog'
import { disablePushNotifications, enablePushNotifications, readPushState, syncExistingPushSubscription } from '../lib/pushNotifications'

const normalized = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g,'d').toLowerCase()
const recipientGroups = [
  ['group:nhanvien','Nhân viên'],['group:letan','Lễ tân'],['group:watchers','Người theo dõi'],
  ['group:leader','Leader'],
  ['group:quanly','Quản lý'],['group:giamdoc','Giám đốc'],['group:all','Tất cả tài khoản'],['group:admin','Admin'],
]
const recipientLabel = (id, options, groups = []) => recipientGroups.find(([key])=>key===id)?.[1] || groups.find(group=>group.key===id)?.label || options.find(person=>person.id===id)?.name || 'Tài khoản không còn hoạt động'
function Recipients({ options, groups = [], selected, onChange, source }) {
  const [search,setSearch] = useState('')
  const filtered=options.filter(item=>normalized(`${item.name} ${item.username} ${item.role}`).includes(normalized(search)))
  return <fieldset className="notification-recipients"><legend>Người nhận · {selected.filter(id=>!id.startsWith('group:')).length} tài khoản · {selected.filter(id=>id.startsWith('group:')).length} nhóm</legend>
    <div className="notification-recipient-groups" role="group" aria-label="Nhóm người nhận">{[...recipientGroups,...groups.map(group=>[group.key,group.label])].map(([key,label])=><label key={key}><input type="checkbox" checked={selected.includes(key)} disabled={key==='group:watchers' && source!=='leave_watch'} onChange={event=>onChange(event.target.checked?[...selected,key]:selected.filter(id=>id!==key))}/>{label}</label>)}</div>
    <small>Nhóm tự cập nhật theo tài khoản đang hoạt động. Người theo dõi chỉ áp dụng cho đúng ngày nghỉ được theo dõi.</small>
    <input aria-label="Tìm người nhận" placeholder="Tìm tên hoặc tài khoản…" value={search} onChange={event=>setSearch(event.target.value)}/>
    <div className="notification-selected">{selected.map(id=><button type="button" key={id} onClick={()=>onChange(selected.filter(value=>value!==id))}>{recipientLabel(id,options,groups)} ×</button>)}</div>
    <div className="notification-recipient-list">{filtered.map(item=><label key={item.id}><input type="checkbox" checked={selected.includes(item.id) || selected.includes('group:all') || selected.includes(`group:${item.role}`)} disabled={selected.includes('group:all') || selected.includes(`group:${item.role}`)} onChange={event=>onChange(event.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id))}/><span>{item.name}<small>{item.username} · {item.role}</small></span></label>)}{!filtered.length && <small>Không tìm thấy tài khoản.</small>}</div>
  </fieldset>
}
export default function NotificationSettingsPage({ user }) {
  usePageRefresh(() => reload(), () => Boolean(busy || editor))
  const [data,setData]=useState({settings:[],recipients:[],channels:[],revision:0})
  const [tasks,setTasks]=useState([]), [query,setQuery]=useState(''), [taskQuery,setTaskQuery]=useState('')
  const [editor,setEditor]=useState(null),[draft,setDraft]=useState(null)
  const [groupName,setGroupName]=useState(''),[groupMembers,setGroupMembers]=useState([])
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
  const [push,setPush]=useState({loading:true,supported:false,subscribed:false}),[pushBusy,setPushBusy]=useState(false)
  const dragged=useRef(null)
  const admin=String(user?.role || '').toLowerCase()==='admin'
  const reload=async()=>{setData(await veraApi.notificationSettings())}
  useEffect(()=>{let active=true;Promise.all([veraApi.notificationSettings(),admin?veraApi.notificationTasks():Promise.resolve({tasks:[]})]).then(([settings,result])=>{if(active){setData(settings);setTasks(result.tasks || [])}}).catch(err=>{if(active)setError(err.message)});return()=>{active=false}},[admin])
  useEffect(()=>{let active=true;syncExistingPushSubscription().catch(()=>readPushState()).then(state=>{if(active)setPush({...state,loading:false})}).catch(err=>{if(active)setPush({loading:false,supported:false,subscribed:false,reason:err.message})});return()=>{active=false}},[])
  const toggleDevice=async()=>{setPushBusy(true);setError('');try{const state=push.subscribed?await disablePushNotifications():await enablePushNotifications();setPush({...state,loading:false})}catch(err){setError(err.message || 'Không cập nhật được thiết bị.')}finally{setPushBusy(false)}}
  const perform=async action=>{
    if(busy)return
    setBusy(true);setError('');setNotice('')
    try{const result=await action();setData(result);setEditor(null);setDraft(null);setNotice('Đã lưu cấu hình thông báo.');window.dispatchEvent(new CustomEvent('vera-notification-settings-changed'))}
    catch(err){setError(err.message || 'Không lưu được cấu hình.')}finally{setBusy(false)}
  }
  const manageGroup=async action=>{setBusy(true);setError('');try{setData(await action());setGroupName('');setGroupMembers([]);setNotice('Đã cập nhật nhóm người nhận.')}catch(err){setError(err.message || 'Không cập nhật được nhóm.')}finally{setBusy(false)}}
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
    <section className="panel notification-device-panel"><Smartphone size={26}/><div><h3>Thông báo màn hình khóa</h3><p>Bật thông báo trên từng thiết bị. Admin có thể bật hoặc tắt từng loại thông báo thiết bị ở danh sách bên dưới. Trên iPhone/iPad, mở ứng dụng từ biểu tượng Màn hình chính.</p>{!push.loading && !push.supported && <small>{push.reason || 'Thiết bị không hỗ trợ Web Push.'}</small>}</div><button type="button" disabled={push.loading || pushBusy || !push.supported} onClick={toggleDevice}>{pushBusy?'Đang xử lý…':push.subscribed?'Tắt trên thiết bị này':'Bật trên thiết bị này'}</button></section>
    <StableFeedback>{error && !editor && <div className="error-box" role="alert">{error} <button disabled={busy} onClick={()=>{void reload().then(()=>{setError('');setEditor(null)}).catch(err=>setError(err.message))}}>Tải lại cấu hình</button></div>}
    {notice && <p role="status">{notice}</p>}</StableFeedback>
    <div className="notification-settings-toolbar"><label><Search size={16}/><input aria-label="Tìm thông báo" placeholder="Tìm thông báo…" value={query} onChange={event=>setQuery(event.target.value)}/></label>{admin && <button type="button" disabled={busy} onClick={()=>open(null)}>+ Tạo thông báo</button>}</div>
    {admin && <details className="notification-custom-groups"><summary>Nhóm người nhận tùy chỉnh</summary><div className="notification-settings-toolbar"><label>Tên nhóm<input value={groupName} maxLength={80} onChange={event=>setGroupName(event.target.value)} placeholder="Ví dụ: Trưởng ca"/></label><button type="button" disabled={busy || !groupName.trim() || !groupMembers.length} onClick={()=>void manageGroup(()=>veraApi.createNotificationGroup({label:groupName,members:groupMembers,revision:data.revision}))}>+ Thêm nhóm</button></div><div className="notification-group-member-list">{data.recipients?.map(person=><label key={person.id}><input type="checkbox" checked={groupMembers.includes(person.id)} onChange={event=>setGroupMembers(current=>event.target.checked?[...current,person.id]:current.filter(id=>id!==person.id))}/>{person.name} · {person.role}</label>)}</div>{data.groups?.map(group=><div className="notification-custom-group" key={group.key}><span>{group.label} · {group.members?.length || 0} tài khoản</span><button type="button" disabled={busy} onClick={()=>void manageGroup(()=>veraApi.deleteNotificationGroup(group.key,data.revision))}>Xóa nhóm</button></div>)}</details>}
    {editor && draft && <NotificationEditorDialog title={editor==='new'?'Tạo thông báo mới':draft.label} busy={busy} onClose={()=>{setEditor(null);setDraft(null);setError('')}}>
      {error && <div className="error-box" role="alert">{error}<button disabled={busy} onClick={()=>{void reload().then(()=>{setError('');setEditor(null);setDraft(null)}).catch(err=>setError(err.message))}}>Tải lại cấu hình</button></div>}
      {editor==='new' && <><label>Tên thông báo<input maxLength={120} value={draft.label} onChange={event=>setDraft({...draft,label:event.target.value})}/></label>
        <label>Tìm tác vụ<input aria-label="Tìm tác vụ" value={taskQuery} onChange={event=>setTaskQuery(event.target.value)} placeholder="Tìm module, thao tác, thông báo…"/></label>
        <label>Tác vụ kích hoạt<select aria-label="Tác vụ kích hoạt" value={draft.source_key} onChange={event=>{const task=tasks.find(item=>item.key===event.target.value);setDraft({...draft,source_key:event.target.value,label:draft.label || task?.label?.slice(0,120) || '',recipients:event.target.value==='leave_watch'?draft.recipients:draft.recipients.filter(id=>id!=='group:watchers')})}}><option value="">Chọn tác vụ…</option>{tasks.filter(item=>item.key===draft.source_key || normalized(`${item.label} ${item.group} ${item.description}`).includes(normalized(taskQuery))).map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label><small>Thông báo tác vụ được tạo sau khi API báo thành công. Nội dung mặc định không đính kèm dữ liệu nghiệp vụ.</small></>}
      <Recipients source={draft.source_key} options={data.recipients || []} groups={data.groups || []} selected={draft.recipients} onChange={recipients=>setDraft({...draft,recipients})}/>
      <fieldset><legend>Kênh thông báo</legend>{(data.channels || []).map(channel=><label className="notification-channel" key={channel.key}><input type="checkbox" checked={draft.channels.includes(channel.key)} onChange={event=>setDraft({...draft,channels:event.target.checked?[...draft.channels,channel.key]:draft.channels.filter(key=>key!==channel.key)})}/>{channel.label}</label>)}<small>Kênh đẩy cần người nhận bật thông báo trên thiết bị. Nếu chưa sẵn sàng, hệ thống giữ hàng đợi và thử lại.</small></fieldset>
      <div className="notification-settings-toolbar"><button type="button" disabled={busy || !draft.recipients.length || !draft.channels.length || (editor==='new' && (!draft.label.trim() || !draft.source_key))} onClick={()=>perform(()=>editor==='new'?veraApi.createNotification({...draft,revision:data.revision}):veraApi.updateNotificationSetting(editor,{...draft,revision:data.revision}))}>Lưu thông báo</button><button disabled={busy} onClick={()=>{setEditor(null);setDraft(null)}}>Hủy</button>{editor!=='new' && !data.settings.find(item=>item.key===editor)?.custom && <button disabled={busy} onClick={()=>perform(()=>veraApi.updateNotificationSetting(editor,{enabled:draft.enabled,reset_routing:true,revision:data.revision}))}>Khôi phục người nhận/kênh mặc định</button>}</div>
    </NotificationEditorDialog>}
    <small>Kéo tay nắm để sắp xếp; dùng ↑ / ↓ trên điện thoại hoặc bàn phím. Thứ tự được lưu cho toàn hệ thống.</small>
    <section className="notification-settings-grid">{visible.map(item=>{const index=data.settings.findIndex(row=>row.key===item.key);return <article className="notification-setting-card" key={item.key} onDragOver={event=>{if(admin && !busy){event.preventDefault();event.currentTarget.classList.add('drag-over')}}} onDragLeave={event=>event.currentTarget.classList.remove('drag-over')} onDrop={event=>{event.preventDefault();event.currentTarget.classList.remove('drag-over');reorder(dragged.current,item.key);dragged.current=null}}>
      <div className="notification-card-order"><button type="button" aria-label={`Kéo ${item.label}`} draggable={admin && !busy && !editor} disabled={!admin || busy || Boolean(editor)} onDragStart={event=>{dragged.current=item.key;event.dataTransfer.setData('text/plain',item.key);event.dataTransfer.effectAllowed='move'}} onDragEnd={()=>{dragged.current=null;document.querySelectorAll('.notification-setting-card.drag-over').forEach(node=>node.classList.remove('drag-over'))}}><GripVertical size={18}/></button><span>{index+1}</span><button type="button" aria-label={`Đưa ${item.label} lên`} disabled={!admin || busy || Boolean(editor) || index===0} onClick={()=>reorder(item.key,data.settings[index-1].key)}>↑</button><button type="button" aria-label={`Đưa ${item.label} xuống`} disabled={!admin || busy || Boolean(editor) || index===data.settings.length-1} onClick={()=>reorder(item.key,data.settings[index+1].key)}>↓</button></div>
      <div><h3>{item.label}</h3><p>{item.description}</p><small>Người nhận: {item.routed?item.recipients?.map(id=>recipientLabel(id,data.recipients || [],data.groups || [])).join(', '):item.audience}</small><small>Kênh: {item.routed?item.channels?.map(key=>data.channels.find(channel=>channel.key===key)?.label).join(', '):item.channel}</small></div>
      <div className="notification-card-actions">{!item.enabled && <button type="button" disabled={!admin || busy || Boolean(editor)} onClick={()=>perform(()=>veraApi.updateNotificationSetting(item.key,{enabled:true,revision:data.revision}))}>Loại đang tắt · Bật lại</button>}<div className="notification-channel-switches">{[['in_app','Trong ứng dụng'],['popup','Popup trong ứng dụng'],['push','Thông báo đẩy trên thiết bị']].map(([channel,label])=><label key={channel} className="notification-channel-check"><input type="checkbox" checked={item.enabled && item.channel_enabled?.[channel] !== false} disabled={!admin || busy || Boolean(editor) || !item.enabled} onChange={()=>perform(()=>veraApi.updateNotificationChannel(item.key,channel,{enabled:item.channel_enabled?.[channel]===false,revision:data.revision}))}/>{label}</label>)}</div>{admin && <button type="button" disabled={busy} onClick={()=>open(item)}>Người nhận / Kênh</button>}</div>
    </article>})}</section>
    {!visible.length && <p>Chưa có thông báo phù hợp.</p>}
  </div>
}
