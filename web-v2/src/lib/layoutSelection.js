export const customKinds = {box:'Box',text:'Text',frame:'Khung cha',row:'Dòng',search:'Search box',dropdown:'Dropdown list',date:'Date picker',table:'Table',filter:'Button filter'}
export const isCustomContainer = item => ['frame','row','box'].includes(item?.custom_kind)
export function selectionNodes(keys) {
  const nodes=keys.map(key=>document.querySelector(`[data-layout-key="${key}"]`)).filter(node=>node?.isConnected)
  // A selected parent already moves its descendants; never transform a child twice.
  return nodes.filter(node=>!nodes.some(parent=>parent!==node && parent.contains(node)))
}
export function boundingSelection(nodes) {
  const rects=nodes.map(node=>node.getBoundingClientRect())
  if(!rects.length)return null
  const left=Math.min(...rects.map(r=>r.left)),top=Math.min(...rects.map(r=>r.top)),right=Math.max(...rects.map(r=>r.right)),bottom=Math.max(...rects.map(r=>r.bottom))
  return {left,top,right,bottom,width:right-left,height:bottom-top}
}
const bounded=n=>Math.max(-2400,Math.min(2400,Math.round(n)))
export function alignSelection(items,nodes,mode) {
  const bounds=boundingSelection(nodes),next={...items}
  if(!bounds)return next
  nodes.forEach(node=>{
    const key=node.dataset.layoutKey,r=node.getBoundingClientRect(),item=next[key] || {}
    let dx=0,dy=0
    if(mode==='left')dx=bounds.left-r.left
    if(mode==='center-x')dx=(bounds.left+bounds.right-r.left-r.right)/2
    if(mode==='right')dx=bounds.right-r.right
    if(mode==='top')dy=bounds.top-r.top
    if(mode==='center-y')dy=(bounds.top+bounds.bottom-r.top-r.bottom)/2
    if(mode==='bottom')dy=bounds.bottom-r.bottom
    next[key]={...item,offset_x:bounded((item.offset_x || 0)+dx),offset_y:bounded((item.offset_y || 0)+dy)}
  })
  return next
}
export function removeLayoutItems(items,keys) {
  const next={...items},removed=new Set(keys.filter(key=>items[key]?.custom_kind))
  let changed=true
  while(changed){changed=false;Object.entries(items).forEach(([key,item])=>{if(item.custom_kind && removed.has(item.move_to) && !removed.has(key)){removed.add(key);changed=true}})}
  keys.forEach(key=>{if(!removed.has(key))next[key]={...next[key],hidden:true}})
  removed.forEach(key=>delete next[key])
  Object.entries(next).forEach(([key,item])=>{
    if(removed.has(item.move_to)){next[key]={...item};delete next[key].move_to;delete next[key].parent;delete next[key].order}
    if(removed.has(item.custom_target)){next[key]={...next[key]};delete next[key].custom_target}
  })
  return next
}
export function translateSelection(items,members,dx,dy) {
  // Clamp one shared delta so a group never loses its spacing at the API limits.
  const axis=(delta,name)=>Math.max(Math.max(...members.map(m=>-2400-(m.original?.[name] || 0))),Math.min(Math.min(...members.map(m=>2400-(m.original?.[name] || 0))),delta))
  const x=axis(dx,'offset_x'),y=axis(dy,'offset_y'),next={...items}
  members.forEach(({key,original})=>{next[key]={...next[key],offset_x:(original?.offset_x || 0)+x,offset_y:(original?.offset_y || 0)+y}})
  return next
}
