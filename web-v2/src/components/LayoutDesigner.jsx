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
  const panelFrame = useLayoutPanelFrame()
  const [guideTool, setGuideTool] = useState('')
  const [newKey, setNewKey] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const resizeOriginal = useRef(null)
  const [inlineTarget, setInlineTarget] = useState(null)
  const [tab, setTab] = useState(initialTab || 'order')
  const [history, setHistory] = useState([])
  const [appearanceDirty, setAppearanceDirty] = useState(false)
  const admin = user?.role === 'admin'
  const [editingEnabled, setEditing] = useState(false)
  const editing = admin && open && editingEnabled
  const [device, setDevice] = useState('desktop')
  const [saved, setSaved] = useState({ layout: { mobile: {}, desktop: {} }, revision: 0 })
  const [draft, setDraft] = useState(null)
  const [selected, setSelected] = useState(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const dragging = useRef(null)
  const preview = useMemo(() => editing && draft ? draft : saved.layout._enabled === false ? {} : saved.layout[device] || {}, [editing, draft, saved.layout, device])
  const selectedKey = selected?.dataset.layoutKey
  useEffect(() => {
    if (!selectedKey) return
    const frame = window.requestAnimationFrame(() => {
      const current = document.querySelector(`[data-layout-key="${selectedKey}"],[data-ui-key="${selectedKey}"]`)
      if (current) { current.dataset.layoutKey = selectedKey; setSelected(current) }
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
    if (phase === 'start') { resizeOriginal.current = { ...configuration }; return }
    if (phase === 'end') { resizeOriginal.current = null; return }
    const previous = resizeOriginal.current
    if (phase === 'cancel') resizeOriginal.current = null
    if (phase === 'cancel' && !previous) return
    setDraft(current => ({ ...current, [selectedKey]: phase === 'cancel' ? previous : { ...current?.[selectedKey], ...size } }))
  }
  const definition = registry[selectedKey?.split('--')[0]]
  useEffect(() => { publishCustomization(preview, editing) }, [preview, editing])
  useEffect(() => { if (initialTab) setTab(initialTab) }, [initialTab])
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
    setDraft(current => ({ ...current, [key]: {custom_kind:kind,custom_text:kind === 'box' ? 'Box mới' : 'Nội dung mới',custom_page:page,...(anchor ? {custom_anchor:anchor} : {}),order:Object.keys(current || {}).length} }))
    setNewKey(key);setGuideTool(kind === 'box' ? 'Thêm box' : 'Thêm text')
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
    if (!window.confirm(configuration.custom_kind ? 'Xóa thành phần tự thêm trong bản xem trước?' : 'Ẩn thành phần này khỏi giao diện? Dữ liệu nghiệp vụ được giữ nguyên.')) return
    setDraft(current=>{const next={...current};if(configuration.custom_kind)delete next[selectedKey];else next[selectedKey]={...configuration,hidden:true};return next});setSelected(null)
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
  useEffect(() => { setSelected(null); setInlineTarget(null) }, [page, editing, tab, device])
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
        element.dataset.layoutEditable = editing && !registry[key.split('--')[0]]?.locked && (element.matches(layoutCandidates) || key.startsWith('l-custom-')) && (tab !== 'labels' || key.startsWith('l-custom-') || (registry[key.split('--')[0]]?.label || registry[key.split('--')[0]]?.dynamic_label)) && root.querySelectorAll(`[data-ui-key="${key}"]`).length <= 1 ? 'true' : 'false'
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
  }, [page, editing, tab])
  const relocate = (source, destination) => {
    if (!source?.dataset.uiOrigin || !destination || !canRelocate(source, destination)) { setMessage('Chọn thành phần trong nhóm nút và khung đích cùng biểu mẫu.'); return }
    const key = source.dataset.layoutKey
    const destinationKey = destination.dataset.uiDropzone
    if (!key || !destinationKey || registry[destinationKey]?.locked || !registry[destinationKey]?.group) return
    setDraft(current => ({ ...current, [key]: { ...current?.[key], move_to: destinationKey, parent: destinationKey, order: destination.children.length } }))
    setSelected(source); setMessage('Đã chuyển khung trong bản xem trước. Bấm Lưu cho tất cả để áp dụng.')
  }
  const move = (source, target) => {
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
  useEffect(() => {
    if (!editing) return undefined
    const candidate = target => target?.closest?.('[data-layout-editable="true"]')
    const down = event => {
      if (event.target.closest('.layout-designer,.layout-resize-overlay')) return
      const element = candidate(event.target)
      if (!element) return
      event.preventDefault(); event.stopPropagation()
      setSelected(element)
      element.dataset.layoutDragging = 'true'
      dragging.current = { element, x: event.clientX, y: event.clientY }
    }
    const up = event => {
      const start = dragging.current; dragging.current = null
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
      if (tab !== 'labels' || !element || !(entry?.label || entry?.dynamic_label)) return
      event.preventDefault(); event.stopPropagation()
      setSelected(element); setInlineTarget(element)
    }
    const block = event => { if (!event.target.closest('.layout-designer,.layout-resize-overlay')) { event.preventDefault(); event.stopPropagation() } }
    document.addEventListener('dblclick', rename, true)
    document.addEventListener('pointerdown', down, true)
    document.addEventListener('pointerup', up, true)
    document.addEventListener('click', block, true)
    document.addEventListener('submit', block, true)
    return () => { document.removeEventListener('dblclick', rename, true); document.removeEventListener('pointerdown', down, true); document.removeEventListener('pointerup', up, true); document.removeEventListener('click', block, true); document.removeEventListener('submit', block, true) }
  }, [editing, tab])
  const patch = (key, value) => setDraft(current => {
    const next = { ...current, [selectedKey]: { ...configuration, [key]: value === '' ? undefined : ['label','mode','text_align','content_align','justify_content','align_items'].includes(key) ? value : Number(value) } }
    if (selected?.dataset.layoutLegacy !== selectedKey) delete next[selected?.dataset.layoutLegacy]
    return next
  })
  const step = (direction) => {
    if (!selected?.parentElement) return
    const siblings = [...selected.parentElement.children].filter(item => item.dataset.layoutKey)
      .sort((a,b) => Number(preview[a.dataset.layoutKey]?.order ?? [...selected.parentElement.children].indexOf(a)) - Number(preview[b.dataset.layoutKey]?.order ?? [...selected.parentElement.children].indexOf(b)))
    move(selected, siblings[siblings.indexOf(selected) + direction])
  }
  const selectParent = () => {
    const parent = selected?.parentElement?.closest('[data-ui-dropzone]') || selected?.parentElement
    if ((!parent?.dataset.veraNode && !parent?.dataset.uiKey) || registry[parent?.dataset.uiKey]?.locked || parent.matches('.app-shell,.sidebar,.main-area,table,thead,tbody,tr,td,th')) return
    parent.dataset.layoutKey = layoutKey(parent, page)
    parent.dataset.layoutEditable = 'true'
    if (parent.parentElement?.dataset.veraNode) {
      parent.parentElement.dataset.layoutKey = layoutKey(parent.parentElement, page)
      parent.parentElement.dataset.layoutBlock = getComputedStyle(parent.parentElement).display === 'block' ? 'true' : 'false'
    }
    setSelected(parent)
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
    <style>{layoutCss(preview)}{editing && selectedKey ? `[data-layout-key="${selectedKey}"]{outline:3px solid #c49524!important;outline-offset:2px}` : ''}</style>
    {admin && open && <aside className={`layout-designer ${['rooms','columns','history'].includes(tab) ? 'layout-designer-wide' : ''}`} style={panelFrame.style} aria-label="Giao diện Admin" onFocusCapture={event=>{
        if(event.target.closest('.layout-tool-guide') || event.target.getAttribute('role') === 'tab')return
        const label=event.target.closest('label')?.childNodes[0]?.textContent?.trim()
        if(label)setGuideTool(/Rộng|Cao tối thiểu/.test(label)?'Kích thước':label)
        else if(event.target.tagName==='BUTTON')setGuideTool(event.target.getAttribute('aria-label') || event.target.textContent?.trim())
      }}>
      <button type="button" disabled={busy} onClick={close} className="layout-close" aria-label="Đóng Giao diện">Đóng ✕</button>
      <div className="layout-panel-frame-toolbar"><button type="button" className="layout-panel-drag" {...panelFrame.move} aria-label="Di chuyển bảng công cụ">⠿ Giao diện · kéo để di chuyển</button><button type="button" onClick={panelFrame.reset} title="Đặt lại vị trí và kích thước bảng công cụ">↺ Vị trí</button></div>
      <label>Chế độ giao diện<select aria-label="Chế độ giao diện" value={device} disabled={busy} onChange={event=>{
        if((appearanceDirty || editing && JSON.stringify(draft)!==JSON.stringify(saved.layout[device] || {})) && !window.confirm('Chuyển chế độ và hủy bản xem trước chưa lưu?'))return
        setDevice(event.target.value);setEditing(false);setDraft(null);setSelected(null);setMessage('Đã chuyển chế độ. Desktop là mặc định khi mở trình duyệt.')
      }}><option value="desktop">Desktop (mặc định)</option><option value="mobile">Mobile</option></select></label>
      <LayoutToolGuide tab={tab} tool={guideTool}/>
      {!editing && <button type="button" disabled={busy || !loaded} onClick={async () => {
        if (!window.confirm('Thay đổi áp dụng bố cục tùy chỉnh cho tất cả người dùng? Cấu hình đã lưu vẫn được giữ.')) return
        setBusy(true)
        try { setSaved(await veraApi.saveUiLayout({ device, revision: saved.revision, items: saved.layout[device] || {}, enabled: saved.layout._enabled === false })); setMessage('Đã cập nhật chế độ áp dụng bố cục.') }
        catch(error) { setMessage(error.message) } finally { setBusy(false) }
      }}>{saved.layout._enabled === false ? 'Bật lại bố cục đã lưu' : 'Tạm dùng bố cục mặc định'}</button>}
      <div className="layout-center-tabs" role="tablist" aria-label="Giao diện">{[['order','Sắp xếp'],['buttons','Nút bấm'],['labels','Tên hiển thị'],['style','Hiệu ứng'],['columns','Bảng & cột'],['rooms','Phòng Live Tour'],['history','Lịch sử'],['elements','Thêm / Xóa']].map(([key,label]) => <button type="button" role="tab" key={key} aria-selected={tab === key} onClick={() => chooseTab(key)}>{label}</button>)}</div>
      {tab === 'columns' && <><UICustomizationColumns page={page} items={preview} onChange={(key,width) => { setEditing(true); setDraft(current => ({ ...(current || saved.layout[device]), [key]: { ...(current || saved.layout[device])?.[key], width } })) }}/>{editing && <div className="layout-designer-actions"><button disabled={busy} onClick={save}>Lưu độ rộng cột</button><button disabled={busy} onClick={() => {setEditing(false);setDraft(null)}}>Hủy</button></div>}</>}
      {['rooms','columns'].includes(tab) && <AppearanceSettingsPage user={user} section={tab} onDirtyChange={setAppearanceDirty} />}
      {tab === 'history' && <div><p>Khôi phục chỉ áp dụng cho bố cục {device === 'mobile' ? 'Mobile' : 'Desktop'}. Cấu hình phòng và cột Live Tour được quản lý riêng trong hai mục tương ứng.</p>{history.map(item => <div className="layout-history-row" key={item.revision}><span>#{item.revision} · {item.actor} · {formatVeraDateTime(item.created_at)} · {item.device}</span><button disabled={busy} onClick={() => restore(item.revision)}>Khôi phục</button></div>)}{!history.length && <p>Chưa có lịch sử bố cục.</p>}</div>}
      {['order','buttons','labels','style','elements'].includes(tab) && <>
      {tab === 'labels' && <small>Nhấp đúp vào menu, tab hoặc nút trên trang để sửa tên tại chỗ. Trên điện thoại: chạm chọn rồi sửa ô Tên hiển thị. Bấm Lưu cho tất cả để áp dụng.</small>}
      <small>Mở trang cần chỉnh trước, sau đó chọn thành phần trên trang. Cấu hình lưu dùng chung; Mobile và Desktop độc lập.</small>
      {!editing ? <><button type="button" disabled={!loaded} onClick={() => { setDraft({ ...saved.layout[device] }); setEditing(true); setMessage('Chọn một thành phần. Kéo thả trong cùng nhóm để đổi vị trí.') }}>Chỉnh giao diện · {device === 'mobile' ? 'Mobile' : 'Desktop'}</button>{message && <small role="status">{message}</small>}</> : <>
        <strong>Bố cục {device === 'mobile' ? 'Mobile' : 'Desktop'}</strong><small>Chọn thành phần; kéo sang nhóm khác hoặc chọn Khung đích. Mobile và Desktop lưu riêng.</small>
        {tab === 'elements' && <><div className="layout-designer-actions"><button type="button" onClick={()=>addElement('box')}>Thêm box</button><button type="button" onClick={()=>addElement('text')}>Thêm text</button></div><small>Thêm sau thành phần đang chọn; nếu chưa chọn, thêm cuối trang. Box/text mới chỉ là phần trình bày.</small>{Object.entries(preview).filter(([,item])=>item.hidden).map(([key])=><button type="button" key={key} onClick={()=>setDraft(current=>({...current,[key]:{...current[key],hidden:false}}))}>Hiện lại: {registry[key]?.label || key}</button>)}</>}
        {selectedKey && <><small>Thông số hiện tại: {metrics?.width ?? '—'} × {metrics?.height ?? '—'} px · {metrics?.rawFont || '—'}. Kéo góc phải dưới để đổi kích thước.</small><small>Đã chọn: {selected.getAttribute('aria-label') || selected.textContent?.trim().slice(0, 70) || selected.tagName}</small><div className="layout-designer-actions"><button type="button" onClick={() => step(-1)}>← Trước</button><button type="button" onClick={() => step(1)}>Sau →</button><button type="button" onClick={selectParent}>Chọn khung cha</button></div>{tab === 'labels' && (definition?.label || definition?.dynamic_label) && <label>Tên hiển thị<input type="text" maxLength={100} value={configuration.label ?? definition.label ?? selected.textContent?.trim()} onChange={e => patch('label', e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() } if (e.key === 'Escape') patch('label', '') }} /></label>}
        {configuration.custom_kind && <label>Nội dung<textarea maxLength={2000} value={configuration.custom_text || ''} onChange={event=>setDraft(current=>({...current,[selectedKey]:{...current[selectedKey],custom_text:event.target.value}}))}/></label>}
        {tab === 'elements' && <button type="button" onClick={removeElement}>{configuration.custom_kind ? 'Xóa box/text' : 'Ẩn thành phần'}</button>}
        {tab === 'buttons' && <><small>Chọn khung cha của nhóm nút để chỉnh số dòng hoặc gom nhóm.</small>{definition?.group && <><label>Số dòng<select value={configuration.rows ?? 0} onChange={e => patch('rows', e.target.value)}><option value="0">Tự động theo màn hình</option>{[1,2,3,4].map(n => <option key={n} value={n}>{n} dòng</option>)}</select></label><label>Cách hiển thị<select value={configuration.mode || 'fit'} onChange={e => patch('mode', e.target.value)}><option value="fit">Vừa màn hình</option><option value="group">Gom nút phụ (nhóm chỉ có nút)</option></select></label></>}<label>Cỡ chữ nút<input type="number" min="12" max="24" value={configuration.font_size ?? metrics?.appearance?.font_size ?? ''} onChange={e => patch('font_size', e.target.value)}/></label></>}
        {selected?.dataset.uiOrigin && <label>Khung đích<select aria-label="Khung đích" value={configuration.move_to || selected.dataset.uiOrigin} onChange={event => relocate(selected, getLayoutTargets()[event.target.value]?.element)}>{Object.entries(getLayoutTargets()).filter(([key, target]) => registry[key]?.group && !registry[key]?.locked && canRelocate(selected, target.element)).map(([key,target]) => <option key={key} value={key}>{target.element.getAttribute('aria-label') || target.element.textContent?.trim().slice(0,60) || registry[key]?.file || key}</option>)}</select></label>}
        {tab === 'style' && <UIVisualStyleControls value={configuration.appearance} current={metrics?.appearance} onChange={appearance => setDraft(current => ({ ...current, [selectedKey]: { ...configuration, appearance } }))}/>}
        <fieldset className="layout-align-tools"><legend>Căn chỉnh</legend>
        <label>Căn chữ<select value={configuration.text_align || ''} onChange={e => patch('text_align', e.target.value)}><option value="">Mặc định</option>{[['left','Trái'],['center','Giữa'],['right','Phải'],['justify','Đều hai bên']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Căn dọc nội dung<select value={configuration.content_align || ''} onChange={e => patch('content_align', e.target.value)}><option value="">Mặc định</option>{[['start','Trên'],['center','Giữa'],['end','Dưới']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {definition?.group && <><small>Căn nhóm theo trục của bố cục Flex/Grid hiện tại.</small><label>Phân bố nhóm<select value={configuration.justify_content || ''} onChange={e => patch('justify_content', e.target.value)}><option value="">Mặc định</option>{[['start','Đầu'],['center','Giữa'],['end','Cuối'],['space-between','Giãn hai đầu'],['space-around','Giãn quanh'],['space-evenly','Giãn đều']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Căn thành phần<select value={configuration.align_items || ''} onChange={e => patch('align_items', e.target.value)}><option value="">Mặc định</option>{[['start','Đầu'],['center','Giữa'],['end','Cuối'],['stretch','Kéo giãn']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Khoảng cách (px)<input type="number" min="0" max="100" value={configuration.gap ?? ''} onChange={e => patch('gap', e.target.value)}/></label></>}
        </fieldset><label>Rộng (px)<input type="number" min="32" max="2400" value={configuration.width ?? metrics?.width ?? ''} placeholder="Tự động" onChange={e => patch('width', e.target.value)}/></label><label>Cao tối thiểu (px)<input type="number" min="24" max="1600" value={configuration.height ?? metrics?.height ?? ''} placeholder="Tự động" onChange={e => patch('height', e.target.value)}/></label><button type="button" onClick={() => setDraft(current => { const next = { ...current }; if(configuration.custom_kind){next[selectedKey]={custom_kind:configuration.custom_kind,custom_text:configuration.custom_text,custom_page:configuration.custom_page,custom_anchor:configuration.custom_anchor};return next} delete next[selectedKey]; delete next[selected?.dataset.layoutLegacy]; return next })}>Khôi phục thành phần</button></>}
        <div className="layout-designer-actions"><button className="layout-save" type="button" disabled={busy} onClick={save}>{busy ? 'Đang lưu…' : 'Lưu cho tất cả'}</button><button type="button" disabled={busy} onClick={() => { setEditing(false); setDraft(null); setSelected(null) }}>Hủy</button><button type="button" disabled={busy} onClick={() => { if (window.confirm('Khôi phục toàn bộ bố cục thiết bị này? Bấm Lưu để áp dụng.')) setDraft({}) }}>Mặc định</button></div>
        {message && <small role="status">{message}</small>}
      </>}
      </>}
      {!editing && ['rooms','columns','history'].includes(tab) && message && <small role="status">{message}</small>}
    {inlineTarget && editing && tab === 'labels' && <InlineLabelEditor key={inlineTarget.dataset.layoutKey} target={inlineTarget} value={configuration.label ?? definition?.label ?? inlineTarget.textContent?.trim() ?? ''} onCommit={value => { patch('label', value.trim()); setInlineTarget(null) }} onCancel={() => setInlineTarget(null)} />}
      <button type="button" className="layout-panel-resize" {...panelFrame.resize} aria-label="Kéo đổi kích thước bảng công cụ">↘ Kéo giãn bảng công cụ</button>
    </aside>}
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
