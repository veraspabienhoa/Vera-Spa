import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, Download, RotateCcw, Save } from 'lucide-react'
import { veraApi } from '../lib/api'
import {
  LIVE_TOUR_ROOM_TEXT_FIELDS,
  mergeLiveTourAppearance,
} from '../lib/liveTourAppearance'

const FONT_OPTIONS = ['', 'system-ui', 'Arial', 'Georgia', 'Tahoma', 'Verdana', 'Times New Roman', 'Courier New']
const WEIGHT_OPTIONS = ['', '400', '500', '600', '700', '800', '900']
const STYLE_OPTIONS = ['', 'normal', 'italic']

function NumberField({ value, onChange, min = 0, max, step = 1, label }) {
  return <label className="appearance-field"><span>{label}</span><input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value || 0))}/></label>
}

function currentDesktopTableFontSize() {
  if (typeof document === 'undefined' || typeof getComputedStyle !== 'function') return 10
  const probe = document.createElement('div')
  probe.className = 'live-tour-page'
  probe.style.cssText = 'position:fixed;left:-10000px;top:-10000px;visibility:hidden;pointer-events:none'
  probe.innerHTML = '<div class="responsive-data-table tour-table"><table><tbody><tr><td data-appearance-key="probe">A</td></tr></tbody></table></div>'
  document.body.appendChild(probe)
  const cell = probe.querySelector('td')
  const value = Number.parseFloat(cell ? getComputedStyle(cell).fontSize : '')
  probe.remove()
  return Number.isFinite(value) && value > 0 ? Math.round(value * 2) / 2 : 10
}

function withCurrentEffectiveColumnFontSizes(settings) {
  const merged = mergeLiveTourAppearance(settings || {})
  const desktopSize = currentDesktopTableFontSize()
  // Current mobile roster CSS is clamp(5px, 1.55vw, 7px). Use a 390px
  // reference viewport when the settings page is opened on desktop so Mobile
  // still receives the effective value instead of the sentinel 0.
  const mobileWidth = typeof window !== 'undefined' && window.innerWidth <= 820 ? window.innerWidth : 390
  const mobileSize = Math.round(Math.min(7, Math.max(5, mobileWidth * 0.0155)) * 2) / 2
  return {
    ...merged,
    desktop: { ...merged.desktop, columns: merged.desktop.columns.map((column) => ({ ...column, font_size: Number(column.font_size) > 0 ? column.font_size : desktopSize })) },
    mobile: { ...merged.mobile, columns: merged.mobile.columns.map((column) => ({ ...column, font_size: Number(column.font_size) > 0 ? column.font_size : mobileSize })) },
  }
}

export default function AppearanceSettingsPage({ user }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [device, setDevice] = useState('desktop')
  const [draft, setDraft] = useState(() => mergeLiveTourAppearance({}))
  const [defaultDraft, setDefaultDraft] = useState(() => mergeLiveTourAppearance({}))
  const [revision, setRevision] = useState(null)
  const [busy, setBusy] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = async ({ announce = false } = {}) => {
    if (!isAdmin) return
    setBusy(true); setError('')
    if (announce) setMessage('')
    try {
      const result = await veraApi.liveTour(true)
      const loaded = withCurrentEffectiveColumnFontSizes(result?.appearance_settings || {})
      setDraft(loaded)
      setDefaultDraft(loaded)
      setRevision(result?.revision ?? null)
      if (announce) setMessage(`Đã lấy thông số hiện tại, bao gồm Size chữ thực tế của các cột, cho giao diện ${device === 'mobile' ? 'Mobile' : 'Desktop'}.`)
    } catch (err) { setError(err?.message || 'Không tải được cài đặt giao diện.') }
    finally { setBusy(false) }
  }

  useEffect(() => { void load() }, [isAdmin])
  const current = draft[device]

  const patchDevice = (patch) => setDraft((state) => ({ ...state, [device]: { ...state[device], ...patch } }))
  const patchRoomText = (key, patch) => patchDevice({ room_text: { ...current.room_text, [key]: { ...current.room_text[key], ...patch } } })
  const patchColumn = (key, patch) => patchDevice({ columns: current.columns.map((item) => item.key === key ? { ...item, ...patch } : item) })
  const moveColumn = (index, direction) => {
    const nextIndex = index + direction
    if (nextIndex < 0 || nextIndex >= current.columns.length) return
    const columns = current.columns.map((item) => ({ ...item }))
    const [item] = columns.splice(index, 1)
    columns.splice(nextIndex, 0, item)
    columns.forEach((column, order) => { column.order = order })
    patchDevice({ columns })
  }

  const persist = async ({ asDefault = false } = {}) => {
    if (revision == null || saving) return
    setSaving(true); setError(''); setMessage('')
    try {
      const result = await veraApi.liveTourAction({
        action: 'appearance_settings_update', payload: draft, expected_revision: revision,
        idempotency_key: crypto.randomUUID(),
      })
      const saved = mergeLiveTourAppearance(result?.appearance_settings || draft)
      setDraft(saved)
      setRevision(result?.revision ?? revision)
      if (asDefault) {
        setDefaultDraft(saved)
        setMessage(`Đã đặt thông số hiện tại làm mặc định cho giao diện ${device === 'mobile' ? 'Mobile' : 'Desktop'}.`)
      } else {
        setMessage('Đã lưu giao diện. Live Tour trên Desktop/Mobile sẽ dùng cấu hình mới khi làm mới dữ liệu.')
      }
    } catch (err) {
      setError(err?.status === 409 ? 'Dữ liệu Live Tour vừa thay đổi. Hãy bấm Lấy thông số hiện tại rồi lưu lại.' : err?.message || 'Không lưu được giao diện.')
    } finally { setSaving(false) }
  }

  const restoreDefault = () => {
    const savedDefault = defaultDraft[device]
    setDraft((state) => ({ ...state, [device]: mergeLiveTourAppearance({ [device]: savedDefault })[device] }))
    setError('')
    setMessage(`Đã khôi phục thông số mặc định của ${device === 'mobile' ? 'Mobile' : 'Desktop'} vào form. Bấm Lưu giao diện để áp dụng.`)
  }

  const columnCount = useMemo(() => current.columns.filter((item) => item.visible).length, [current.columns])
  if (!isAdmin) return <div className="panel">Chỉ Admin được cấu hình giao diện.</div>

  return <div className="feature-page appearance-settings-page">
    <style>{`
      .appearance-settings-page{display:grid;gap:14px}.appearance-head{display:flex;align-items:end;justify-content:space-between;gap:12px;flex-wrap:wrap}.appearance-head h1{margin:0}.appearance-tabs{display:flex;gap:8px}.appearance-card{border:1px solid #c8d9d0;border-radius:14px;background:#fff;padding:14px;display:grid;gap:12px}.appearance-card h2{margin:0;font-size:18px}.appearance-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.appearance-field{display:grid;gap:5px}.appearance-field>span{font-size:12px;font-weight:800}.appearance-field input,.appearance-field select{width:100%;min-height:38px}.appearance-table{width:100%;border-collapse:collapse}.appearance-table th,.appearance-table td{border:1px solid #d3e0da;padding:7px;vertical-align:middle}.appearance-table th{font-size:11px;text-align:left;background:#f3f8f5}.appearance-table input[type=number]{width:78px}.appearance-table input[type=color]{width:42px;height:34px;padding:2px}.appearance-row-actions{display:flex;gap:4px}.appearance-row-actions button{min-width:34px;min-height:32px;padding:3px}.appearance-savebar{position:sticky;bottom:8px;z-index:2;display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;padding:10px;border:1px solid #c8d9d0;border-radius:12px;background:rgba(247,250,248,.96)}.appearance-help{margin:0;color:#557267;font-size:12px}.appearance-scroll{overflow-x:auto}.appearance-color{display:flex;align-items:center;gap:6px}.appearance-color input[type=text]{min-width:90px}
      @media(max-width:820px){.appearance-grid{grid-template-columns:1fr}.appearance-card{padding:10px}.appearance-table th,.appearance-table td{padding:5px;font-size:10px}.appearance-table input[type=number]{width:65px}.appearance-scroll{margin-inline:-4px}.appearance-head{align-items:flex-start}.appearance-savebar button{flex:1 1 145px}}
    `}</style>
    <div className="appearance-head"><div><div className="topbar-kicker">ADMIN</div><h1>Giao diện</h1><p className="appearance-help">Cấu hình Live Tour độc lập cho Desktop và Mobile. Khi mở trang, hệ thống tự lấy cấu hình đang lưu; có thể lấy lại thông số hiện tại hoặc đặt cấu hình đang chỉnh làm mặc định.</p></div><div className="appearance-tabs"><button type="button" className={device === 'desktop' ? 'primary-button' : 'secondary-button'} onClick={() => setDevice('desktop')}>Desktop</button><button type="button" className={device === 'mobile' ? 'primary-button' : 'secondary-button'} onClick={() => setDevice('mobile')}>Mobile</button></div></div>
    {busy ? <div className="panel">Đang tải cấu hình…</div> : <>
      {error && <div className="error-box">{error}</div>}{message && <div className="setup-note">{message}</div>}
      <section className="appearance-card"><h2>1. Khu vực phòng · {device === 'mobile' ? 'Mobile' : 'Desktop'}</h2><p className="appearance-help">Có thể đặt riêng số phòng trên mỗi dòng và số dòng hiển thị. Khi giới hạn số dòng, phần phòng vượt quá sẽ cuộn dọc trong khu vực phòng.</p><div className="appearance-grid"><NumberField label="Độ cao phòng (px)" value={current.room.height} min={0} max={device === 'desktop' ? 1000 : 260} onChange={(height) => patchDevice({ room: { ...current.room, height } })}/><NumberField label="Độ rộng tối thiểu phòng (px)" value={current.room.width} min={0} max={520} onChange={(width) => patchDevice({ room: { ...current.room, width } })}/><NumberField label="Số phòng trên mỗi dòng" value={current.room.columns_per_row} min={0} max={20} onChange={(columns_per_row) => patchDevice({ room: { ...current.room, columns_per_row } })}/><NumberField label="Số dòng cho khu vực phòng" value={current.room.rows} min={0} max={20} onChange={(rows) => patchDevice({ room: { ...current.room, rows } })}/></div></section>
      <section className="appearance-card"><h2>2. Chữ hiển thị trong phòng</h2><div className="appearance-scroll"><table className="appearance-table"><thead><tr><th>Nội dung</th><th>Size</th><th>Font</th><th>Độ đậm</th><th>Kiểu</th><th>Màu chữ</th></tr></thead><tbody>{LIVE_TOUR_ROOM_TEXT_FIELDS.map(([key,label]) => { const style = current.room_text[key]; return <tr key={key}><td><strong>{label}</strong></td><td><input aria-label={`Size ${label}`} type="number" min="0" max="64" step="0.5" value={style.font_size} onChange={(event) => patchRoomText(key,{font_size:Number(event.target.value || 0)})}/></td><td><select value={style.font_family} onChange={(event) => patchRoomText(key,{font_family:event.target.value})}>{FONT_OPTIONS.map((value) => <option key={value || 'default'} value={value}>{value || 'Mặc định'}</option>)}</select></td><td><select value={style.font_weight} onChange={(event) => patchRoomText(key,{font_weight:event.target.value})}>{WEIGHT_OPTIONS.map((value) => <option key={value || 'default'} value={value}>{value || 'Mặc định'}</option>)}</select></td><td><select value={style.font_style} onChange={(event) => patchRoomText(key,{font_style:event.target.value})}>{STYLE_OPTIONS.map((value) => <option key={value || 'default'} value={value}>{value || 'Mặc định'}</option>)}</select></td><td><div className="appearance-color"><input type="color" value={style.color || '#173c30'} onChange={(event) => patchRoomText(key,{color:event.target.value})}/><input type="text" placeholder="Mặc định" value={style.color} onChange={(event) => patchRoomText(key,{color:event.target.value})}/></div></td></tr> })}</tbody></table></div></section>
      <section className="appearance-card"><h2>3–6. Cột bảng tua</h2><p className="appearance-help">Đang hiển thị {columnCount}/{current.columns.length} cột. Bật/tắt cột, chỉnh độ rộng, size chữ và dùng ↑ ↓ để đổi vị trí.</p><div className="appearance-scroll"><table className="appearance-table"><thead><tr><th>Hiện</th><th>Vị trí</th><th>Tên cột</th><th>Rộng (px)</th><th>Size chữ</th></tr></thead><tbody>{current.columns.map((column,index) => <tr key={column.key}><td><input type="checkbox" checked={column.visible} onChange={(event) => patchColumn(column.key,{visible:event.target.checked})}/></td><td><div className="appearance-row-actions"><button type="button" className="secondary-button" disabled={index===0} onClick={() => moveColumn(index,-1)} aria-label={`Đưa ${column.key} lên`}><ChevronUp size={15}/></button><button type="button" className="secondary-button" disabled={index===current.columns.length-1} onClick={() => moveColumn(index,1)} aria-label={`Đưa ${column.key} xuống`}><ChevronDown size={15}/></button></div></td><td><strong>{column.key}</strong></td><td><input type="number" min="0" max="600" value={column.width} onChange={(event) => patchColumn(column.key,{width:Number(event.target.value || 0)})}/></td><td><input type="number" min="0" max="32" step="0.5" value={column.font_size} onChange={(event) => patchColumn(column.key,{font_size:Number(event.target.value || 0)})}/></td></tr>)}</tbody></table></div></section>
      <div className="appearance-savebar"><button type="button" className="secondary-button" disabled={busy || saving} onClick={restoreDefault}><RotateCcw size={15}/> Khôi phục mặc định {device === 'mobile' ? 'Mobile' : 'Desktop'}</button><button type="button" className="secondary-button" disabled={busy || saving} onClick={() => load({ announce: true })}><Download size={15}/> Lấy thông số hiện tại</button><button type="button" className="secondary-button" disabled={saving || revision == null} onClick={() => persist({ asDefault: true })}><Save size={15}/> {saving ? 'Đang lưu…' : 'Đặt làm mặc định'}</button><button type="button" className="primary-button" disabled={saving || revision == null} onClick={() => persist()}><Save size={15}/>{saving ? 'Đang lưu…' : 'Lưu giao diện'}</button></div>
    </>}
  </div>
}
