import { customKinds, isCustomContainer, selectionNodes, boundingSelection, alignSelection, distributeSelection, removeLayoutItems, translateSelection } from '../lib/layoutSelection'
import { createPortal } from 'react-dom'
import { freeMovePosition } from '../lib/layoutFreeMove'
import useLayoutToolScale from './useLayoutToolScale'
import useLayoutPanelFrame from './useLayoutPanelFrame'
import LayoutToolGuide from './LayoutToolGuide'
import LayoutCustomElements from './LayoutCustomElements'
import LayoutResizeOverlay from './LayoutResizeOverlay'
import { readLayoutMetrics } from '../lib/layoutMetrics'
import UIVisualStyleControls from './UIVisualStyleControls'
import { useEffect, useRef, useState, useMemo } from 'react'
import { getLayoutTargets, canRelocate } from '../lib/uiLayoutTargets'
import { veraApi } from '../lib/api'
import { layoutCandidates, layoutCss, layoutKey, legacyLayoutKey } from '../lib/sharedLayout'
import './LayoutDesigner.css'
import registry from '../../../vera_ui_registry.json'
import { publishCustomization } from '../lib/uiCustomizationStore'
import UICustomizationColumns from './UICustomizationColumns'
import AppearanceSettingsPage from '../pages/AppearanceSettingsPage'
import { formatVeraDateTime } from '../lib/veraDate'

export default function LayoutDesigner({ user, page, open = false, onClose, initialTab }) {
  const [panelHidden, setPanelHidden] = useState(false)
  const panelFrame = useLayoutPanelFrame()
  const toolScale = useLayoutToolScale()
  const textEditor = useRef(null)
  const [guideTool, setGuideTool] = useState('')
  const [newKey, setNewKey] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const resizeOriginal = useRef(null)
  const [inlineTarget, setInlineTarget] = useState(null)
  const [tab, setTab] = useState(['rooms','columns','history'].includes(initialTab) ? initialTab : 'object')
  const [history, setHistory] = useState([])
  const [appearanceDirty, setAppearanceDirty] = useState(false)
  const admin = user?.role === 'admin'
  const [editingEnabled, setEditing] = useState(false)
  const editing = admin && open && editingEnabled
  const [device, setDevice] = useState('desktop')
  const [saved, setSaved] = useState({ layout: { mobile: {}, desktop: {} }, revision: 0 })
  const [draft, setDraft] = useState(null)
  const [selected, setPrimary] = useState(null)
  const [selection, setSelection] = useState([])
  const selectionRef=useRef([]);selectionRef.current=selection
  const setSelected = node => {setPrimary(node);setSelection(node?.dataset.layoutKey?[node.dataset.layoutKey]:[])}
  const [snapEnabled,setSnapEnabled]=useState(true)
  const [centerLines,setCenterLines]=useState(true)
  const [addKind,setAddKind]=useState('frame')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [alignReference, setAlignReference] = useState('selection')
  const [nudgeStep, setNudgeStep] = useState(1)
  const [freeMove, setFreeMove] = useState(true)
  const [guides, setGuides] = useState(null)
  const dragging = useRef(null)
  const preview = useMemo(() => editing && draft ? draft : saved.layout._enabled === false ? {} : saved.layout[device] || {}, [editing, draft, saved.layout, device])
  const dragPreview = useRef(preview)
  dragPreview.current = preview
  const selectedKey = selected?.dataset.layoutKey
  useEffect(() => {
    if (!selectedKey) return
    const frame = window.requestAnimationFrame(() => {
      const current = document.querySelector(`[data-layout-key="${selectedKey}"],[data-ui-key="${selectedKey}"]`)
      if (current) { current.dataset.layoutKey = selectedKey; setPrimary(current) }
    })
    return () => window.cancelAnimationFrame(frame)
  }, [selectedKey, preview])
  const configuration = preview[selectedKey] || preview[selected?.dataset.layoutLegacy] || {}
  const refreshMetrics = () => { const next = readLayoutMetrics(selected); setMetrics(current => JSON.stringify(current) === JSON.stringify(next) ? current : next) }
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { const next = readLayoutMetrics(selected); setMetrics(current => JSON.stringify(current) === JSON.stringify(next) ? current : next) })
    return () => window.cancelAnimationFrame(frame)
  }, [selected, preview])
  const resizeSelection = (size, phase) => {
    const keys=selectionRef.current.length?selectionRef.current:[selectedKey]
    if(phase==='start'){resizeOriginal.current=Object.fromEntries(keys.map(key=>[key,preview[key]]));return}
    if(phase==='end'){resizeOriginal.current=null;return}
    if(phase==='cancel'){
      const original=resizeOriginal.current;resizeOriginal.current=null
      if(original)setDraft(current=>{const next={...current};Object.entries(original).forEach(([key,item])=>{if(item)next[key]=item;else delete next[key]});return next})
      return
    }
    setDraft(current=>{const next={...current};keys.forEach(key=>{next[key]={...next[key],...size}});return next})
  }
  const definition = registry[selectedKey?.split('--')[0]]
  useEffect(() => { publishCustomization(preview, editing) }, [preview, editing])
  useEffect(() => { if (initialTab) setTab(['rooms','columns','history'].includes(initialTab) ? initialTab : 'object') }, [initialTab])
  useEffect(() => {
    if (!admin || !open || tab !== 'history') return
    veraApi.uiLayoutHistory().then(result => setHistory(result.items || [])).catch(error => setMessage(error.message))
  }, [admin, open, tab, saved.revision])
  useEffect(() => {
    if (!editing && !appearanceDirty) return undefined
    const warn = event => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [editing, appearanceDirty])
  const chooseTab = next => {
    if (['rooms','columns','history'].includes(next) && editing) {
      if (JSON.stringify(draft) !== JSON.stringify(saved.layout[device] || {}) && !window.confirm('Hủy bản xem trước chưa lưu để chuyển mục?')) return
      setEditing(false); setDraft(null); setSelected(null)
    }
    if (appearanceDirty && !['rooms','columns'].includes(next) && !window.confirm('Hủy thay đổi giao diện Live Tour chưa lưu?')) return
    setGuideTool(''); setTab(next)
  }
  const addElement = kind => {
    const key = `l-custom-${crypto.randomUUID()}`
    const anchor = configuration.custom_kind ? configuration.custom_anchor : selectedKey
    const destination=isCustomContainer(configuration)?selectedKey:undefined
    setDraft(current => ({ ...current, [key]: {custom_kind:kind,custom_text:kind==='table'?'Tên | Ngày | Loại\nMẫu A | 23-09-2026 | Lựa chọn 1':kind==='text'?'Nội dung mới':customKinds[kind],...(kind==='dropdown'?{custom_options:'Lựa chọn 1\nLựa chọn 2'}:{}),custom_page:page,...(destination?{move_to:destination}:anchor ? {custom_anchor:anchor} : {}),order:Object.keys(current || {}).length} }))
    setNewKey(key);setGuideTool(['box','text'].includes(kind)?'Thêm '+kind:'Loại thành phần')
  }
  useEffect(() => {
    if (!newKey) return undefined
    let frame, attempts=0
    const select = () => { const node=document.querySelector(`[data-ui-key="${newKey}"]`); if(node){setSelected(node);setNewKey(null)}else if(++attempts<60)frame=window.requestAnimationFrame(select);else{setNewKey(null);setMessage('Chưa tìm được vị trí thêm. Hãy chọn một khung ngoài bảng rồi thử lại.')} }
    frame=window.requestAnimationFrame(select)
    return()=>window.cancelAnimationFrame(frame)
  },[newKey])
  const removeElement = () => {
    setGuideTool('Xóa / Ẩn')
    if(!window.confirm('Xóa các thành phần tự thêm đã chọn (kèm phần con), hoặc ẩn thành phần có sẵn? Dữ liệu nghiệp vụ được giữ nguyên.'))return
    setDraft(current=>removeLayoutItems(current,selection.length?selection:[selectedKey]));setSelected(null)
  }
  const groupSelection = grouped => {
    if(grouped && selectionNodes(selection).some(node=>node.closest('.nav-list'))){setMessage('Menu được sắp xếp riêng bằng kéo lên/xuống hoặc Trước/Sau.');return}
    const id=grouped?'g-'+crypto.randomUUID():undefined
    setDraft(current=>{const next={...current};selection.forEach(key=>{next[key]={...next[key],group_id:id}});return next})
    setGuideTool(grouped?'Group':'Ungroup')
  }
  const alignMany = mode => {
    const nodes=selectionNodes(selection)
    const pageBounds=alignReference==='page' ? (selected?.closest('.page-wrap') || document.querySelector('.page-wrap') || document.documentElement).getBoundingClientRect() : undefined
    setDraft(current=>mode.startsWith('distribute-') ? distributeSelection(current || preview,nodes,mode.slice(11),pageBounds) : alignSelection(current || preview,nodes,mode,pageBounds))
  }
  const restore = async revision => {
    if (!window.confirm('Khôi phục bố cục thiết bị này từ phiên bản đã chọn?')) return
    setBusy(true)
    try { const result = await veraApi.restoreUiLayout(revision, { device, revision: saved.revision, items: {} }); setSaved(result); setMessage('Đã khôi phục bố cục.') }
    catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }

  useEffect(() => {
    let active = true
    const refresh = async () => {
      if (editing || document.hidden) return
      try { const result = await veraApi.uiLayout(); if (active) { setSaved(result); setLoaded(true) } }
      catch (error) { if (active && admin) setMessage(error.message) }
    }
    void refresh()
    const interval = window.setInterval(refresh, 60000)
    window.addEventListener('focus', refresh)
    return () => { active = false; window.clearInterval(interval); window.removeEventListener('focus', refresh) }
  }, [editing, admin])
  useEffect(() => { setSelected(null); setInlineTarget(null) }, [page, editing, device])
  useEffect(() => {
    const root = document.querySelector('.app-shell')
    if (!root) return undefined
    const identify = () => {
      for (const element of root.querySelectorAll('[data-vera-node],[data-ui-key]')) {
        if (element.closest('.layout-designer, .layout-resize-overlay, .break-alert-stack')) continue
        if (element.closest('table') && !element.matches('table,th')) continue
        let key = layoutKey(element, page)
        if (element.matches('th') && element.dataset.veraItem) {
          let hash=2166136261
          for (const char of element.dataset.veraItem) hash=Math.imul(hash ^ char.charCodeAt(0),16777619)
          key += `--${(hash>>>0).toString(36)}`
        }
        if (!key) continue
        element.dataset.layoutKey = key
        element.dataset.layoutLegacy = legacyLayoutKey(element, page)
        element.dataset.layoutEditable = editing && !element.matches('.app-shell,.main-area,.sidebar') && !registry[key.split('--')[0]]?.locked && (element.matches(layoutCandidates) || key.startsWith('l-custom-')) && root.querySelectorAll(`[data-ui-key="${key}"]`).length <= 1 ? 'true' : 'false'
        const parent = element.parentElement
        if (parent?.dataset.veraNode || parent?.dataset.uiKey) {
          parent.dataset.layoutKey = layoutKey(parent, page)
          // Keep native grid/flex responsive layouts; only ordinary block groups need flex order.
          if (!parent.dataset.layoutBlock) parent.dataset.layoutBlock = getComputedStyle(parent).display === 'block' ? 'true' : 'false'
        }
      }
    }
    identify()
    let frame = null
    const observer = new MutationObserver(() => {
      if (frame !== null) return
      frame = window.requestAnimationFrame(() => { frame = null; identify() })
    })
    observer.observe(root, { childList: true, subtree: true })
    return () => { observer.disconnect(); if (frame !== null) window.cancelAnimationFrame(frame) }
  }, [page, editing])
  const relocate = (source, destination, before = null) => {
    if (!source?.dataset.uiOrigin || !destination || !canRelocate(source, destination)) { setMessage('Chọn thành phần trong nhóm nút và khung đích cùng biểu mẫu.'); return }
    const key = source.dataset.layoutKey
    const destinationKey = destination.dataset.uiDropzone
    if (!key || !destinationKey || registry[destinationKey]?.locked || (!registry[destinationKey]?.group && !isCustomContainer(preview[destinationKey]))) return
    const moving=selectionRef.current.includes(key)?selectionNodes(selectionRef.current):[source]
    if(moving.some(node=>!node.dataset.uiOrigin || !canRelocate(node,destination))){setMessage('Các thành phần cần cùng biểu mẫu và hỗ trợ chuyển khung.');return}
    const peers = [...destination.querySelectorAll('[data-ui-origin]')].filter(node => !moving.includes(node) && node.closest('[data-ui-dropzone]') === destination)
      .sort((a,b)=>(preview[a.dataset.layoutKey]?.order ?? peersIndex(a))-(preview[b.dataset.layoutKey]?.order ?? peersIndex(b)))
    function peersIndex(node) { return [...destination.querySelectorAll('[data-ui-origin]')].indexOf(node) }
    const index = before ? peers.indexOf(before) : peers.length
    peers.splice(index < 0 ? peers.length : index,0,...moving)
    setDraft(current => {const next={...current};peers.forEach((node,order)=>{const k=node.dataset.layoutKey || node.dataset.uiKey;if(k)next[k]={...next[k],parent:destinationKey,order,...(moving.includes(node)?{move_to:destinationKey,offset_x:0,offset_y:0}:{})}});return next})
    setPrimary(source); setMessage('Đã chuyển khung trong bản xem trước. Bấm Lưu cho tất cả để áp dụng.')
  }
  const move = (source, target) => {
    if(source?.closest('.nav-list') && target?.closest('.nav-list')===source.closest('.nav-list')){
      const nodes=[...source.closest('.nav-list').querySelectorAll('a[data-ui-key^="u-menu-"]')].sort((a,b)=>(preview[a.dataset.uiKey]?.order ?? [...source.parentElement.children].indexOf(a))-(preview[b.dataset.uiKey]?.order ?? [...source.parentElement.children].indexOf(b)))
      const from=nodes.indexOf(source),to=nodes.indexOf(target)
      if(from<0 || to<0)return
      nodes.splice(to,0,...nodes.splice(from,1))
      setDraft(current=>{const next={...current};nodes.forEach((node,order)=>{next[node.dataset.uiKey]={...next[node.dataset.uiKey],order,offset_x:0,offset_y:0}});return next});return
    }
    if (!source || !target || source === target) return
    if (source.parentElement !== target.parentElement) { relocate(source, target.closest('[data-ui-dropzone]')); return }
    const parent = source.parentElement
    if (!parent.dataset.layoutKey || parent.matches('table,thead,tbody,tr')) { setMessage('Nhóm này giữ bố cục cố định để không tràn màn hình.'); return }
    const children = [...parent.children].filter(item => item.dataset.layoutKey && !registry[item.dataset.layoutKey]?.locked)
      .sort((a,b) => Number(preview[a.dataset.layoutKey]?.order ?? [...parent.children].indexOf(a)) - Number(preview[b.dataset.layoutKey]?.order ?? [...parent.children].indexOf(b)))
    const from = children.indexOf(source), to = children.indexOf(target)
    if (from < 0 || to < 0) return
    children.splice(from, 1); children.splice(to, 0, source)
    const slots = [...parent.children].map((item,index) => !registry[item.dataset.layoutKey]?.locked ? index : null).filter(index => index !== null)
    setDraft(current => {
      const next = { ...current }
      children.forEach((item, index) => { next[item.dataset.layoutKey] = { ...next[item.dataset.layoutKey], order: slots[index] ?? index, parent: parent.dataset.layoutKey } })
      return next
    })
    setSelected(source); setMessage('Đã đổi vị trí trong bản xem trước. Bấm Lưu để áp dụng cho mọi người.')
  }
  const moveRef = useRef(move); moveRef.current = move
  const relocateRef = useRef(relocate); relocateRef.current = relocate
  useEffect(() => {
    if (!editing) return undefined
    const candidate = target => target?.closest?.('.nav-list > a[data-layout-editable="true"]') || target?.closest?.('[data-ui-key^="l-custom-"][data-layout-editable="true"]') || target?.closest?.('[data-layout-editable="true"]')
    const down = event => {
      if (event.button !== 0 || event.target.closest('.layout-designer,.layout-resize-overlay')) return
      const element = candidate(event.target)
      if (!element) return
      event.preventDefault(); event.stopPropagation()
      const clicked=element.dataset.layoutKey
      if(event.shiftKey || event.ctrlKey || event.metaKey){
        const old=selectionRef.current
        const keys=old.includes(clicked)?old.filter(key=>key!==clicked):[...old,clicked]
        const independent=selectionNodes(keys).map(node=>node.dataset.layoutKey)
        setSelection(independent);setPrimary(independent.includes(clicked)?element:selectionNodes(independent)[0] || null);return
      }
      const group=dragPreview.current[clicked]?.group_id
      const keys=group?Object.keys(dragPreview.current).filter(key=>dragPreview.current[key]?.group_id===group):selectionRef.current.includes(clicked)?selectionRef.current:[clicked]
      const nodes=selectionNodes(keys)
      const members=nodes.map(node=>({key:node.dataset.layoutKey,original:dragPreview.current[node.dataset.layoutKey]}))
      setInlineTarget(null);setPrimary(element);setSelection(nodes.map(node=>node.dataset.layoutKey))
      element.dataset.layoutDragging = 'true'
      const key = element.dataset.layoutKey
      const original = dragPreview.current[key]
      const rect = boundingSelection(nodes) || element.getBoundingClientRect()
      const targets = [...document.querySelectorAll('.app-shell [data-layout-editable="true"]')].filter(node=>!node.closest('.layout-designer') && !nodes.some(member=>member===node || member.contains(node) || node.contains(member))).map(node=>node.getBoundingClientRect()).filter(r=>r.width && r.height && r.bottom>=0 && r.top<=window.innerHeight)
      targets.push(element.parentElement.getBoundingClientRect(),{left:0,right:window.innerWidth,top:0,bottom:window.innerHeight,width:window.innerWidth,height:window.innerHeight})
      dragging.current = { element, key, original, rect, targets, members, menu:Boolean(element.closest('.nav-list')),  pointer: event.pointerId, x: event.clientX, y: event.clientY, scrollX: window.scrollX, scrollY: window.scrollY }
    }
    const dropAt = (event, start) => {
      const hidden=selectionNodes(start.members.map(member=>member.key)).map(node=>[node,node.style.pointerEvents])
      hidden.forEach(([node])=>{node.style.pointerEvents='none'})
      let hit
      try {hit=document.elementFromPoint(event.clientX,event.clientY)} finally {hidden.forEach(([node,value])=>{node.style.pointerEvents=value})}
      if (!hit || hit.closest('.layout-designer')) return null
      const destination=hit.closest('[data-ui-dropzone]')
      if (!start.element.dataset.uiOrigin || !destination || !canRelocate(start.element,destination) || (!registry[destination.dataset.uiDropzone]?.group && !isCustomContainer(dragPreview.current[destination.dataset.uiDropzone])) || registry[destination.dataset.uiDropzone]?.locked) return null
      const peer=hit.closest('[data-ui-origin]')
      const current=start.element.closest('[data-ui-dropzone]')
      // In free mode, same-row gestures remain free positioning; different rows reflow.
      if(freeMove && destination===current && (!peer || Math.abs(peer.getBoundingClientRect().top-start.rect.top)<8))return null
      const peers=[...destination.querySelectorAll('[data-ui-origin]')].filter(node=>node!==start.element && node.closest('[data-ui-dropzone]')===destination)
      const vertical=getComputedStyle(destination).flexDirection==='column'
      const r=peer?.getBoundingClientRect()
      const after=r && (vertical ? event.clientY>(r.top+r.bottom)/2 : event.clientX>(r.left+r.right)/2)
      const ordered=peers.sort((a,b)=>(dragPreview.current[a.dataset.layoutKey]?.order ?? peers.indexOf(a))-(dragPreview.current[b.dataset.layoutKey]?.order ?? peers.indexOf(b)))
      const before=peer ? (after ? ordered[ordered.indexOf(peer)+1] : peer) : null
      const rect=destination.getBoundingClientRect()
      return {destination,before,line:r ? (vertical?{x:r.left,y:after?r.bottom:r.top,width:r.width,height:2}:{x:after?r.right:r.left,y:r.top,width:2,height:r.height}):{x:rect.left,y:rect.top,width:rect.width,height:2}}
    }
    const motion = event => {
      const start = dragging.current
      if (!start || start.pointer !== event.pointerId) return
      const dx = event.clientX - start.x, dy = event.clientY - start.y
      if (!start.moved && Math.hypot(dx,dy) <= 4) return
      start.moved = true
      event.preventDefault()
      start.drop=dropAt(event,start)
      if (!freeMove || start.menu) {setGuides({drop:start.drop?.line});return}
      const result = freeMovePosition(start, dx, dy, window.innerWidth, snapEnabled && !event.altKey, window.scrollX, window.scrollY)
      setDraft(current=>translateSelection(current,start.members,result.x-(start.original?.offset_x || 0),result.y-(start.original?.offset_y || 0)))
      setGuides({...result.guides,drop:start.drop?.line})
    }
    const cancel = () => {
      const start = dragging.current; dragging.current = null; setGuides(null)
      if (!start) return
      delete start.element.dataset.layoutDragging
      if (start.moved) setDraft(current => {const next={...current};start.members.forEach(({key,original})=>{if(original)next[key]=original;else delete next[key]});return next})
    }
    const escape = event => { if(event.key === 'Escape') cancel() }
    const up = event => {
      const start = dragging.current
      if (!start || start.pointer !== event.pointerId) return
      if (start.moved || Math.hypot(event.clientX-start.x,event.clientY-start.y)>12) {
        const drop=dropAt(event,start)
        if(drop){dragging.current=null;delete start.element.dataset.layoutDragging;setGuides(null);relocateRef.current(start.element,drop.destination,drop.before);return}
      }
      if (freeMove && !start.menu) { motion(event); dragging.current=null; delete start.element.dataset.layoutDragging; setGuides(null); return }
      dragging.current = null
      if (!start) return
      delete start.element.dataset.layoutDragging
      const hit = document.elementFromPoint(event.clientX, event.clientY)
      const target = candidate(hit) || hit?.closest('[data-ui-dropzone]')
      if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > 12) moveRef.current(start.element, target)
    }
    const rename = event => {
      if (event.target.closest('.layout-designer,.layout-resize-overlay')) return
      const element = candidate(event.target)
      const entry = registry[element?.dataset.layoutKey?.split('--')[0]]
      if (!element || !(entry?.label || entry?.dynamic_label)) return
      event.preventDefault(); event.stopPropagation()
      setSelected(element); setInlineTarget(element)
    }
    const block = event => { if (!event.target.closest('.layout-designer,.layout-resize-overlay')) { event.preventDefault(); event.stopPropagation() } }
    document.addEventListener('pointermove', motion, true)
    document.addEventListener('pointercancel', cancel, true)
    document.addEventListener('keydown', escape, true)
    window.addEventListener('blur', cancel)
    document.addEventListener('dblclick', rename, true)
    document.addEventListener('pointerdown', down, true)
    document.addEventListener('pointerup', up, true)
    document.addEventListener('click', block, true)
    document.addEventListener('submit', block, true)
    return () => { cancel(); document.removeEventListener('pointermove', motion, true); document.removeEventListener('pointercancel', cancel, true); document.removeEventListener('keydown', escape, true); window.removeEventListener('blur', cancel); document.removeEventListener('dblclick', rename, true); document.removeEventListener('pointerdown', down, true); document.removeEventListener('pointerup', up, true); document.removeEventListener('click', block, true); document.removeEventListener('submit', block, true) }
  }, [editing, freeMove, snapEnabled])
  const patch = (key, value) => setDraft(current => {
    const next = { ...current, [selectedKey]: { ...configuration, [key]: value === '' ? undefined : ['label','mode','text_align','content_align','justify_content','align_items'].includes(key) ? value : Number(value) } }
    if(['width','height','text_align','content_align','font_size'].includes(key))selection.forEach(id=>{next[id]={...next[id],[key]:next[selectedKey][key]}})
    if (selected?.dataset.layoutLegacy !== selectedKey) delete next[selected?.dataset.layoutLegacy]
    return next
  })
  const nudge = (dx, dy) => {
    const nodes = selectionNodes(selection.length ? selection : [selectedKey])
    setDraft(current => {
      const items = current || preview
      return translateSelection(items, nodes.map(node => ({key:node.dataset.layoutKey, original:items[node.dataset.layoutKey] || {}})), dx*nudgeStep, dy*nudgeStep)
    })
  }
  const patchTypography = values => setDraft(current => {
    const next = {...(current || preview)}
    for (const key of selection.length ? selection : [selectedKey]) {
      next[key] = {...next[key], appearance:{...next[key]?.appearance,...values}}
      if ('font_size' in values) next[key].font_size = values.font_size
    }
    return next
  })
  const step = (direction) => {
    if (!selected?.parentElement) return
    const siblings = [...selected.parentElement.children].filter(item => item.dataset.layoutKey)
      .sort((a,b) => Number(preview[a.dataset.layoutKey]?.order ?? [...selected.parentElement.children].indexOf(a)) - Number(preview[b.dataset.layoutKey]?.order ?? [...selected.parentElement.children].indexOf(b)))
    move(selected, siblings[siblings.indexOf(selected) + direction])
  }
  const selectParent = () => {
    let parent = selected?.parentElement
    while (parent && !parent.dataset.veraNode && !parent.dataset.uiKey && !parent.matches('.app-shell')) parent = parent.parentElement
    if (!parent || registry[parent.dataset.uiKey]?.locked || parent.matches('.app-shell,.sidebar,.main-area,thead,tbody,tr,td,th')) return
    parent.dataset.layoutKey = layoutKey(parent, page)
    parent.dataset.layoutEditable = 'true'
    if (parent.parentElement?.dataset.veraNode) {
      parent.parentElement.dataset.layoutKey = layoutKey(parent.parentElement, page)
      parent.parentElement.dataset.layoutBlock = getComputedStyle(parent.parentElement).display === 'block' ? 'true' : 'false'
    }
    setSelected(parent)
  }
  const descendants = selected ? [...selected.querySelectorAll('[data-layout-editable="true"]')]
    .filter(node => !node.closest('.layout-designer,.layout-resize-overlay')) : []
  const canEditText = Boolean(configuration.custom_kind || definition?.label || definition?.dynamic_label)
  const isContainer = Boolean(definition?.group || selected?.matches('header,section,main,nav,aside,footer,div,fieldset,form'))
  const beginEditing = () => {
    if (appearanceDirty && !window.confirm('Hủy thay đổi giao diện Live Tour chưa lưu để tùy chỉnh thành phần?')) return
    setTab('object'); setGuideTool('Tùy chỉnh')
    if (!editing) { setDraft({ ...saved.layout[device] }); setEditing(true) }
    setMessage('Chọn bất kỳ thành phần trên trang hoặc chọn khung cha, rồi chỉnh thuộc tính ngay trong bảng công cụ.')
  }
  const changeDevice = next => {
    if (next === device) return
    if ((appearanceDirty || editing && JSON.stringify(draft)!==JSON.stringify(saved.layout[device] || {})) && !window.confirm('Chuyển chế độ và hủy bản xem trước chưa lưu?')) return
    setDevice(next);setEditing(false);setDraft(null);setSelected(null);setMessage('Đã chuyển chế độ.')
  }
  const toggleLayout = async () => {
    if (!window.confirm('Thay đổi áp dụng bố cục tùy chỉnh cho tất cả người dùng? Cấu hình đã lưu vẫn được giữ.')) return
    setBusy(true)
    try { setSaved(await veraApi.saveUiLayout({ device, revision: saved.revision, items: saved.layout[device] || {}, enabled: saved.layout._enabled === false })); setMessage('Đã cập nhật chế độ áp dụng bố cục.') }
    catch(error) { setMessage(error.message) } finally { setBusy(false) }
  }
  const close = () => {
    if (busy) return
    if ((appearanceDirty || editing && JSON.stringify(draft) !== JSON.stringify(saved.layout[device] || {})) && !window.confirm('Đóng và hủy các thay đổi bố cục chưa lưu?')) return
    setEditing(false); setDraft(null); setSelected(null); setMessage(''); dragging.current = null
    onClose?.()
  }
  const save = async () => {
    setBusy(true); setMessage('')
    try {
      const result = await veraApi.saveUiLayout({ device, revision: saved.revision, items: draft || {} })
      setSaved(result); setEditing(false); setDraft(null); setSelected(null)
      setMessage('Đã lưu và áp dụng cho tất cả người dùng. Thiết bị đang mở sẽ cập nhật trong vòng một phút.')
    } catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }
  return <>
    <LayoutCustomElements items={preview} page={page} editing={editing}/>
    <style>{layoutCss(preview)}{editing ? selection.map(key=>`[data-layout-key="${key}"]{outline:3px solid #c49524!important;outline-offset:2px}`).join('') : ''}</style>
    {admin && open && <aside className={`layout-designer ${['rooms','columns','history'].includes(tab) ? 'layout-designer-wide' : ''}`} style={{ ...panelFrame.style, ...toolScale.style, ...(panelHidden ? {width:'auto',height:'auto'} : {}) }} aria-label="Giao diện Admin" onFocusCapture={event=>{
        if(event.target.closest('.layout-tool-guide') || event.target.getAttribute('role') === 'tab')return
        const label=event.target.closest('label')?.childNodes[0]?.textContent?.trim()
        if(label)setGuideTool(/Rộng|Cao tối thiểu/.test(label)?'Kích thước':label)
        else if(event.target.tagName==='BUTTON')setGuideTool(event.target.getAttribute('aria-label') || event.target.textContent?.trim())
      }}>
      {panelHidden && <button type="button" onClick={()=>setPanelHidden(false)} aria-label="Show bảng công cụ">Show</button>}
      <div className="layout-panel-header" hidden={panelHidden}>
      <div className="layout-panel-frame-toolbar" role="group" aria-label="Điều khiển bảng công cụ">
        <button type="button" disabled={busy || !loaded} aria-pressed={editing} onClick={beginEditing}>Tùy chỉnh</button>
        <button type="button" aria-pressed={tab === 'object'} onClick={()=>chooseTab('object')}>Thành phần</button>
        <button type="button" disabled={busy || !loaded || editing || appearanceDirty} aria-pressed={saved.layout._enabled === false} aria-label={saved.layout._enabled === false ? 'Tiếp tục' : 'Tạm dùng bố cục mặc định'} title={editing ? 'Lưu hoặc hủy bản xem trước trước khi dùng bố cục mặc định' : 'Tạm dùng bố cục mặc định hoặc bật lại bố cục đã lưu cho tất cả người dùng'} onClick={toggleLayout}>{saved.layout._enabled === false ? 'Tiếp tục' : 'Mặc định'}</button>
        <button type="button" onClick={panelFrame.reset} title="Đặt lại vị trí và kích thước bảng công cụ">Vị trí</button>
        <button type="button" className="layout-panel-drag" {...panelFrame.move} aria-label="Di chuyển bảng công cụ">Di chuyển</button>
        <button type="button" onClick={()=>setPanelHidden(true)}>Hide</button>
      </div>
      <div className="layout-fixed-actions"><button type="button" aria-pressed={tab === 'rooms'} onClick={()=>chooseTab('rooms')}>Phòng Live Tour</button><button type="button" aria-pressed={tab === 'columns'} onClick={()=>chooseTab('columns')}>Cấu hình cột</button><button type="button" disabled={busy || !editing} onClick={() => { if (window.confirm('Khôi phục toàn bộ bố cục thiết bị này? Bấm Lưu để áp dụng.')) setDraft({}) }}>Mặc định</button><button type="button" disabled={busy || !editing} onClick={() => { setEditing(false); setDraft(null); setSelected(null) }}>Hủy</button><button className="layout-save" title="Lưu cho tất cả người dùng" type="button" disabled={busy || !editing} onClick={save}>{busy ? 'Đang lưu…' : 'Lưu'}</button></div>
      <label className="layout-tool-scale">Cỡ nút công cụ · {toolScale.value}%<input type="range" aria-label="Cỡ nút công cụ" min="70" max="110" step="5" value={toolScale.value} onChange={event => toolScale.setValue(Number(event.target.value))}/></label>
      <div className="layout-device-toolbar">        {['desktop','mobile'].map(mode=><label key={mode}><input type="checkbox" aria-label={mode === 'desktop' ? 'Desktop' : 'Mobile'} checked={device === mode} disabled={busy} onChange={()=>changeDevice(mode)}/>{mode === 'desktop' ? 'Desktop' : 'Mobile'}</label>)}</div>
      <button type="button" disabled={busy} onClick={close} className="layout-close" aria-label="Đóng Giao diện">Đóng ✕</button>
      </div>
      <div className="layout-panel-content" hidden={panelHidden}>
      {tab === 'columns' && <><UICustomizationColumns page={page} items={preview} onChange={(key,width) => { setEditing(true); setDraft(current => ({ ...(current || saved.layout[device]), [key]: { ...(current || saved.layout[device])?.[key], width } })) }}/>{editing && <div className="layout-designer-actions"><button disabled={busy} onClick={save}>Lưu độ rộng cột</button><button disabled={busy} onClick={() => {setEditing(false);setDraft(null)}}>Hủy</button></div>}</>}
      {['rooms','columns'].includes(tab) && <AppearanceSettingsPage user={user} section={tab} onDirtyChange={setAppearanceDirty} />}
      {tab === 'history' && <div><p>Khôi phục chỉ áp dụng cho bố cục {device === 'mobile' ? 'Mobile' : 'Desktop'}. Cấu hình phòng và cột Live Tour được quản lý riêng trong hai mục tương ứng.</p>{history.map(item => <div className="layout-history-row" key={item.revision}><span>#{item.revision} · {item.actor} · {formatVeraDateTime(item.created_at)} · {item.device}</span><button disabled={busy} onClick={() => restore(item.revision)}>Khôi phục</button></div>)}{!history.length && <p>Chưa có lịch sử bố cục.</p>}</div>}
      {tab === 'object' && <>
      {!editing ? <>{message && <small role="status">{message}</small>}</> : <>
        <label className="layout-free-mode"><input type="checkbox" checked={snapEnabled} onChange={e=>setSnapEnabled(e.target.checked)}/>Bắt dính cạnh và tâm</label>
        <label className="layout-free-mode"><input type="checkbox" checked={centerLines} onChange={e=>setCenterLines(e.target.checked)}/>Đường tâm ngang/dọc</label>
        <label className="layout-free-mode"><input type="checkbox" aria-label="Kéo tự do" checked={freeMove} onChange={event=>setFreeMove(event.target.checked)}/>Kéo tự do</label>
        <small>Kéo để đặt vị trí; đường ngang/dọc giúp căn cạnh và tâm. Giữ Alt để bỏ bắt dính; Esc hủy lượt kéo. Thả vào dòng khác theo vạch xanh để chèn và tự dàn lại. Bỏ chọn Kéo tự do nếu chỉ muốn sắp xếp.</small>
        <small>Shift/Ctrl + bấm để chọn nhiều thành phần. Đã chọn: {selection.length}. Kéo menu để đổi thứ tự hoặc dùng Trước/Sau.</small>
        <fieldset className="layout-align-tools" aria-label="Căn chỉnh đối tượng"><legend>Căn chỉnh đối tượng</legend>
          <label>Căn theo<select aria-label="Căn theo" value={alignReference} onChange={e=>setAlignReference(e.target.value)}><option value="page">Khung trang (Align to Slide)</option><option value="selection">Đối tượng đang chọn (Align Selected Objects)</option></select></label>
          <div className="layout-multi-tools">{[['left','Căn trái'],['center-x','Căn giữa ngang'],['right','Căn phải'],['top','Căn trên'],['center-y','Căn giữa dọc'],['bottom','Căn dưới'],['distribute-horizontal','Giãn đều ngang'],['distribute-vertical','Giãn đều dọc']].map(([mode,label])=><button type="button" key={mode} disabled={selection.length < (mode.startsWith('distribute-') ? (alignReference==='page'?2:3) : (alignReference==='page'?1:2))} onClick={()=>alignMany(mode)}>{label}</button>)}</div>
        </fieldset>
        {selection.length>1 && <div className="layout-multi-tools" aria-label="Chỉnh nhiều thành phần"><button type="button" onClick={()=>groupSelection(true)}>Group</button><button type="button" onClick={()=>groupSelection(false)}>Ungroup</button><small>Rộng/Cao và tay nắm resize áp dụng cho tất cả thành phần đã chọn.</small></div>}

        <strong>Bố cục {device === 'mobile' ? 'Mobile' : 'Desktop'}</strong>
        <label>Mục menu<select aria-label="Mục menu" value={selectedKey?.startsWith('u-menu-')?selectedKey:''} onChange={e=>{const node=document.querySelector(`.nav-list [data-ui-key="${e.target.value}"]`);if(node)setSelected(node)}}><option value="">Chọn menu để đổi vị trí</option>{[...document.querySelectorAll('.nav-list a[data-ui-key^="u-menu-"]')].map(node=><option key={node.dataset.uiKey} value={node.dataset.uiKey}>{node.textContent}</option>)}</select></label>
        <label>Loại thành phần<select aria-label="Loại thành phần" value={addKind} onChange={e=>setAddKind(e.target.value)}>{Object.entries(customKinds).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <button type="button" onClick={()=>addElement(addKind)}>Thêm {customKinds[addKind]}</button>
        <div className="layout-designer-actions layout-element-actions">
          <button type="button" onClick={()=>addElement('box')}>Thêm box</button>
          <button type="button" onClick={()=>addElement('text')}>Thêm text</button>
          <button type="button" disabled={!canEditText} onClick={()=>{setGuideTool('Sửa text');textEditor.current?.focus()}}>Sửa text</button>
          <button type="button" disabled={!selectedKey} onClick={removeElement}>{configuration.custom_kind ? 'Xóa '+(configuration.custom_kind==='box'?'box':configuration.custom_kind==='text'?'text':customKinds[configuration.custom_kind]) : 'Xóa khỏi giao diện'}</button>
        </div>
        {!selectedKey && <small>Bấm chọn thành phần, section, header hoặc text trên trang. Chọn khung cha để chỉnh khung bao ngoài.</small>}
        <div className="layout-designer-actions"><button type="button" disabled={!selectedKey} onClick={() => step(-1)}>← Trước</button><button type="button" disabled={!selectedKey} onClick={() => step(1)}>Sau →</button><button type="button" disabled={!selectedKey} onClick={selectParent}>Chọn khung cha</button></div>
        <fieldset className="layout-align-tools"><legend>Di chuyển thành phần</legend>
          <label>Bước di chuyển (px)<input type="number" min="1" step="1" value={nudgeStep} onChange={e=>setNudgeStep(Math.max(1,Math.round(Number(e.target.value)||1)))}/></label>
          <div className="layout-designer-actions">{[[0,-1,'↑ Lên'],[0,1,'↓ Xuống'],[-1,0,'← Trái'],[1,0,'Phải →']].map(([dx,dy,label])=><button type="button" key={label} disabled={!selectedKey} onClick={()=>nudge(dx,dy)}>{label}</button>)}</div>
        </fieldset>
        <LayoutToolGuide tab={tab} tool={guideTool}/>
        {Object.entries(preview).some(([,item])=>item.hidden) && <details><summary>Thành phần đã ẩn</summary>{Object.entries(preview).filter(([,item])=>item.hidden).map(([key])=><button type="button" key={key} onClick={()=>setDraft(current=>({...current,[key]:{...current[key],hidden:false}}))}>Hiện lại: {registry[key]?.label || key}</button>)}</details>}
        {selectedKey && <><label>Vị trí X (px)<input type="number" min="-2400" max="2400" value={configuration.offset_x ?? 0} onChange={event=>patch('offset_x',event.target.value)}/></label><label>Vị trí Y (px)<input type="number" min="-2400" max="2400" value={configuration.offset_y ?? 0} onChange={event=>patch('offset_y',event.target.value)}/></label><small>Thông số hiện tại: {metrics?.width ?? '—'} × {metrics?.height ?? '—'} px · {metrics?.rawFont || '—'}. Kéo góc phải dưới để đổi kích thước.</small><small>Đã chọn: {selected.getAttribute('aria-label') || selected.textContent?.trim().slice(0, 70) || selected.tagName}</small>{(definition?.label || definition?.dynamic_label) && <label>Tên hiển thị<input ref={textEditor} type="text" maxLength={100} value={configuration.label ?? definition.label ?? selected.textContent?.trim()} onChange={e => patch('label', e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() } if (e.key === 'Escape') patch('label', '') }} /></label>}
        {descendants.length > 0 && <label>Thành phần bên trong<select aria-label="Thành phần bên trong" value="" onChange={event=>{const node=descendants.find(item=>item.dataset.layoutKey===event.target.value);if(node){setSelected(node);setInlineTarget(null)}}}><option value="">Chọn thành phần con ({descendants.length})</option>{descendants.map((node,index)=><option key={`${node.dataset.layoutKey}-${index}`} value={node.dataset.layoutKey}>{node.tagName.toLowerCase()} · {node.getAttribute('aria-label') || node.textContent?.trim().slice(0,60) || node.getAttribute('placeholder') || node.tagName}</option>)}</select></label>}
        {['search','dropdown','date','filter'].includes(configuration.custom_kind) && <label>Bảng cần lọc<select aria-label="Bảng cần lọc" value={configuration.custom_target || ''} onChange={e=>setDraft(current=>({...current,[selectedKey]:{...current[selectedKey],custom_target:e.target.value || undefined}}))}><option value="">Chưa liên kết bảng</option>{Object.entries(preview).filter(([,item])=>item.custom_kind==='table' && item.custom_page===page).map(([key,item])=><option key={key} value={key}>{item.custom_text?.split('\n')[0] || key}</option>)}</select></label>}
        {configuration.custom_kind==='dropdown' && <label>Lựa chọn (mỗi dòng một mục)<textarea value={configuration.custom_options || ''} onChange={e=>setDraft(current=>({...current,[selectedKey]:{...current[selectedKey],custom_options:e.target.value}}))}/></label>}
        {configuration.custom_kind==='table' && <small>Dòng đầu là tiêu đề, các dòng sau là dữ liệu; tách cột bằng |. Bộ lọc tự thêm chỉ tác động bảng tự thêm được liên kết.</small>}
        {configuration.custom_kind && <label>Nội dung<textarea ref={textEditor} aria-label="Nội dung text" maxLength={2000} value={configuration.custom_text || ''} onChange={event=>setDraft(current=>({...current,[selectedKey]:{...current[selectedKey],custom_text:event.target.value}}))}/></label>}
        <>{definition?.group && <><label>Số dòng<select value={configuration.rows ?? 0} onChange={e => patch('rows', e.target.value)}><option value="0">Tự động theo màn hình</option>{[1,2,3,4].map(n => <option key={n} value={n}>{n} dòng</option>)}</select></label><label>Cách hiển thị<select value={configuration.mode || 'fit'} onChange={e => patch('mode', e.target.value)}><option value="fit">Vừa màn hình</option><option value="group">Gom nút phụ (nhóm chỉ có nút)</option></select></label></>}<label>Cỡ chữ thành phần<input type="number" step="any" value={configuration.appearance?.font_size ?? configuration.font_size ?? metrics?.appearance?.font_size ?? ''} onChange={e => patchTypography({font_size:e.target.value === '' ? undefined : Number(e.target.value)})}/></label></>
        <fieldset className="layout-align-tools"><legend>Font và kiểu chữ</legend>
          <label>Font chữ<select value={configuration.appearance?.font_family || metrics?.appearance?.font_family || 'system'} onChange={e=>patchTypography({font_family:e.target.value})}>{[['system','Hệ thống'],['segoe','Segoe UI'],['roboto','Roboto / Arial'],['serif','Georgia']].map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
          <div className="layout-designer-actions"><button type="button" aria-pressed={(configuration.appearance?.font_weight ?? metrics?.appearance?.font_weight ?? 400)>=700} onClick={()=>patchTypography({font_weight:(configuration.appearance?.font_weight ?? metrics?.appearance?.font_weight ?? 400)>=700?400:700})}><b>B</b> Đậm</button><button type="button" aria-pressed={(configuration.appearance?.font_style ?? metrics?.appearance?.font_style)==='italic'} onClick={()=>patchTypography({font_style:(configuration.appearance?.font_style ?? metrics?.appearance?.font_style)==='italic'?'normal':'italic'})}><i>I</i> Nghiêng</button></div>
        </fieldset>
        {selected?.dataset.uiOrigin && <label>Khung đích<select aria-label="Khung đích" value={configuration.move_to || selected.dataset.uiOrigin} onChange={event => relocate(selected, getLayoutTargets()[event.target.value]?.element)}>{Object.entries(getLayoutTargets()).filter(([key, target]) => (registry[key]?.group || isCustomContainer(preview[key])) && !registry[key]?.locked && canRelocate(selected, target.element)).map(([key,target]) => <option key={key} value={key}>{target.element.getAttribute('aria-label') || target.element.textContent?.trim().slice(0,60) || registry[key]?.file || key}</option>)}</select></label>}
        <details className="layout-inspector-section"><summary>Phong cách & hiệu ứng</summary><UIVisualStyleControls key={selectedKey} value={configuration.appearance} current={metrics?.appearance} onChange={appearance => setDraft(current => ({ ...current, [selectedKey]: { ...configuration, appearance } }))}/></details>
        <fieldset className="layout-align-tools"><legend>Căn chỉnh</legend>
        <label>Căn chữ<select value={configuration.text_align || ''} onChange={e => patch('text_align', e.target.value)}><option value="">Mặc định</option>{[['left','Trái'],['center','Giữa'],['right','Phải'],['justify','Đều hai bên']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Căn dọc nội dung<select value={configuration.content_align || ''} onChange={e => patch('content_align', e.target.value)}><option value="">Mặc định</option>{[['start','Trên'],['center','Giữa'],['end','Dưới']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {isContainer && <><small>Căn nhóm theo trục của bố cục Flex/Grid hiện tại.</small><label>Phân bố nhóm<select value={configuration.justify_content || ''} onChange={e => patch('justify_content', e.target.value)}><option value="">Mặc định</option>{[['start','Đầu'],['center','Giữa'],['end','Cuối'],['space-between','Giãn hai đầu'],['space-around','Giãn quanh'],['space-evenly','Giãn đều']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Căn thành phần<select value={configuration.align_items || ''} onChange={e => patch('align_items', e.target.value)}><option value="">Mặc định</option>{[['start','Đầu'],['center','Giữa'],['end','Cuối'],['stretch','Kéo giãn']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Khoảng cách (px)<input type="number" min="0" max="100" value={configuration.gap ?? ''} onChange={e => patch('gap', e.target.value)}/></label></>}
        </fieldset><label>Rộng (px)<input type="number" min="32" max="2400" value={configuration.width ?? metrics?.width ?? ''} placeholder="Tự động" onChange={e => patch('width', e.target.value)}/></label><label>Cao tối thiểu (px)<input type="number" min="24" max="1600" value={configuration.height ?? metrics?.height ?? ''} placeholder="Tự động" onChange={e => patch('height', e.target.value)}/></label><button type="button" onClick={() => setDraft(current => { const next = { ...current }; if(configuration.custom_kind){next[selectedKey]={custom_kind:configuration.custom_kind,custom_text:configuration.custom_text,custom_page:configuration.custom_page,custom_anchor:configuration.custom_anchor,custom_options:configuration.custom_options,custom_target:configuration.custom_target};return next} delete next[selectedKey]; delete next[selected?.dataset.layoutLegacy]; return next })}>Khôi phục thành phần</button></>}

        {message && <small role="status">{message}</small>}
      </>}
      </>}
      {!editing && ['rooms','columns','history'].includes(tab) && message && <small role="status">{message}</small>}
    {inlineTarget && editing && <InlineLabelEditor key={inlineTarget.dataset.layoutKey} target={inlineTarget} value={configuration.label ?? definition?.label ?? inlineTarget.textContent?.trim() ?? ''} onCommit={value => { patch('label', value.trim()); setInlineTarget(null) }} onCancel={() => setInlineTarget(null)} />}
      </div>
      {!panelHidden && <button type="button" className="layout-history-fixed" disabled={busy} onClick={()=>chooseTab('history')}>Lịch sử</button>}
      {!panelHidden && <button type="button" className="layout-panel-resize" {...panelFrame.resize} aria-label="Kéo đổi kích thước bảng công cụ">Resize</button>}
    </aside>}
    {editing && centerLines && createPortal(<div className="layout-center-guides" aria-hidden="true"><i className="layout-center-vertical"/><i className="layout-center-horizontal"/></div>,document.body)}
    {editing && guides && createPortal(<div className="layout-alignment-guides" aria-hidden="true"><>{Number.isFinite(guides.x) && <div className="layout-guide-vertical" style={{left:guides.x}}/>}{Number.isFinite(guides.y) && <div className="layout-guide-horizontal" style={{top:guides.y}}/>}{guides.drop && <div className="layout-drop-line" style={{left:guides.drop.x,top:guides.drop.y,width:guides.drop.width,height:guides.drop.height}}/>}</></div>, document.body)}
    {editing && selectedKey && <LayoutResizeOverlay selected={selected} onResize={resizeSelection} onMetrics={refreshMetrics}/>}
  </>
}

function InlineLabelEditor({ target, value, onCommit, onCancel }) {
  const input = useRef(null)
  const cancelled = useRef(false)
  const rect = target.getBoundingClientRect()
  useEffect(() => { input.current?.focus(); input.current?.select() }, [])
  return <input ref={input} className="layout-inline-label" aria-label="Sửa tên trực tiếp" maxLength={100} defaultValue={value}
    style={{ position: 'fixed', left: Math.max(8, Math.min(rect.left, window.innerWidth - Math.min(Math.max(rect.width, 180), window.innerWidth - 16) - 8)), top: Math.max(8, Math.min(rect.top, window.innerHeight - 60)), width: Math.min(Math.max(rect.width, 180), window.innerWidth - 16) }}
    onBlur={event => { if (!cancelled.current) onCommit(event.target.value) }}
    onKeyDown={event => {
      if (event.nativeEvent.isComposing) return
      if (event.key === 'Enter') { event.preventDefault(); event.currentTarget.blur() }
      if (event.key === 'Escape') { event.preventDefault(); cancelled.current = true; onCancel() }
    }} />
}
