const normalize = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').trim().toUpperCase()

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
  'Ô chọn', 'STT', 'Tên nhân viên', 'Thao tác', 'Lịch hẹn', 'Trạng thái', 'Phòng', 'TG CÒN LẠI', 'Yêu cầu', 'Dịch vụ',
  'Đi làm', 'Vào ca', 'Breaktime', 'TG nghỉ còn lại', 'Giờ ra', 'Giờ vào', 'Ghi chú', 'Thời lượng',
  'TG bắt đầu thực hiện', 'TG bắt đầu thực hiện YC', 'TT thanh toán', 'Kết quả hoàn thành', 'SL tua',
  'SL yêu cầu', 'Tổng SL', 'VIP', 'Giờ Booking', 'TG khách chờ', 'TG Xông Hơi',
]

const FONT_FAMILIES = new Set(['', 'system-ui', 'Arial', 'Georgia', 'Tahoma', 'Verdana', 'Times New Roman', 'Courier New'])
const FONT_WEIGHTS = new Set(['', '400', '500', '600', '700', '800', '900'])
const FONT_STYLES = new Set(['', 'normal', 'italic'])

const defaultRoomText = () => Object.fromEntries(LIVE_TOUR_ROOM_TEXT_FIELDS.map(([key]) => [key, {
  font_size: 0, font_family: '', font_weight: '', font_style: '', color: '',
}]))

const defaultColumns = () => LIVE_TOUR_COLUMN_DEFINITIONS.map((key, order) => ({
  key, order, visible: true, width: 0, font_size: 0,
}))

const defaultDevice = () => ({
  room: { height: 0, width: 0, columns_per_row: 0, rows: 0 },
  room_text: defaultRoomText(),
  columns: defaultColumns(),
})

export const DEFAULT_LIVE_TOUR_APPEARANCE = {
  desktop: defaultDevice(),
  mobile: defaultDevice(),
}

const bounded = (value, min, max, fallback = 0) => {
  const number = Number(value)
  return Number.isFinite(number) ? Math.max(min, Math.min(max, number)) : fallback
}

const cleanColor = (value) => /^#[0-9a-f]{6}$/i.test(String(value || '')) ? String(value) : ''

const mergeDevice = (raw, _device) => {
  const base = defaultDevice()
  const room = raw?.room && typeof raw.room === 'object' ? raw.room : {}
  const roomText = raw?.room_text && typeof raw.room_text === 'object' ? raw.room_text : {}
  const sourceColumns = Array.isArray(raw?.columns) ? raw.columns : []
  const columnMap = new Map(sourceColumns.map((item) => [String(item?.key || ''), item]))
  return {
    room: {
      height: bounded(room.height, 0, 260),
      width: bounded(room.width, 0, 520),
      columns_per_row: bounded(room.columns_per_row, 0, 20),
      rows: bounded(room.rows, 0, 20),
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

export function resetLiveTourAppearanceDevice(_device) {
  return defaultDevice()
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
  const selectCfg = configured.get('Ô chọn')
  const entries = [
    { kind: 'select', column: '', key: 'Ô chọn', order: selectCfg?.order ?? 0, visible: selectCfg?.visible !== false },
    ...(columns || []).map((column, index) => {
      const key = liveTourColumnKey(column)
      const cfg = configured.get(key)
      return { kind: 'column', column, key, order: cfg?.order ?? 100 + index, visible: cfg?.visible !== false }
    }),
  ]
  if (canOperate) {
    const cfg = configured.get('Thao tác')
    entries.push({ kind: 'actions', column: '', key: 'Thao tác', order: cfg?.order ?? 2, visible: cfg?.visible !== false })
  }
  return entries.filter((entry) => entry.visible).sort((a, b) => a.order - b.order)
}

const cssEscape = (value) => String(value || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"')
const familyCss = (value) => value === 'Times New Roman' || value === 'Courier New' ? `"${value}"` : value

export function buildLiveTourAppearanceCss(deviceSettings) {
  const settings = deviceSettings || defaultDevice()
  const lines = []
  const roomHeight = Number(settings.room?.height || 0)
  const roomWidth = Number(settings.room?.width || 0)
  const columnsPerRow = Number(settings.room?.columns_per_row || 0)
  const roomRows = Number(settings.room?.rows || 0)
  if (roomHeight > 0) {
    lines.push(`html body .live-tour-page .tour-room-grid{grid-auto-rows:${roomHeight}px!important}`)
    lines.push(`html body .live-tour-page .tour-room-card{height:${roomHeight}px!important;min-height:${roomHeight}px!important;max-height:${roomHeight}px!important}`)
  }
  if (columnsPerRow > 0) {
    lines.push(`html body .live-tour-page .tour-room-grid{grid-template-columns:repeat(${columnsPerRow},minmax(0,1fr))!important}`)
  } else if (roomWidth > 0) {
    lines.push(`html body .live-tour-page .tour-room-grid{grid-template-columns:repeat(auto-fill,minmax(${roomWidth}px,1fr))!important}`)
  }
  if (roomRows > 0) {
    const effectiveHeight = roomHeight > 0 ? roomHeight : 96
    lines.push(`html body .live-tour-page .tour-room-grid{max-height:${roomRows * effectiveHeight + Math.max(0, roomRows - 1) * 4}px!important;overflow-y:auto!important;overflow-x:hidden!important}`)
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
