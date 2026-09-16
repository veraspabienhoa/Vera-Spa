from pathlib import Path

ROOT = Path('.')


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'Missing patch anchor: {label}')
    return text.replace(old, new, 1)


appearance_lib = r'''const normalize = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').trim().toUpperCase()

export const LIVE_TOUR_ROOM_TEXT_FIELDS = [
  ['title', 'Tên phòng'],
  ['type', 'Loại phòng (VIP / STANDARD / BÀN / GIƯỜNG)'],
  ['customer_count', 'Số khách'],
  ['countdown', 'Thời gian còn lại / Đang trống / Đã hết giờ'],
  ['staff', 'Tên nhân viên trong phòng'],
  ['meta', 'Nội dung phòng trống'],
  ['private_badge', 'Badge PR'],
]

export const LIVE_TOUR_COLUMN_DEFINITIONS = [
  'STT', 'Tên nhân viên', 'Thao tác', 'Lịch hẹn', 'Trạng thái', 'Phòng', 'TG CÒN LẠI', 'Yêu cầu', 'Dịch vụ',
  'Đi làm', 'Vào ca', 'Breaktime', 'TG nghỉ còn lại', 'Giờ ra', 'Giờ vào', 'Ghi chú', 'Thời lượng',
  'TG bắt đầu thực hiện', 'TG bắt đầu thực hiện YC', 'TT thanh toán', 'Kết quả hoàn thành', 'SL tua',
  'SL yêu cầu', 'Tổng SL', 'VIP', 'Giờ Booking', 'TG khách chờ', 'TG Xông Hơi',
]

const MOBILE_VISIBLE = new Set(['STT', 'Tên nhân viên', 'Thao tác', 'Lịch hẹn', 'Trạng thái', 'Phòng', 'TG CÒN LẠI', 'Yêu cầu', 'Dịch vụ'])
const FONT_FAMILIES = new Set(['', 'system-ui', 'Arial', 'Georgia', 'Tahoma', 'Verdana', 'Times New Roman', 'Courier New'])
const FONT_WEIGHTS = new Set(['', '400', '500', '600', '700', '800', '900'])
const FONT_STYLES = new Set(['', 'normal', 'italic'])

const defaultRoomText = () => Object.fromEntries(LIVE_TOUR_ROOM_TEXT_FIELDS.map(([key]) => [key, {
  font_size: 0, font_family: '', font_weight: '', font_style: '', color: '',
}]))

const defaultColumns = (device) => LIVE_TOUR_COLUMN_DEFINITIONS.map((key, order) => ({
  key, order, visible: device === 'mobile' ? MOBILE_VISIBLE.has(key) : true, width: 0, font_size: 0,
}))

const defaultDevice = (device) => ({
  room: { height: 0, width: 0 },
  room_text: defaultRoomText(),
  columns: defaultColumns(device),
})

export const DEFAULT_LIVE_TOUR_APPEARANCE = {
  desktop: defaultDevice('desktop'),
  mobile: defaultDevice('mobile'),
}

const bounded = (value, min, max, fallback = 0) => {
  const number = Number(value)
  return Number.isFinite(number) ? Math.max(min, Math.min(max, number)) : fallback
}

const cleanColor = (value) => /^#[0-9a-f]{6}$/i.test(String(value || '')) ? String(value) : ''

const mergeDevice = (raw, device) => {
  const base = defaultDevice(device)
  const room = raw?.room && typeof raw.room === 'object' ? raw.room : {}
  const roomText = raw?.room_text && typeof raw.room_text === 'object' ? raw.room_text : {}
  const sourceColumns = Array.isArray(raw?.columns) ? raw.columns : []
  const columnMap = new Map(sourceColumns.map((item) => [String(item?.key || ''), item]))
  return {
    room: {
      height: bounded(room.height, 0, 260),
      width: bounded(room.width, 0, 520),
    },
    room_text: Object.fromEntries(LIVE_TOUR_ROOM_TEXT_FIELDS.map(([key]) => {
      const source = roomText[key] && typeof roomText[key] === 'object' ? roomText[key] : {}
      return [key, {
        font_size: bounded(source.font_size, 0, 64),
        font_family: FONT_FAMILIES.has(String(source.font_family || '')) ? String(source.font_family || '') : '',
        font_weight: FONT_WEIGHTS.has(String(source.font_weight || '')) ? String(source.font_weight || '') : '',
        font_style: FONT_STYLES.has(String(source.font_style || '')) ? String(source.font_style || '') : '',
        color: cleanColor(source.color),
      }]
    })),
    columns: base.columns.map((item) => {
      const source = columnMap.get(item.key) || {}
      return {
        key: item.key,
        order: bounded(source.order, 0, 200, item.order),
        visible: typeof source.visible === 'boolean' ? source.visible : item.visible,
        width: bounded(source.width, 0, 600),
        font_size: bounded(source.font_size, 0, 32),
      }
    }).sort((a, b) => a.order - b.order),
  }
}

export function mergeLiveTourAppearance(raw) {
  return {
    desktop: mergeDevice(raw?.desktop, 'desktop'),
    mobile: mergeDevice(raw?.mobile, 'mobile'),
  }
}

export function resetLiveTourAppearanceDevice(device) {
  return defaultDevice(device === 'mobile' ? 'mobile' : 'desktop')
}

export function liveTourColumnKey(label) {
  const key = normalize(label)
  if (key === 'STT' || key === 'SO THU TU') return 'STT'
  if (['TEN NHAN VIEN', 'NHAN VIEN', 'HO VA TEN', 'HO TEN'].includes(key)) return 'Tên nhân viên'
  if (key.includes('LICH HEN')) return 'Lịch hẹn'
  if (key === 'TRANG THAI') return 'Trạng thái'
  if (key === 'PHONG' || key.startsWith('PHONG (')) return 'Phòng'
  if (key === 'TG CON LAI' || key === 'THOI GIAN CON LAI') return 'TG CÒN LẠI'
  if (key === 'YEU CAU' || key.startsWith('YEU CAU (')) return 'Yêu cầu'
  if (key === 'DICH VU' || key.startsWith('DICH VU (')) return 'Dịch vụ'
  return LIVE_TOUR_COLUMN_DEFINITIONS.find((name) => normalize(name) === key) || String(label || '')
}

export function buildLiveTourTableLayout(columns, deviceSettings, canOperate) {
  const configured = new Map((deviceSettings?.columns || []).map((item, index) => [item.key, { ...item, _index: index }]))
  const entries = (columns || []).map((column, index) => {
    const key = liveTourColumnKey(column)
    const cfg = configured.get(key)
    return { kind: 'column', column, key, order: cfg?.order ?? 100 + index, visible: cfg?.visible !== false }
  })
  if (canOperate) {
    const cfg = configured.get('Thao tác')
    entries.push({ kind: 'actions', column: '', key: 'Thao tác', order: cfg?.order ?? 2, visible: cfg?.visible !== false })
  }
  return entries.filter((entry) => entry.visible).sort((a, b) => a.order - b.order)
}

const cssEscape = (value) => String(value || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')
const familyCss = (value) => value === 'Times New Roman' || value === 'Courier New' ? `"${value}"` : value

export function buildLiveTourAppearanceCss(deviceSettings) {
  const settings = deviceSettings || defaultDevice('desktop')
  const lines = []
  const roomHeight = Number(settings.room?.height || 0)
  const roomWidth = Number(settings.room?.width || 0)
  if (roomHeight > 0) {
    lines.push(`html body .live-tour-page .tour-room-grid{grid-auto-rows:${roomHeight}px!important}`)
    lines.push(`html body .live-tour-page .tour-room-card{height:${roomHeight}px!important;min-height:${roomHeight}px!important;max-height:${roomHeight}px!important}`)
  }
  if (roomWidth > 0) {
    lines.push(`html body .live-tour-page .tour-room-grid{grid-template-columns:repeat(auto-fill,minmax(${roomWidth}px,1fr))!important}`)
  }
  const selectors = {
    title: '.tour-room-card-head>strong', type: '.tour-room-type', customer_count: '.tour-room-customer-count',
    countdown: '.tour-room-countdown,.tour-room-countdown span', staff: '.tour-room-staff', meta: '.tour-room-meta',
    private_badge: '.tour-room-private-badge',
  }
  for (const [key, selector] of Object.entries(selectors)) {
    const style = settings.room_text?.[key] || {}
    const declarations = []
    if (Number(style.font_size) > 0) declarations.push(`font-size:${Number(style.font_size)}px!important`)
    if (style.font_family) declarations.push(`font-family:${familyCss(style.font_family)},sans-serif!important`)
    if (style.font_weight) declarations.push(`font-weight:${style.font_weight}!important`)
    if (style.font_style) declarations.push(`font-style:${style.font_style}!important`)
    if (style.color) declarations.push(`color:${style.color}!important`)
    if (declarations.length) lines.push(`html body .live-tour-page .tour-room-grid ${selector}{${declarations.join(';')}}`)
  }
  for (const column of settings.columns || []) {
    const declarations = []
    if (Number(column.width) > 0) declarations.push(`width:${Number(column.width)}px!important`, `min-width:${Number(column.width)}px!important`, `max-width:${Number(column.width)}px!important`)
    if (Number(column.font_size) > 0) declarations.push(`font-size:${Number(column.font_size)}px!important`)
    if (declarations.length) lines.push(`html body .live-tour-page .tour-table [data-appearance-key="${cssEscape(column.key)}"]{${declarations.join(';')}}`)
  }
  return lines.join('\n')
}
'''

appearance_page = r'''import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, RotateCcw, Save } from 'lucide-react'
import { veraApi } from '../lib/api'
import {
  LIVE_TOUR_ROOM_TEXT_FIELDS,
  mergeLiveTourAppearance,
  resetLiveTourAppearanceDevice,
} from '../lib/liveTourAppearance'

const FONT_OPTIONS = ['', 'system-ui', 'Arial', 'Georgia', 'Tahoma', 'Verdana', 'Times New Roman', 'Courier New']
const WEIGHT_OPTIONS = ['', '400', '500', '600', '700', '800', '900']
const STYLE_OPTIONS = ['', 'normal', 'italic']

function NumberField({ value, onChange, min = 0, max, step = 1, label }) {
  return <label className="appearance-field"><span>{label}</span><input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value || 0))}/></label>
}

export default function AppearanceSettingsPage({ user }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [device, setDevice] = useState('desktop')
  const [draft, setDraft] = useState(() => mergeLiveTourAppearance({}))
  const [revision, setRevision] = useState(null)
  const [busy, setBusy] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    if (!isAdmin) return
    setBusy(true); setError('')
    try {
      const result = await veraApi.liveTour(true)
      setDraft(mergeLiveTourAppearance(result?.appearance_settings || {}))
      setRevision(result?.revision ?? null)
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

  const save = async () => {
    if (revision == null || saving) return
    setSaving(true); setError(''); setMessage('')
    try {
      const result = await veraApi.liveTourAction({
        action: 'appearance_settings_update', payload: draft, expected_revision: revision,
        idempotency_key: crypto.randomUUID(),
      })
      setDraft(mergeLiveTourAppearance(result?.appearance_settings || draft))
      setRevision(result?.revision ?? revision)
      setMessage('Đã lưu giao diện. Live Tour trên Desktop/Mobile sẽ dùng cấu hình mới khi làm mới dữ liệu.')
    } catch (err) {
      setError(err?.status === 409 ? 'Dữ liệu Live Tour vừa thay đổi. Hãy bấm Làm mới rồi lưu lại.' : err?.message || 'Không lưu được giao diện.')
    } finally { setSaving(false) }
  }

  const columnCount = useMemo(() => current.columns.filter((item) => item.visible).length, [current.columns])
  if (!isAdmin) return <div className="panel">Chỉ Admin được cấu hình giao diện.</div>

  return <div className="feature-page appearance-settings-page">
    <style>{`
      .appearance-settings-page{display:grid;gap:14px}.appearance-head{display:flex;align-items:end;justify-content:space-between;gap:12px;flex-wrap:wrap}.appearance-head h1{margin:0}.appearance-tabs{display:flex;gap:8px}.appearance-card{border:1px solid #c8d9d0;border-radius:14px;background:#fff;padding:14px;display:grid;gap:12px}.appearance-card h2{margin:0;font-size:18px}.appearance-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.appearance-field{display:grid;gap:5px}.appearance-field>span{font-size:12px;font-weight:800}.appearance-field input,.appearance-field select{width:100%;min-height:38px}.appearance-table{width:100%;border-collapse:collapse}.appearance-table th,.appearance-table td{border:1px solid #d3e0da;padding:7px;vertical-align:middle}.appearance-table th{font-size:11px;text-align:left;background:#f3f8f5}.appearance-table input[type=number]{width:78px}.appearance-table input[type=color]{width:42px;height:34px;padding:2px}.appearance-row-actions{display:flex;gap:4px}.appearance-row-actions button{min-width:34px;min-height:32px;padding:3px}.appearance-savebar{position:sticky;bottom:8px;z-index:2;display:flex;justify-content:flex-end;gap:8px;padding:10px;border:1px solid #c8d9d0;border-radius:12px;background:rgba(247,250,248,.96)}.appearance-help{margin:0;color:#557267;font-size:12px}.appearance-scroll{overflow-x:auto}.appearance-color{display:flex;align-items:center;gap:6px}.appearance-color input[type=text]{min-width:90px}
      @media(max-width:820px){.appearance-grid{grid-template-columns:1fr}.appearance-card{padding:10px}.appearance-table th,.appearance-table td{padding:5px;font-size:10px}.appearance-table input[type=number]{width:65px}.appearance-scroll{margin-inline:-4px}.appearance-head{align-items:flex-start}}
    `}</style>
    <div className="appearance-head"><div><div className="topbar-kicker">ADMIN</div><h1>Giao diện</h1><p className="appearance-help">Cấu hình Live Tour độc lập cho Desktop và Mobile. Giá trị 0 nghĩa là giữ kích thước CSS mặc định hiện tại.</p></div><div className="appearance-tabs"><button type="button" className={device === 'desktop' ? 'primary-button' : 'secondary-button'} onClick={() => setDevice('desktop')}>Desktop</button><button type="button" className={device === 'mobile' ? 'primary-button' : 'secondary-button'} onClick={() => setDevice('mobile')}>Mobile</button></div></div>
    {busy ? <div className="panel">Đang tải cấu hình…</div> : <>
      {error && <div className="error-box">{error}</div>}{message && <div className="setup-note">{message}</div>}
      <section className="appearance-card"><h2>1. Kích thước phòng · {device === 'mobile' ? 'Mobile' : 'Desktop'}</h2><div className="appearance-grid"><NumberField label="Độ cao phòng (px)" value={current.room.height} min={0} max={260} onChange={(height) => patchDevice({ room: { ...current.room, height } })}/><NumberField label="Độ rộng tối thiểu phòng (px)" value={current.room.width} min={0} max={520} onChange={(width) => patchDevice({ room: { ...current.room, width } })}/></div></section>
      <section className="appearance-card"><h2>2. Chữ hiển thị trong phòng</h2><div className="appearance-scroll"><table className="appearance-table"><thead><tr><th>Nội dung</th><th>Size</th><th>Font</th><th>Độ đậm</th><th>Kiểu</th><th>Màu chữ</th></tr></thead><tbody>{LIVE_TOUR_ROOM_TEXT_FIELDS.map(([key,label]) => { const style = current.room_text[key]; return <tr key={key}><td><strong>{label}</strong></td><td><input aria-label={`Size ${label}`} type="number" min="0" max="64" step="0.5" value={style.font_size} onChange={(event) => patchRoomText(key,{font_size:Number(event.target.value || 0)})}/></td><td><select value={style.font_family} onChange={(event) => patchRoomText(key,{font_family:event.target.value})}>{FONT_OPTIONS.map((value) => <option key={value || 'default'} value={value}>{value || 'Mặc định'}</option>)}</select></td><td><select value={style.font_weight} onChange={(event) => patchRoomText(key,{font_weight:event.target.value})}>{WEIGHT_OPTIONS.map((value) => <option key={value || 'default'} value={value}>{value || 'Mặc định'}</option>)}</select></td><td><select value={style.font_style} onChange={(event) => patchRoomText(key,{font_style:event.target.value})}>{STYLE_OPTIONS.map((value) => <option key={value || 'default'} value={value}>{value || 'Mặc định'}</option>)}</select></td><td><div className="appearance-color"><input type="color" value={style.color || '#173c30'} onChange={(event) => patchRoomText(key,{color:event.target.value})}/><input type="text" placeholder="Mặc định" value={style.color} onChange={(event) => patchRoomText(key,{color:event.target.value})}/></div></td></tr> })}</tbody></table></div></section>
      <section className="appearance-card"><h2>3–6. Cột bảng tua</h2><p className="appearance-help">Đang hiển thị {columnCount}/{current.columns.length} cột. Bật/tắt cột, chỉnh độ rộng, size chữ và dùng ↑ ↓ để đổi vị trí.</p><div className="appearance-scroll"><table className="appearance-table"><thead><tr><th>Hiện</th><th>Vị trí</th><th>Tên cột</th><th>Rộng (px)</th><th>Size chữ</th></tr></thead><tbody>{current.columns.map((column,index) => <tr key={column.key}><td><input type="checkbox" checked={column.visible} onChange={(event) => patchColumn(column.key,{visible:event.target.checked})}/></td><td><div className="appearance-row-actions"><button type="button" className="secondary-button" disabled={index===0} onClick={() => moveColumn(index,-1)} aria-label={`Đưa ${column.key} lên`}><ChevronUp size={15}/></button><button type="button" className="secondary-button" disabled={index===current.columns.length-1} onClick={() => moveColumn(index,1)} aria-label={`Đưa ${column.key} xuống`}><ChevronDown size={15}/></button></div></td><td><strong>{column.key}</strong></td><td><input type="number" min="0" max="600" value={column.width} onChange={(event) => patchColumn(column.key,{width:Number(event.target.value || 0)})}/></td><td><input type="number" min="0" max="32" step="0.5" value={column.font_size} onChange={(event) => patchColumn(column.key,{font_size:Number(event.target.value || 0)})}/></td></tr>)}</tbody></table></div></section>
      <div className="appearance-savebar"><button type="button" className="secondary-button" onClick={() => patchDevice(resetLiveTourAppearanceDevice(device))}><RotateCcw size={15}/> Khôi phục {device === 'mobile' ? 'Mobile' : 'Desktop'}</button><button type="button" className="secondary-button" disabled={busy || saving} onClick={load}>Làm mới</button><button type="button" className="primary-button" disabled={saving || revision == null} onClick={save}><Save size={15}/>{saving ? 'Đang lưu…' : 'Lưu giao diện'}</button></div>
    </>}
  </div>
}
'''

Path('web-v2/src/lib/liveTourAppearance.js').write_text(appearance_lib, encoding='utf-8')
Path('web-v2/src/pages/AppearanceSettingsPage.jsx').write_text(appearance_page, encoding='utf-8')

# App route
path = Path('web-v2/src/App.jsx')
text = path.read_text(encoding='utf-8')
text = replace_once(text,
    "'reports', 'customers', 'settings', 'auto-check', 'changes', 'storage'])",
    "'reports', 'customers', 'settings', 'appearance', 'auto-check', 'changes', 'storage'])",
    'App VALID_PAGES')
text = replace_once(text,
    "const AutoCheckPage = lazyPage(() => import('./pages/AutoCheckPage'))",
    "const AutoCheckPage = lazyPage(() => import('./pages/AutoCheckPage'))\nconst AppearanceSettingsPage = lazyPage(() => import('./pages/AppearanceSettingsPage'))",
    'App lazy appearance')
text = replace_once(text,
    "{page === 'settings' && <SpaManagementPage user={shellUser} mode=\"settings\" />}",
    "{page === 'settings' && <SpaManagementPage user={shellUser} mode=\"settings\" />}\n        {page === 'appearance' && <AppearanceSettingsPage user={shellUser} />}",
    'App render appearance')
path.write_text(text, encoding='utf-8')

# Sidebar menu
path = Path('web-v2/src/components/AppShell.jsx')
text = path.read_text(encoding='utf-8')
text = replace_once(text,
    "RadioTower, RefreshCw, ScanLine, Settings2, ShieldCheck, UserRound",
    "RadioTower, RefreshCw, ScanLine, Settings2, Palette, ShieldCheck, UserRound",
    'AppShell Palette import')
text = replace_once(text,
    "{ id: 'settings', label: 'Cài đặt', icon: Settings2, ready: true, permission: 'live_tour_admin' },",
    "{ id: 'settings', label: 'Cài đặt', icon: Settings2, ready: true, permission: 'live_tour_admin' },\n  { id: 'appearance', label: 'Giao diện', icon: Palette, ready: true, adminOnly: true },",
    'AppShell appearance item')
path.write_text(text, encoding='utf-8')

# Live Tour integration
path = Path('web-v2/src/pages/LiveTourPage.jsx')
text = path.read_text(encoding='utf-8')
text = replace_once(text,
    "import { catalogIsAvailable, catalogTransactionDate, comboUsagePreview, comboExtraSubtotal, vietnamDate } from '../lib/serviceCatalog'",
    "import { catalogIsAvailable, catalogTransactionDate, comboUsagePreview, comboExtraSubtotal, vietnamDate } from '../lib/serviceCatalog'\nimport { buildLiveTourAppearanceCss, buildLiveTourTableLayout, mergeLiveTourAppearance } from '../lib/liveTourAppearance'",
    'LiveTour appearance import')
text = replace_once(text,
    "customers: [], pending_payments: [], reports: {}, audit: [], backups: [], capabilities: {}, revision: null,",
    "customers: [], pending_payments: [], reports: {}, audit: [], backups: [], capabilities: {}, appearance_settings: {}, revision: null,",
    'LiveTour empty appearance')
text = replace_once(text,
    "const [customScope, setCustomScope] = useState('displayed')",
    "const [customScope, setCustomScope] = useState('displayed')\n  const [appearanceMobile, setAppearanceMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 820px)').matches)",
    'LiveTour mobile appearance state')
text = replace_once(text,
    "  useEffect(() => {\n    const interval = window.setInterval(() => setClockMs(Date.now()), 1000)\n    return () => window.clearInterval(interval)\n  }, [])",
    "  useEffect(() => {\n    const interval = window.setInterval(() => setClockMs(Date.now()), 1000)\n    return () => window.clearInterval(interval)\n  }, [])\n\n  useEffect(() => {\n    const media = window.matchMedia('(max-width: 820px)')\n    const sync = () => setAppearanceMobile(media.matches)\n    sync()\n    media.addEventListener?.('change', sync)\n    return () => media.removeEventListener?.('change', sync)\n  }, [])",
    'LiveTour appearance media effect')
text = replace_once(text,
    "  const validRecords = useMemo(() => asArray(data.records).filter((record) => validLiveTourRecord(record, columns)), [columns, data.records])",
    "  const appearanceSettings = useMemo(() => mergeLiveTourAppearance(data.appearance_settings || {}), [data.appearance_settings])\n  const activeAppearance = appearanceSettings[appearanceMobile ? 'mobile' : 'desktop']\n  const appearanceTableColumns = useMemo(() => buildLiveTourTableLayout(columns, activeAppearance, canOperate), [activeAppearance, canOperate, columns])\n  const appearanceCss = useMemo(() => buildLiveTourAppearanceCss(activeAppearance), [activeAppearance])\n  const validRecords = useMemo(() => asArray(data.records).filter((record) => validLiveTourRecord(record, columns)), [columns, data.records])",
    'LiveTour appearance derived state')
text = replace_once(text,
    "  return <div className=\"feature-page tour-page live-tour-page\">\n    <style>{`",
    "  return <div className=\"feature-page tour-page live-tour-page\">\n    <style>{appearanceCss}</style>\n    <style>{`",
    'LiveTour runtime appearance CSS')
old_table = '''      <div className="responsive-data-table tour-table" tabIndex="0" aria-label="Danh sách Live Tour"><table><thead><tr><th className="live-tour-select-col"><input type="checkbox" checked={allDisplayedSelected} onChange={toggleDisplayed} aria-label="Chọn tất cả nhân viên đang hiển thị"/></th>{columns.map((column) => <Fragment key={column}><th className={columnClass(column)}>{column}</th>{column === employeeColumn && canOperate && <th className="live-tour-actions-col">Thao tác</th>}</Fragment>)}</tr></thead><tbody>{displayedRecords.map((item, index) => {
        const id = recordId(item, index)
        return <tr className={rowClass(item, selectedIds.has(id), data.payment_settings?.shift_ready_times, clockMs)} key={id} onClick={(event) => { if (!event.target.closest('button,input,a,select')) toggleRow(id) }}><td className="live-tour-select-col"><input type="checkbox" checked={selectedIds.has(id)} onChange={() => toggleRow(id)} aria-label={`Chọn ${cellValue(item, employeeColumn)}`}/></td>{columns.map((column) => <Fragment key={column}><td className={columnClass(column)}>{column === employeeColumn ? <button type="button" className="text-button" title={String(item[column] ?? '')} disabled={!canOperate && !canPayment && !canBook} onClick={() => openEmployeeBooking(item)}>{String(item[column] ?? '')}</button> : column === appointmentColumn && canEditAppointment ? appointmentEditor(item) : column === sttColumn(columns) ? String(item[column] ?? '') : (column === statusColumn && hasGroup(item, 'doing') ? 'Thực hiện' : String(breakCellValue(item, column, clockMs)))}</td>{column === employeeColumn && canOperate && <td className="live-tour-actions-col">{employeeServiceActions(item)}</td>}</Fragment>)}</tr>
      })}</tbody></table></div>'''
new_table = '''      <div className="responsive-data-table tour-table" tabIndex="0" aria-label="Danh sách Live Tour"><table><thead><tr><th className="live-tour-select-col"><input type="checkbox" checked={allDisplayedSelected} onChange={toggleDisplayed} aria-label="Chọn tất cả nhân viên đang hiển thị"/></th>{appearanceTableColumns.map((entry) => entry.kind === 'actions'
        ? <th className="live-tour-actions-col" data-appearance-key="Thao tác" key="__actions">Thao tác</th>
        : <th className={columnClass(entry.column)} data-appearance-key={entry.key} key={entry.column}>{entry.column}</th>)}</tr></thead><tbody>{displayedRecords.map((item, index) => {
        const id = recordId(item, index)
        return <tr className={rowClass(item, selectedIds.has(id), data.payment_settings?.shift_ready_times, clockMs)} key={id} onClick={(event) => { if (!event.target.closest('button,input,a,select')) toggleRow(id) }}><td className="live-tour-select-col"><input type="checkbox" checked={selectedIds.has(id)} onChange={() => toggleRow(id)} aria-label={`Chọn ${cellValue(item, employeeColumn)}`}/></td>{appearanceTableColumns.map((entry) => {
          if (entry.kind === 'actions') return <td className="live-tour-actions-col" data-appearance-key="Thao tác" key="__actions">{employeeServiceActions(item)}</td>
          const column = entry.column
          return <td className={columnClass(column)} data-appearance-key={entry.key} key={column}>{column === employeeColumn ? <button type="button" className="text-button" title={String(item[column] ?? '')} disabled={!canOperate && !canPayment && !canBook} onClick={() => openEmployeeBooking(item)}>{String(item[column] ?? '')}</button> : column === appointmentColumn && canEditAppointment ? appointmentEditor(item) : column === sttColumn(columns) ? String(item[column] ?? '') : (column === statusColumn && hasGroup(item, 'doing') ? 'Thực hiện' : String(breakCellValue(item, column, clockMs)))}</td>
        })}</tr>
      })}</tbody></table></div>'''
text = replace_once(text, old_table, new_table, 'LiveTour table appearance layout')
path.write_text(text, encoding='utf-8')

# Backend persistence and API projection
path = Path('vera_web_v2_live_tour.py')
text = path.read_text(encoding='utf-8')
text = replace_once(text,
    '"update_booking", "cancel_booking", "restart_booking", "change_employee", "update_appointment", "update_started_at", "finish_to_pending", "payment_settings_update", "start_room", "finish_room", "clear_orphan_pending",',
    '"update_booking", "cancel_booking", "restart_booking", "change_employee", "update_appointment", "update_started_at", "finish_to_pending", "payment_settings_update", "appearance_settings_update", "start_room", "finish_room", "clear_orphan_pending",',
    'backend idempotency appearance action')
text = replace_once(text,
    '"break_events": [], "payment_settings": _default_payment_settings(),',
    '"break_events": [], "payment_settings": _default_payment_settings(), "appearance_settings": {},',
    'backend empty appearance state')
text = replace_once(text,
    '    state.setdefault("payment_settings", _default_payment_settings())\n',
    '    state.setdefault("payment_settings", _default_payment_settings())\n    if not isinstance(state.get("appearance_settings"), dict):\n        state["appearance_settings"] = {}\n',
    'backend normalize appearance')
text = replace_once(text,
    'def _required_action_feature(action: str) -> str:\n',
    'def _required_action_feature(action: str) -> str:\n    if action == "appearance_settings_update":\n        return "live_tour_admin"\n',
    'backend appearance permission')
helper = '''\n\ndef _appearance_settings_update(payload: dict[str, Any]) -> dict[str, Any]:\n    if not isinstance(payload, dict):\n        raise HTTPException(400, "Cấu hình giao diện không hợp lệ.")\n    unknown = set(payload) - {"desktop", "mobile"}\n    if unknown:\n        raise HTTPException(400, "Cấu hình giao diện chỉ nhận Desktop và Mobile.")\n    for device in ("desktop", "mobile"):\n        value = payload.get(device, {})\n        if not isinstance(value, dict):\n            raise HTTPException(400, f"Cấu hình {device} không hợp lệ.")\n        if set(value) - {"room", "room_text", "columns"}:\n            raise HTTPException(400, f"Cấu hình {device} có trường không hỗ trợ.")\n        if "columns" in value and (not isinstance(value["columns"], list) or len(value["columns"]) > 80):\n            raise HTTPException(400, "Danh sách cột giao diện không hợp lệ.")\n    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)\n    if len(encoded.encode("utf-8")) > 100_000:\n        raise HTTPException(400, "Cấu hình giao diện vượt giới hạn 100 KB.")\n    return deepcopy(payload)\n'''
anchor = 'def _apply_action(state: dict[str, Any], action: str, payload: dict[str, Any], actor: str, now: datetime) -> dict[str, Any]:\n'
if '_appearance_settings_update' not in text:
    text = replace_once(text, anchor, helper + '\n' + anchor, 'backend appearance helper')
text = replace_once(text,
    '    elif action == "payment_settings_update":\n',
    '    elif action == "appearance_settings_update":\n        state["appearance_settings"] = _appearance_settings_update(payload)\n        result["appearance_settings"] = deepcopy(state["appearance_settings"])\n    elif action == "payment_settings_update":\n',
    'backend appearance action branch')
state_idx = text.index('def _state_response(')
payment_idx = text.index('"payment_settings"', state_idx)
line_start = text.rfind('\n', state_idx, payment_idx) + 1
if '"appearance_settings"' not in text[state_idx:payment_idx]:
    indent = text[line_start:payment_idx]
    text = text[:line_start] + indent + '"appearance_settings": deepcopy(state.get("appearance_settings") or {}),\n' + text[line_start:]
path.write_text(text, encoding='utf-8')

# Focused regression tests
test = r'''from datetime import datetime
from zoneinfo import ZoneInfo

import vera_web_v2_live_tour as live

NOW = datetime(2026, 9, 17, 10, 0, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))


def test_appearance_settings_are_persistent_and_projected():
    state = live._empty_state(NOW)
    payload = {
        'desktop': {'room': {'height': 104, 'width': 150}, 'room_text': {}, 'columns': []},
        'mobile': {'room': {'height': 96, 'width': 92}, 'room_text': {}, 'columns': []},
    }
    result = live._apply_action(state, 'appearance_settings_update', payload, 'admin', NOW)
    assert result['appearance_settings']['desktop']['room']['height'] == 104
    projected = live._state_response(state, 3, NOW)
    assert projected['appearance_settings'] == payload
    assert live._required_action_feature('appearance_settings_update') == 'live_tour_admin'
    assert 'appearance_settings_update' in live.IDEMPOTENCY_REQUIRED_ACTIONS


def test_appearance_settings_reject_unknown_top_level_device():
    state = live._empty_state(NOW)
    try:
        live._apply_action(state, 'appearance_settings_update', {'tablet': {}}, 'admin', NOW)
    except Exception as exc:
        assert getattr(exc, 'status_code', None) == 400
    else:
        raise AssertionError('Expected invalid appearance settings to fail')
'''
Path('tests/test_live_tour_appearance_settings.py').write_text(test, encoding='utf-8')

print('LIVE_TOUR_APPEARANCE_PATCH=OK')
