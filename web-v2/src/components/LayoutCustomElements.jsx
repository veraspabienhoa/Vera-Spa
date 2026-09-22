import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import LayoutCustomWidget from './LayoutCustomWidget'
import { customKinds } from '../lib/layoutSelection'

// Only our empty portal host is inserted into the page; business nodes are untouched.
function CustomGroup({ anchor, destination, entries, editing, widgets }) {
 const [host,setHost]=useState(null)
 useEffect(()=>{
  const root=document.querySelector('.app-shell');if(!root)return undefined
  const slot=document.createElement('div');slot.className='layout-custom-host'
  const mount=()=>{
   const group=destination && root.querySelector(`[data-ui-dropzone="${destination}"]`)
   if(group){slot.style.display='contents';if(slot.parentElement!==group)group.append(slot);return}
   slot.style.display=''
   const target=anchor && root.querySelector(`[data-layout-key="${anchor}"],[data-ui-key="${anchor}"]`)
   const fallback=root.querySelector('.page-content')
   const parent=target?.parentElement
   if(anchor && (!target || !parent || parent.closest('table,button,a,label,select') || target.closest('.layout-designer'))) {slot.remove();return}
   if(slot.isConnected)return
   if(target)target.after(slot);else fallback?.append(slot)
  }
  mount();setHost(slot)
  const observer=new MutationObserver(mount);observer.observe(root,{childList:true,subtree:true})
  return()=>{observer.disconnect();slot.remove()}
 },[anchor,destination])
 if(!host)return null
 return createPortal(entries.map(([key,item])=><LayoutCustomWidget key={key} id={key} item={item} editing={editing} destination={destination} {...widgets}/>),host)
}
export default function LayoutCustomElements({items,page,editing}) {
 const [values,setValues]=useState({}),[applied,setApplied]=useState({})
 const widgets={items,values,applied,onValue:(key,value)=>setValues(current=>({...current,[key]:value})),onApply:target=>setApplied(current=>({...current,...Object.fromEntries(Object.entries(values).filter(([key])=>items[key]?.custom_target===target))}))}
 const groups=new Map()
 Object.entries(items).filter(([key,item])=>/^l-custom-[a-z0-9-]+$/.test(key)&&Object.hasOwn(customKinds,item.custom_kind)&&item.custom_page===page).sort((a,b)=>(a[1].order||0)-(b[1].order||0)).forEach(entry=>{const anchor=entry[1].custom_anchor||'',destination=entry[1].move_to||'';if(!/^(?:[lu]-[a-z0-9-]+)?$/.test(anchor)||!/^(?:[lu]-[a-z0-9-]+)?$/.test(destination))return;const group=JSON.stringify([anchor,destination]);if(!groups.has(group))groups.set(group,[]);groups.get(group).push(entry)})
 return [...groups].map(([group,entries])=>{const [anchor,destination]=JSON.parse(group);return <CustomGroup key={`${page}:${group}`} anchor={anchor} destination={destination} entries={entries} editing={editing} widgets={widgets}/>})
}
