import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { layoutCandidates, layoutCss, layoutKey } from '../lib/sharedLayout'
import './LayoutDesigner.css'

export default function LayoutDesigner({ user, page, open = false, onClose }) {
  const admin = user?.role === 'admin'
  const [editingEnabled, setEditing] = useState(false)
  const editing = admin && open && editingEnabled
  const [device, setDevice] = useState(() => window.innerWidth <= 768 ? 'mobile' : 'desktop')
  const [saved, setSaved] = useState({ layout: { mobile: {}, desktop: {} }, revision: 0 })
  const [draft, setDraft] = useState(null)
  const [selected, setSelected] = useState(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const dragging = useRef(null)
  const deviceRef = useRef(device)
  const preview = editing && draft ? draft : saved.layout[device] || {}
  const selectedKey = selected?.dataset.layoutKey
  const configuration = preview[selectedKey] || {}

  useEffect(() => {
    const resize = () => {
      const next = window.innerWidth <= 768 ? 'mobile' : 'desktop'
      if (next === deviceRef.current) return
      deviceRef.current = next
      setDevice(next); setEditing(false); setDraft(null); setSelected(null)
      setMessage('Đã chuyển loại màn hình. Các thay đổi chưa lưu của bản xem trước đã được hủy.')
    }
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])
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
  useEffect(() => { setSelected(null) }, [page])
  useEffect(() => {
    const root = document.querySelector('.app-shell')
    if (!root) return undefined
    const identify = () => {
      for (const element of root.querySelectorAll('[data-vera-node]')) {
        if (element.closest('.layout-designer, .break-alert-stack')) continue
        if (element.closest('table') && !element.matches('button,input,select,textarea,label')) continue
        const key = layoutKey(element, page)
        if (!key) continue
        element.dataset.layoutKey = key
        element.dataset.layoutEditable = editing && element.matches(layoutCandidates) ? 'true' : 'false'
        const parent = element.parentElement
        if (parent?.dataset.veraNode) {
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
  const move = (source, target) => {
    if (!source || !target || source === target || source.parentElement !== target.parentElement) return
    const parent = source.parentElement
    if (!parent.dataset.layoutKey || parent.matches('table,thead,tbody,tr')) { setMessage('Nhóm này giữ bố cục cố định để không tràn màn hình.'); return }
    const children = [...parent.children].filter(item => item.dataset.layoutKey)
      .sort((a,b) => Number(preview[a.dataset.layoutKey]?.order ?? [...parent.children].indexOf(a)) - Number(preview[b.dataset.layoutKey]?.order ?? [...parent.children].indexOf(b)))
    const from = children.indexOf(source), to = children.indexOf(target)
    if (from < 0 || to < 0) return
    children.splice(from, 1); children.splice(to, 0, source)
    setDraft(current => {
      const next = { ...current }
      children.forEach((item, index) => { next[item.dataset.layoutKey] = { ...next[item.dataset.layoutKey], order: index, parent: parent.dataset.layoutKey } })
      return next
    })
    setSelected(source); setMessage('Đã đổi vị trí trong bản xem trước. Bấm Lưu để áp dụng cho mọi người.')
  }
  const moveRef = useRef(move); moveRef.current = move
  useEffect(() => {
    if (!editing) return undefined
    const candidate = target => target?.closest?.('[data-layout-editable="true"]')
    const down = event => {
      if (event.target.closest('.layout-designer')) return
      const element = candidate(event.target)
      if (!element) return
      event.preventDefault(); event.stopPropagation()
      setSelected(element)
      dragging.current = { element, x: event.clientX, y: event.clientY }
    }
    const up = event => {
      const start = dragging.current; dragging.current = null
      if (!start) return
      const target = candidate(document.elementFromPoint(event.clientX, event.clientY))
      if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > 12) moveRef.current(start.element, target)
    }
    const block = event => { if (!event.target.closest('.layout-designer')) { event.preventDefault(); event.stopPropagation() } }
    document.addEventListener('pointerdown', down, true)
    document.addEventListener('pointerup', up, true)
    document.addEventListener('click', block, true)
    return () => { document.removeEventListener('pointerdown', down, true); document.removeEventListener('pointerup', up, true); document.removeEventListener('click', block, true) }
  }, [editing])
  const patch = (key, value) => setDraft(current => ({ ...current, [selectedKey]: { ...current[selectedKey], [key]: value === '' ? undefined : Number(value) } }))
  const step = (direction) => {
    if (!selected?.parentElement) return
    const siblings = [...selected.parentElement.children].filter(item => item.dataset.layoutKey)
      .sort((a,b) => Number(preview[a.dataset.layoutKey]?.order ?? [...selected.parentElement.children].indexOf(a)) - Number(preview[b.dataset.layoutKey]?.order ?? [...selected.parentElement.children].indexOf(b)))
    move(selected, siblings[siblings.indexOf(selected) + direction])
  }
  const selectParent = () => {
    const parent = selected?.parentElement
    if (!parent?.dataset.veraNode || parent.matches('.app-shell,.sidebar,.main-area,table,thead,tbody,tr,td,th')) return
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
    if (editing && JSON.stringify(draft) !== JSON.stringify(saved.layout[device] || {}) && !window.confirm('Đóng và hủy các thay đổi bố cục chưa lưu?')) return
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
    <style>{layoutCss(preview)}{editing && selectedKey ? `[data-layout-key="${selectedKey}"]{outline:3px solid #c49524!important;outline-offset:2px}` : ''}</style>
    {admin && open && <aside className="layout-designer" aria-label="Tùy chỉnh bố cục Admin">
      <button type="button" disabled={busy} onClick={close} aria-label="Đóng chỉnh bố cục">Đóng ✕</button>
      {!editing ? <><button type="button" disabled={!loaded} onClick={() => { setDraft({ ...saved.layout[device] }); setEditing(true); setMessage('Chọn một thành phần. Kéo thả trong cùng nhóm để đổi vị trí.') }}>Chỉnh bố cục · {device === 'mobile' ? 'Mobile' : 'Desktop'}</button>{message && <small role="status">{message}</small>}</> : <>
        <strong>Bố cục {device === 'mobile' ? 'Mobile' : 'Desktop'}</strong><small>Chọn menu, tab, nút hoặc khung; kéo thả trong cùng nhóm. Bản còn lại được giữ riêng.</small>
        {selectedKey && <><small>Đã chọn: {selected.getAttribute('aria-label') || selected.textContent?.trim().slice(0, 70) || selected.tagName}</small><div className="layout-designer-actions"><button type="button" onClick={() => step(-1)}>← Trước</button><button type="button" onClick={() => step(1)}>Sau →</button><button type="button" onClick={selectParent}>Chọn khung cha</button></div><label>Rộng (px)<input type="number" min="32" max="2400" value={configuration.width ?? ''} placeholder="Tự động" onChange={e => patch('width', e.target.value)}/></label><label>Cao tối thiểu (px)<input type="number" min="24" max="1600" value={configuration.height ?? ''} placeholder="Tự động" onChange={e => patch('height', e.target.value)}/></label><button type="button" onClick={() => setDraft(current => { const next = { ...current }; delete next[selectedKey]; return next })}>Khôi phục thành phần</button></>}
        <div className="layout-designer-actions"><button type="button" disabled={busy} onClick={save}>{busy ? 'Đang lưu…' : 'Lưu cho tất cả'}</button><button type="button" disabled={busy} onClick={() => { setEditing(false); setDraft(null); setSelected(null) }}>Hủy</button><button type="button" disabled={busy} onClick={() => { if (window.confirm('Khôi phục toàn bộ bố cục thiết bị này? Bấm Lưu để áp dụng.')) setDraft({}) }}>Mặc định</button></div>
        {message && <small role="status">{message}</small>}
      </>}
    </aside>}
  </>
}
