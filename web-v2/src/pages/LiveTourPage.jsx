import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { formatVeraDateTime } from '../lib/veraDate'
import VeraDateInput from '../components/VeraDateInput'
import ClearableSearchInput from '../components/ClearableSearchInput'
import { isBeforeShiftReady } from '../lib/liveTourShiftReady'
import { breakCellValue } from '../lib/liveTourBreaktime'
import { watchLeaveChanges } from '../lib/leaveRefresh'
import { canChangeEmployee } from '../lib/liveTourEmployeeChange'
import LiveTourPaymentQr from '../components/LiveTourPaymentQr'
import { searchTextMatches } from '../lib/searchText'
import { roomOptionMatches, bookingRoomGroup } from '../lib/liveTourRooms'
import { tourStartOrder } from '../lib/liveTourOrder'
import LiveTourCustomerDialog from '../components/LiveTourCustomerDialog'
import LiveTourFilters from '../components/LiveTourFilters'
import LiveTourRevenueSummary from '../components/LiveTourRevenueSummary'
import { EMPTY_TOUR_FILTERS, filterTourRows, tourDateRange } from '../lib/liveTourFilters'
import {
  BellRing, ClipboardCopy, Clock3, Crown, DoorOpen, Download,
  ExternalLink, History, LayoutGrid, PauseCircle, Play, Plus,
  Printer, RefreshCw, Search, Share2, Trash2, X,
} from 'lucide-react'
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import LiveTourBookingDialog from '../components/LiveTourBookingDialog'
import LiveTourPendingDialog from '../components/LiveTourPendingDialog'
import LiveTourPaidInvoiceDialog from '../components/LiveTourPaidInvoiceDialog'
import LiveTourInvoiceChanges from '../components/LiveTourInvoiceChanges'
import LiveTourPaymentSettings from '../components/LiveTourPaymentSettings'
import LiveTourPartialLeaveSettings from '../components/LiveTourPartialLeaveSettings'
import LiveTourReceipt from '../components/LiveTourReceipt'
import LiveTourSearchSelect from '../components/LiveTourSearchSelect'
import LiveTourServiceActions from '../components/LiveTourServiceActions'
import LiveTourAppointmentInput from '../components/LiveTourAppointmentInput'
import LiveTourTransactionDialog from '../components/LiveTourTransactionDialog'
import LiveTourPageItems from '../components/LiveTourPageItems'
import LiveTourCheckoutCustomer from '../components/LiveTourCheckoutCustomer'
import LiveTourComboImportFields from '../components/LiveTourComboImportFields'
import LiveTourTipInput from '../components/LiveTourTipInput'
import { bookingDateTime, bookingTimeLabel, defaultTipMode } from '../lib/liveTourCheckout'
import { checkoutBookingTime, discountAmount } from '../lib/liveTourBooking'
import { copyPngToClipboard } from '../lib/clipboardImage'
import './LiveTourControls.css'
import { availableBookingPurchase, comboBookingItems, preferredBookingCombo } from '../lib/liveTourComboBooking'
import { customerMatches } from '../lib/customerSearch'
import { catalogIsAvailable, catalogTransactionDate, comboUsagePreview, comboExtraSubtotal, vietnamDate } from '../lib/serviceCatalog'
import { buildLiveTourAppearanceCss, buildLiveTourTableLayout, mergeLiveTourAppearance } from '../lib/liveTourAppearance'
import { startLiveTourClock, startLiveTourPolling } from '../lib/liveTourPerformance'

const EMPTY_LIVE_TOUR = {
  columns: [], records: [], rooms: {}, available_rooms: [], services: [], combo_catalog: [],
  customers: [], pending_payments: [], reports: {}, audit: [], backups: [], capabilities: {}, appearance_settings: {}, revision: null,
}
const LIVE_TOUR_CACHE_MAX_AGE = 10 * 60 * 1000
const PENDING_REMINDER_INTERVAL_MS = 15 * 60 * 1000
const VIP_ROOMS = ['16', '17', '18', '19', '20', '21']
const VIP_ROOM_KEYS = new Set(VIP_ROOMS)
const PANEL_TABS = [
  ['pending', 'Hóa đơn chờ thanh toán'],
  ['invoices', 'Hóa đơn đã thanh toán'],
  ['reports', 'Báo cáo'],
  ['customers', 'Khách hàng'],
  ['history', 'Lịch sử & sao lưu'],
  ['catalog', 'Danh mục'],
]
const EXPORT_KINDS = [
  ['revenue', 'Xuất doanh thu'],
  ['tip', 'Xuất tiền TIP'],
  ['customers', 'Xuất khách hàng'],
  ['pending', 'Xuất chờ thanh toán'],
  ['history', 'Xuất lịch sử'],
  ['breaks', 'Xuất nghỉ giữa ca'],
]
const FILTERED_EXPORT_KINDS = new Set(['revenue', 'tip', 'pending', 'history', 'breaks'])
const PRIVATE_CACHE_KEYS = new Set(['customer_id', 'customer_name', 'customer_phone', 'phone'])

function hasLiveTourExportAccess(kind, capabilities) {
  if (!capabilities.export) return false
  if (kind === 'board' || kind === 'custom') return true
  if (kind === 'history' || kind === 'breaks') return capabilities.history
  if (kind === 'customers') return capabilities.customers
  if (kind === 'pending') return capabilities.pending && capabilities.invoiceView
  if (kind === 'revenue' || kind === 'tip') return capabilities.reports
  if (kind === 'customer_detail') return capabilities.customers && capabilities.invoiceView && capabilities.paidInvoiceView && capabilities.pending && capabilities.reports
  return false
}

function compactExportQuery(filters) {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => String(value || '').trim()))
}

function liveTourCacheKey(user) {
  const identity = user?.employee_username || user?.email || 'viewer'
  return `vera-live-tour-cache:${identity}`
}

function readCachedLiveTour(key) {
  try {
    const cached = JSON.parse(window.sessionStorage.getItem(key) || 'null')
    if (!cached?.savedAt || Date.now() - cached.savedAt > LIVE_TOUR_CACHE_MAX_AGE) return EMPTY_LIVE_TOUR
    if (!Array.isArray(cached.data?.columns) || !Array.isArray(cached.data?.records)) return EMPTY_LIVE_TOUR
    return { ...EMPTY_LIVE_TOUR, ...cacheSafeLiveTour(cached.data) }
  } catch {
    return EMPTY_LIVE_TOUR
  }
}

function sanitizeLiveTourCacheValue(value) {
  if (Array.isArray(value)) return value.map(sanitizeLiveTourCacheValue)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(Object.entries(value).flatMap(([key, nested]) => (
    PRIVATE_CACHE_KEYS.has(key.replace(/^_/, '').toLowerCase()) ? [] : [[key, sanitizeLiveTourCacheValue(nested)]]
  )))
}

function cacheSafeLiveTour(data) {
  // Prune large/private collections before recursively sanitizing. The previous
  // order walked customers, invoices, reports and audit history only to discard
  // them afterwards, causing avoidable main-thread work after every changed poll.
  const source = data && typeof data === 'object' ? data : {}
  const state = source.state && typeof source.state === 'object'
    ? { ...source.state, employees: [], customers: [], pending: [], invoices: [], combo_usage: [], combo_purchases: [], combo_sale_requests: [], reports: [], audit: [], backups: [] }
    : undefined
  const candidate = {
    ...source,
    customers: [], pending_payments: [], pending: [], invoices: [], combo_usage: [], combo_purchases: [], combo_sale_requests: [], report_rows: [], reports: {},
    audit: [], history: [], backups: [], pending_changes: [], invoice_changes: [], customer_changes: [], pending_count: 0, combo_sale_request_count: 0,
    ...(state ? { state } : {}),
  }
  delete candidate.result
  const safeData = sanitizeLiveTourCacheValue(candidate)
  return { ...safeData, records: asArray(safeData.records) }
}

function saveCachedLiveTour(key, data) {
  try { window.sessionStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data: cacheSafeLiveTour(data) })) } catch { /* cache is optional */ }
}

function normalizedColumn(column) {
  return String(column || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').trim().toUpperCase()
}

function findColumn(columns, acceptedNames) {
  const wanted = new Set(acceptedNames)
  return columns.find((column) => wanted.has(normalizedColumn(column))) || ''
}

function cellValue(record, column) {
  return column ? String(record?.[column] ?? '').trim() : ''
}

function sttColumn(columns) {
  return findColumn(columns, ['STT', 'SO THU TU'])
}

function employeeNameColumn(columns) {
  return findColumn(columns, ['TEN NHAN VIEN', 'NHAN VIEN', 'HO VA TEN', 'HO TEN'])
}

function serviceNameColumn(columns) {
  return columns.find((column) => {
    const key = normalizedColumn(column)
    return key === 'DICH VU' || key.startsWith('DICH VU (')
  }) || ''
}

function validLiveTourRecord(record, columns) {
  return Boolean(cellValue(record, sttColumn(columns)) && cellValue(record, employeeNameColumn(columns)))
}

function stableEmployeeId(record) {
  return String(record?._employee_id ?? record?.employee_id ?? record?._id ?? record?.id ?? '').trim()
}

function recordId(record, index = 0) {
  return stableEmployeeId(record) || String(record?.username ?? `row-${index}`)
}

function columnClass(column) {
  const key = normalizedColumn(column)
  const centered = new Set([
    'TG CON LAI', 'CON LAI', 'YEU CAU', 'DI LAM', 'VAO CA', 'BREAKTIME', 'TG NGHI CON LAI',
    'GIO RA', 'GIO VAO', 'GHI CHU', 'THOI LUONG', 'TG BAT DAU THUC HIEN',
    'TG BAT DAU THUC HIEN YC', 'TT THANH TOAN', 'KET QUA HOAN THANH', 'SL TUA',
    'SL YEU CAU', 'TONG SL', 'VIP', 'GIO BOOKING', 'TG KHACH CHO', 'TG XONG HOI',
  ])
  if (key === 'STT' || key === 'SO THU TU') return 'tour-col-stt center'
  if (['TEN NHAN VIEN', 'NHAN VIEN', 'HO VA TEN', 'HO TEN'].includes(key)) return 'tour-col-employee'
  if (key === 'TRANG THAI') return 'tour-col-status center'
  if (key === 'DICH VU' || key.startsWith('DICH VU (')) return 'tour-col-service'
  if (key === 'TG CON LAI' || key === 'THOI GIAN CON LAI') return 'tour-col-remaining center'
  if (key === 'PHONG' || key.startsWith('PHONG (')) return 'tour-col-room center'
  if (key === 'YEU CAU' || key.startsWith('YEU CAU (')) return 'tour-col-request center'
  if (key.includes('LICH HEN')) return 'tour-col-appointment'
  return `tour-col-mobile-hidden${centered.has(key) ? ' center' : ''}`
}

function rowClass(record, selected, settings, clockMs = Date.now()) {
  const base = `tour-row-${record?._row_style || 'default'}`
  const waiting = Array.isArray(record?._tour_groups) && record._tour_groups.includes('waiting')
  return `${base}${waiting ? ' tour-row-waiting' : ''}${selected ? ' live-tour-selected' : ''}${isBeforeShiftReady(record, settings, clockMs) ? ' tour-row-before-shift' : ''}`
}

function isCurrentlyOnBreak(record) {
  return record?._attendance_break_active === true || record?.break_active === true
}

function hasGroup(record, key) {
  if (key === 'break') return isCurrentlyOnBreak(record)
  if (key === 'idle') return hasGroup(record, 'available') && !hasGroup(record, 'finishing')
  return Array.isArray(record?._tour_groups) && record._tour_groups.includes(key)
}

function groupCount(records, key) {
  return records.reduce((count, record) => count + (hasGroup(record, key) ? 1 : 0), 0)
}

function prioritizeRecords(records, columns, activeFilter) {
  if (records.some(record => record._manual_order)) return [...records].sort((a, b) => Number(hasGroup(a, 'leave')) - Number(hasGroup(b, 'leave')) || Number(a._sort_index || 0) - Number(b._sort_index || 0))
  const priorityGroup = activeFilter === 'finishing' ? 'available' : activeFilter
  const startedColumn = findColumn(columns, ['TG BAT DAU THUC HIEN', 'BAT DAU THUC HIEN'])
  return records.map((record, index) => ({ record, index })).sort((left, right) => {
    const leftLeave = hasGroup(left.record, 'leave')
    const rightLeave = hasGroup(right.record, 'leave')
    if (leftLeave !== rightLeave) return leftLeave ? 1 : -1
    const [leftRank, leftTime] = tourStartOrder(cellValue(left.record, startedColumn))
    const [rightRank, rightTime] = tourStartOrder(cellValue(right.record, startedColumn))
    if (leftRank !== rightRank) return leftRank - rightRank
    if (leftTime !== rightTime) return leftTime - rightTime
    const leftMatches = hasGroup(left.record, priorityGroup)
    const rightMatches = hasGroup(right.record, priorityGroup)
    if (leftMatches !== rightMatches) return leftMatches ? -1 : 1
    return left.index - right.index
  }).map(({ record }) => record)
}

function shiftBucket(record, columns) {
  const raw = cellValue(record, findColumn(columns, ['VAO CA', 'GIO VAO CA', 'THOI GIAN VAO CA']))
  if (!raw) return ''
  const normalized = normalizedColumn(raw).replace(/\s+/g, ' ')
  if (/(^|\s)CA\s*1(\s|$)/.test(normalized) || normalized === 'CA1') return 'ca1'
  if (/(^|\s)CA\s*2(\s|$)/.test(normalized) || normalized === 'CA2') return 'ca2'
  const match = raw.match(/(?:^|\s)(\d{1,2})\s*[:Hh]\s*(\d{2})?/)
  if (match && Number.isFinite(Number(match[1]))) return Number(match[1]) < 12 ? 'ca1' : 'ca2'
  const compact = normalized.replace(/\s+/g, '')
  if (['10', '10H', '10H00'].includes(compact)) return 'ca1'
  if (['12', '12H', '12H00', '14', '14H', '14H00'].includes(compact)) return 'ca2'
  return ''
}

function roomKey(value) {
  if (typeof value === 'object' && value?.area_id) return normalizedColumn(value.name)
  const raw = typeof value === 'object' && value ? value.code ?? value.name ?? value.room ?? value.id : value
  return normalizedColumn(raw).replace(/^PHONG\s*/, '').replace(/\s+/g, ' ').trim()
}

function roomValue(value) {
  if (typeof value === 'object' && value?.area_id) return String(value.name || '').trim()
  if (typeof value === 'object' && value) return String(value.code ?? value.name ?? value.room ?? value.id ?? '').replace(/^phòng\s*/i, '').trim()
  return String(value ?? '').replace(/^phòng\s*/i, '').trim()
}

function physicalRoomValue(value) {
  const explicitGroup = typeof value === 'object' && value
    ? value.group ?? value.room_group ?? value.physical_room ?? value.parent_room
    : ''
  const raw = roomValue(explicitGroup || value).replace(/^VIP\s*/i, '').trim()
  return raw.replace(/\.\d+$/, '')
}

function physicalRoomKey(value) {
  return normalizedColumn(physicalRoomValue(value)).replace(/^PHONG\s*/, '').replace(/\s+/g, ' ').trim()
}

function compareRooms(left, right) {
  return roomKey(left).localeCompare(roomKey(right), 'vi', { numeric: true, sensitivity: 'base' })
}

function isVipRoom(room) {
  return VIP_ROOM_KEYS.has(roomKey(room))
}

function roomLabel(room) {
  return isVipRoom(room) ? `VIP ${roomValue(room)}` : `Phòng ${roomValue(room)}`
}

function roomRecordPriority(record) {
  if (isCurrentlyOnBreak(record)) return 5
  if (hasGroup(record, 'doing')) return 4
  if (hasGroup(record, 'waiting')) return 3
  if (record?._countdown_deadline) return 2
  return 1
}

function pickRoomRecord(records, remainingColumn) {
  return [...records].sort((left, right) => {
    const priority = roomRecordPriority(right) - roomRecordPriority(left)
    if (priority) return priority
    const leftValue = Number(cellValue(left, remainingColumn))
    const rightValue = Number(cellValue(right, remainingColumn))
    return Number.isFinite(leftValue) && Number.isFinite(rightValue) ? leftValue - rightValue : 0
  })[0] || null
}

function roomState(record, available, clockMs) {
  if (!record) return available ? 'blank' : 'default'
  if (isCurrentlyOnBreak(record)) return 'break'
  if (hasGroup(record, 'waiting')) return 'waiting'
  const deadlineMs = record._countdown_deadline ? new Date(record._countdown_deadline).getTime() : NaN
  if (Number.isFinite(deadlineMs) && Math.ceil((deadlineMs - clockMs) / 1000) <= -15 * 60) return 'red'
  return ['green', 'yellow', 'red', 'break', 'idle', 'leave', 'work'].includes(record._row_style) ? record._row_style : 'default'
}

function durationText(seconds) {
  const totalMinutes = Math.max(0, Math.ceil(Math.abs(Number(seconds || 0)) / 60))
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours}:${`${minutes}`.padStart(2, '0')}`
}

function roomCountdown(record, remainingColumn, clockMs, available, occupied) {
  if (!record) return available ? 'Đang trống' : occupied ? 'Đang sử dụng' : 'Chưa có dữ liệu'
  const deadlineMs = record._countdown_deadline ? new Date(record._countdown_deadline).getTime() : NaN
  if (Number.isFinite(deadlineMs)) {
    const delta = Math.ceil((deadlineMs - clockMs) / 1000)
    if (delta <= -15 * 60) return 'Đã hết giờ'
    return delta >= 0 ? `Còn ${durationText(delta)}` : `Trễ ${durationText(-delta)}`
  }
  const remainingRaw = cellValue(record, remainingColumn)
  const remaining = remainingRaw === '' ? null : Number(remainingRaw)
  if (Number.isFinite(remaining)) return remaining >= 0 ? `Còn ${remaining} phút` : `Trễ ${Math.abs(remaining)} phút`
  if (hasGroup(record, 'waiting')) return 'Đang chờ'
  if (hasGroup(record, 'doing')) return 'Thực hiện'
  return 'Chưa có thời gian'
}

function isPrivateService(value) {
  const normalized = normalizedColumn(value).replace(/\s+/g, ' ')
  return /(^|[^A-Z0-9])PR(?=$|[^A-Z0-9])/.test(normalized) || /(^|[^A-Z0-9])P\s*\.?\s*RIENG(?=$|[^A-Z0-9])/.test(normalized)
}

function isRoomAssignmentActive(record) {
  if (record?._active_booking !== undefined) return Boolean(record._active_booking)
  return ['DANG CHO', 'DANG THUC HIEN'].includes(normalizedColumn(record?.['Trạng thái'] ?? record?.status))
}

function isQuickCheckoutEligible(record, columns) {
  if (!stableEmployeeId(record) || record?._hidden) return false
  if (record?._payment_pending === true) return true
  const status = normalizedColumn(cellValue(record, findColumn(columns, ['TRANG THAI'])))
  return status === 'CHO THANH TOAN'
}

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function itemId(item, index = 0) {
  return String(item?._id ?? item?.id ?? item?.code ?? item?.name ?? item?.customer_id ?? `item-${index}`)
}

function stableCustomerId(customer) {
  return String(customer?._id ?? customer?.id ?? customer?.customer_id ?? '').trim()
}

function customerComboPurchases(customer) {
  const purchases = asArray(customer?.combo_purchases)
  return purchases.length ? purchases : asArray(customer?.combos)
}

function itemLabel(item, fallback = 'Chưa đặt tên') {
  if (typeof item !== 'object' || !item) return String(item || fallback)
  return String(item.name ?? item.label ?? item.code ?? item.room ?? item.service_name ?? item.combo_name ?? item.customer_name ?? item.full_name ?? fallback)
}

function formatMoney(value) {
  const amount = Number(value)
  return Number.isFinite(amount) ? `${amount.toLocaleString('vi-VN')} đ` : String(value ?? '')
}

function catalogServiceMetric(services, serviceName, field, unknownValue) {
  const name = String(serviceName || '').trim()
  if (!name) return unknownValue
  const exact = services.find((item) => normalizedColumn(itemLabel(item)) === normalizedColumn(name))
  if (exact) {
    const value = Number(exact?.[field])
    return Number.isFinite(value) ? value : field === 'ticket_units' ? 1 : unknownValue
  }
  const parts = name.split(/\s*&\s*/).map((part) => part.trim()).filter(Boolean)
  if (parts.length <= 1) return field === 'ticket_units' ? 1 : unknownValue
  const values = parts.map((part) => catalogServiceMetric(services, part, field, unknownValue))
  return values.every((value) => Number.isFinite(value)) ? values.reduce((sum, value) => sum + value, 0) : unknownValue
}

function previewEntryPrice(entry, services) {
  const storedRaw = entry?.price ?? entry?.service_price
  const stored = Number(storedRaw)
  const source = String(entry?.price_source ?? entry?.service_price_source ?? '')
  const catalogPrice = catalogServiceMetric(services, entry?.service, 'price', null)
  const needsCatalog = source === 'tour_import' || storedRaw === null || storedRaw === undefined || storedRaw === '' || (!source && stored === 0)
  if (needsCatalog) return catalogPrice
  return Number.isFinite(stored) ? stored : catalogPrice
}

function previewEntryTicketUnits(entry, services) {
  return catalogServiceMetric(services, entry?.service, 'ticket_units', 1)
}

function newIdempotencyKey(action) {
  const suffix = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `live-tour:${action}:${suffix}`
}

function stableSerialize(value) {
  if (Array.isArray(value)) return `[${value.map(stableSerialize).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().filter((key) => value[key] !== undefined).map((key) => `${JSON.stringify(key)}:${stableSerialize(value[key])}`).join(',')}}`
  }
  if (value === undefined) return 'null'
  return JSON.stringify(value)
}

function requestSignature(action, payload) {
  return stableSerialize({ action, payload })
}

function signatureHash(value) {
  let first = 2166136261
  let second = 2246822519
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index)
    first = Math.imul(first ^ code, 16777619)
    second = Math.imul(second ^ code, 3266489917)
  }
  return `${(first >>> 0).toString(36)}-${(second >>> 0).toString(36)}-${value.length.toString(36)}`
}

function requestStorageKey(cacheKey, signature) {
  return `${cacheKey}:request:${signatureHash(signature)}`
}

function requestIdempotencyEntry(entries, cacheKey, action, payload, preferredKey = '') {
  const signature = requestSignature(action, payload)
  const existing = entries.get(signature)
  if (existing && !preferredKey) return existing
  const storageKey = requestStorageKey(cacheKey, signature)
  let key = preferredKey
  if (!key) {
    try { key = window.sessionStorage.getItem(storageKey) || '' } catch { /* session persistence is optional */ }
  }
  const entry = { key: key || newIdempotencyKey(action), signature, storageKey }
  entries.set(signature, entry)
  try { window.sessionStorage.setItem(storageKey, entry.key) } catch { /* in-memory retry still works */ }
  return entry
}

function releaseIdempotencyEntry(entries, entry) {
  entries.delete(entry.signature)
  try { window.sessionStorage.removeItem(entry.storageKey) } catch { /* ignore storage failures */ }
}

function liveTourErrorDetail(error) {
  const detail = error?.payload?.detail
  if (typeof detail === 'string') return detail
  return detail?.message || error?.payload?.message || error?.message || 'Không cập nhật được Live Tour.'
}

function isRevisionConflict(error) {
  if (error?.status !== 409) return false
  const detail = error?.payload?.detail
  const code = String(detail?.code || error?.payload?.code || error?.payload?.error_code || '').toLowerCase()
  if (['revision_conflict', 'live_tour_revision_conflict', 'stale_revision'].includes(code)) return true
  return /live tour đã thay đổi ở thiết bị khác[.!]? hãy làm mới rồi thao tác lại/i.test(String(typeof detail === 'string' ? detail : detail?.message || error?.message || ''))
}

const PAYMENT_ACTIONS = new Set(['checkout', 'quick_checkout', 'move_pending', 'combo_purchase'])
const ADMIN_ACTIONS = new Set([
  'room_upsert', 'room_delete', 'service_upsert', 'service_delete',
  'combo_upsert', 'combo_delete', 'combo_import', 'combo_sale_decide', 'backup', 'restore', 'clear_expired',
  'set_vip', 'payment_settings_update', 'clear_orphan_pending',
])

function canRunAction(action, capabilities) {
  if (['reorder', 'admin_reorder'].includes(action)) return capabilities.reorder
  if (action === 'update_appointment') return capabilities.appointmentEdit
  if (action === 'end_break') return capabilities.endBreak || capabilities.operate
  if (['booking', 'multi_booking'].includes(action)) return capabilities.booking
  if (action === 'customer_delete') return capabilities.customersDelete && capabilities.customers
  if (action === 'customer_combo_update') return capabilities.comboEdit && capabilities.customers
  if (action === 'customer_combo_delete') return capabilities.comboDelete && capabilities.customers
  if (action === 'pending_update') return capabilities.invoiceEdit
  if (action === 'pending_delete') return capabilities.invoiceDelete
  if (action === 'paid_invoice_update') return capabilities.paidInvoiceEdit
  if (action === 'paid_invoice_delete') return capabilities.paidInvoiceDelete
  if (['backup', 'restore'].includes(action)) return capabilities.backup
  if (action === 'customer_upsert') return capabilities.customersEdit && capabilities.customers
  if (action === 'combo_purchase') return capabilities.payment && capabilities.customers
  if (action === 'combo_import') return capabilities.comboImport && capabilities.customers
  if (ADMIN_ACTIONS.has(action)) return capabilities.admin
  if (action === 'set_shift' || action === 'restart_booking') return capabilities.isAdmin === true
  if (PAYMENT_ACTIONS.has(action)) return capabilities.payment
  return capabilities.operate
}

function LiveTourModal({ title, onClose, children, fitViewport = false, busy = false, className = '' }) {
  return fitViewport ? <LiveTourTransactionDialog title={title} onClose={onClose} busy={busy} className="tour-payment-dialog">{children}</LiveTourTransactionDialog>
    : <LiveTourLegacyModal title={title} onClose={onClose} className={className}>{children}</LiveTourLegacyModal>
}

function LiveTourLegacyModal({ title, onClose, children, className = '' }) {
  const dialogRef = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    const previousFocus = document.activeElement
    const dialog = dialogRef.current
    const focusableSelector = 'button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
    const focusable = () => [...(dialog?.querySelectorAll(focusableSelector) || [])]
    const frame = window.requestAnimationFrame(() => (dialog?.querySelector('[autofocus]') || focusable()[0] || dialog)?.focus())
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusable()
      if (!items.length) { event.preventDefault(); dialog?.focus(); return }
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      window.cancelAnimationFrame(frame)
      document.removeEventListener('keydown', onKeyDown)
      previousFocus?.focus?.()
    }
  }, [])

  return <div className="live-tour-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section data-ui-key="u-c98ae975f819" ref={dialogRef} tabIndex="-1" className={`live-tour-modal ${className}`.trim()} role="dialog" aria-modal="true" aria-label={title}>
      <div className="live-tour-modal-head"><strong>{title}</strong><button data-ui-key="u-766163924f5b" type="button" className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18}/></button></div>
      {children}
    </section>
  </div>
}

const EMPTY_FORM = {
  checkout_source: 'pending', service_id: '', booking_date: '', booking_time: '', booking_reason: '',
  target_employee_id: '', employee_id: '', employee_search: '', room: '', service: '', request: '', appointment: '', customer_id: '', customer_name: '', phone: '',
  discount: '0', discount_mode: 'amount', discount_percent: '0', tip: '0', tip_mode: 'manual', tip_card_ids: [], print_after: false, ticket_price: '', payment_method: 'TIỀN MẶT', bill_no: '', ticket_no: '',
  bank_selection: 'auto', pending_id: '', combo_purchase_id: '', note: '', name: '', shift: '', combo_id: '', quantity: '1', remaining: '', amount: '0', code: '', duration: '60', vip: false,
  backdate_one_day: false, correction_reason: '', requires_admin_approval: false,
  ticket_units: '1', private_service: false, request_eligible: true, non_request_eligible: true, request_duration: '',
}

export default function LiveTourPage({ user, navigationToggle = null }) {
  const cacheKey = liveTourCacheKey(user)
  const tipPreferenceKey = `${cacheKey}:tip-mode`
  const [data, setData] = useState(() => readCachedLiveTour(cacheKey))
  const initiallyCached = useRef(Boolean(data.records.length))
  const [busy, setBusy] = useState(false)
  const [actionBusy, setActionBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pendingReminder, setPendingReminder] = useState(null)
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [activeFilter, setActiveFilter] = useState('all')
  const [shiftFilter, setShiftFilter] = useState('all')
  const [employeeSearch, setEmployeeSearch] = useState('')
  const [employeePickId, setEmployeePickId] = useState('')
  const [roomSegment, setRoomSegment] = useState('all')
  const [customerContext, setCustomerContext] = useState(null)
  const [listFilters, setListFilters] = useState(() => ({ ...EMPTY_TOUR_FILTERS, preset: 'all' }))
  const [selectedRoomKey, setSelectedRoomKey] = useState('')
  const [roomFilterIds, setRoomFilterIds] = useState(() => new Set())
  const [clockMs, setClockMs] = useState(Date.now())
  const [activePanel, setActivePanel] = useState('pending')
  const [weeklyShiftOpen, setWeeklyShiftOpen] = useState(false)
  const [reorderSteps, setReorderSteps] = useState('1')
  const [targetPosition, setTargetPosition] = useState('')
  const [adminControlsVisible, setAdminControlsVisible] = useState(false)
  const [modal, setModal] = useState(null)
  const [bookingContext, setBookingContext] = useState(null)
  const [pendingContext, setPendingContext] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [expiredPreview, setExpiredPreview] = useState(null)
  const [expiredGrace, setExpiredGrace] = useState('15')
  const [customerSearch, setCustomerSearch] = useState('')
  const [comboLookupOpen, setComboLookupOpen] = useState(false)
  const [comboLookupSearch, setComboLookupSearch] = useState('')
  const [customerHistoryModal, setCustomerHistoryModal] = useState(null)
  const [customerHistoryBusy, setCustomerHistoryBusy] = useState(false)
  const [customerHistoryFilters, setCustomerHistoryFilters] = useState(() => ({ preset: 'month', ...tourDateRange('month') }))
  const [customColumns, setCustomColumns] = useState(null)
  const [customScope, setCustomScope] = useState('displayed')
  const [appearanceMobile, setAppearanceMobile] = useState(() => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 820px)').matches)
  const requestEntriesRef = useRef(new Map())
  const latestRevisionRef = useRef(data.revision)
  const pendingCountRef = useRef(0)
  const previousPendingCountRef = useRef(0)
  const pendingAnnouncementSequenceRef = useRef(0)
  const pendingReminderTimerRef = useRef(null)
  const workspaceRef = useRef(null)
  const isAdmin = String(user?.role || '').trim().toLowerCase() === 'admin'
  const normalizedRole = String(user?.role || '').trim().toLowerCase()
  const privilegedLiveTourRole = ['admin', 'quanly', 'letan'].includes(normalizedRole)
  const capabilities = data.capabilities && typeof data.capabilities === 'object' ? data.capabilities : {}
  const capability = (name, fallback) => Object.prototype.hasOwnProperty.call(capabilities, name) ? capabilities[name] === true : fallback
  const canEditAppointment = capability('appointment_edit', false)
  const canReorder = capability('reorder', isAdmin || user?.permissions?.live_tour_reorder === true)
  const canOperate = capability('operate', isAdmin || user?.permissions?.live_tour_operate === true)
  const canPayment = capability('payment', isAdmin || user?.permissions?.live_tour_payment === true)
  const canAdmin = capability('admin', isAdmin || user?.permissions?.live_tour_admin === true)
  const canExport = capability('export', isAdmin || user?.permissions?.live_tour_export === true)
  const canBook = capability('booking', isAdmin || user?.permissions?.live_tour_booking === true)
  const canInvoiceView = capability('invoice_view', isAdmin || user?.permissions?.live_tour_invoice_view === true)
  const canPaidInvoiceView = capability('paid_invoice_view', isAdmin || user?.permissions?.live_tour_paid_invoice_view === true)
  const canPaidInvoiceEdit = canPaidInvoiceView && capability('paid_invoice_edit', isAdmin || user?.permissions?.live_tour_paid_invoice_edit === true)
  const canPaidInvoiceDelete = canPaidInvoiceView && capability('paid_invoice_delete', isAdmin || user?.permissions?.live_tour_paid_invoice_delete === true)
  const canPending = capability('pending_view', isAdmin || user?.permissions?.live_tour_pending_view === true)
  const canInvoiceEdit = canPending && canInvoiceView && capability('invoice_edit', isAdmin || user?.permissions?.live_tour_invoice_edit === true)
  const canInvoiceDelete = canPending && canInvoiceView && capability('invoice_delete', isAdmin || user?.permissions?.live_tour_invoice_delete === true)
  const canCustomers = capability('customers_view', isAdmin || user?.permissions?.live_tour_customers_view === true)
  const canImportCombo = capability('combo_import', isAdmin || user?.permissions?.live_tour_combo_import === true) && canCustomers
  const canEndBreak = ['admin', 'quanly', 'letan'].includes(normalizedRole)
  const canViewComboPackages = ['admin', 'quanly', 'letan'].includes(normalizedRole) && canCustomers
  const canReports = capability('reports_view', isAdmin || user?.permissions?.live_tour_reports_view === true)
  const canHistory = capability('history_view', isAdmin || user?.permissions?.live_tour_history_view === true)
  const canBackup = capability('backup', isAdmin || user?.permissions?.live_tour_backup === true)
  const canManageCatalog = canAdmin || capabilities.catalog_admin === true || capabilities.manage_catalog === true
  const canExportKind = (kind) => hasLiveTourExportAccess(kind, { export: canExport, pending: canPending, invoiceView: canInvoiceView, paidInvoiceView: canPaidInvoiceView, customers: canCustomers, reports: canReports, history: canHistory })
  const loadPending = useRef(false)
  const actionBusyRef = useRef(actionBusy)
  useEffect(() => { actionBusyRef.current = actionBusy }, [actionBusy])
  const load = useCallback(async (refresh = false, quiet = false, conditional = false) => {
    // Polls must not consume another backend connection while a read is pending.
    if (quiet && loadPending.current) return
    // Explicit reloads wait for the previous read, then fetch fresh state.
    while (loadPending.current) await new Promise((resolve) => setTimeout(resolve, 100))
    loadPending.current = true
    if (!quiet) { setBusy(true); setError('') }
    try {
      const response = await veraApi.liveTour(refresh, false, conditional ? latestRevisionRef.current : null)
      if (response?.unchanged) {
        setError('')
        return
      }
      const next = { ...EMPTY_LIVE_TOUR, ...response }
      latestRevisionRef.current = next.revision
      setData(next)
      setError('')
      saveCachedLiveTour(cacheKey, next)
      setSelectedIds((current) => {
        const valid = new Set(asArray(next.records).map((record, index) => recordId(record, index)))
        return new Set([...current].filter((id) => valid.has(id)))
      })
    } catch (err) {
      setData((current) => cacheSafeLiveTour(current))
      if (err.status === 403) { setModal(null); setBookingContext(null); setPendingContext(null); setReceipt(null); setCustomerHistoryModal(null) }
      setError(err.message || 'Không tải được Live Tour.')
    } finally {
      loadPending.current = false
      if (!quiet) setBusy(false)
    }
  }, [cacheKey])

  useEffect(() => {
    // This lifecycle deliberately depends only on `load`. Previously every
    // dialog open/close and action-busy transition recreated it and triggered
    // another full, projecting load immediately after an operator action.
    void load(false, initiallyCached.current)
    const poll = () => { if (!actionBusyRef.current) void load(false, true, true) }
    const interval = startLiveTourPolling(poll)
    const onVisibilityChange = () => { if (document.visibilityState === 'visible') poll() }
    document.addEventListener('visibilitychange', onVisibilityChange)
    const stopWatching = watchLeaveChanges(() => { if (!actionBusyRef.current) void load(false, true) })
    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      stopWatching()
    }
  }, [load])

  useEffect(() => {
    const interval = startLiveTourClock(setClockMs)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const media = window.matchMedia('(max-width: 820px)')
    const sync = () => setAppearanceMobile(media.matches)
    sync()
    media.addEventListener?.('change', sync)
    return () => media.removeEventListener?.('change', sync)
  }, [])

  useEffect(() => {
    const allowed = {
      pending: canPending,
      invoices: canPaidInvoiceView,
      customers: canCustomers,
      reports: canReports,
      history: canHistory || canBackup,
      catalog: canAdmin,
    }
    if (allowed[activePanel]) return
    const fallback = PANEL_TABS.map(([key]) => key).find((panel) => allowed[panel]) || ''
    setActivePanel(fallback)
  }, [activePanel, canAdmin, canPending, canPaidInvoiceView, canCustomers, canReports, canHistory, canBackup])

  const executeAction = useCallback(async (action, payload = {}, ids = [...selectedIds], options = {}) => {
    if (actionBusy) return null
    if (data.revision === null || data.revision === undefined) {
      setError('Hãy tải Live Tour thành công trước khi thực hiện thao tác.')
      return null
    }
    if (!canRunAction(action, { endBreak: canEndBreak, reorder: canReorder, appointmentEdit: canEditAppointment, operate: canOperate, payment: canPayment, admin: canAdmin, isAdmin, customersEdit: capabilities.customers_edit, customersDelete: capabilities.customers_delete, comboEdit: capabilities.customer_combo_edit, comboDelete: capabilities.customer_combo_delete, booking: canBook, invoiceEdit: canInvoiceEdit, invoiceDelete: canInvoiceDelete, paidInvoiceEdit: canPaidInvoiceEdit, paidInvoiceDelete: canPaidInvoiceDelete, backup: canBackup, customers: canCustomers, comboImport: canImportCombo })) {
      setError('Tài khoản chưa được cấp quyền thực hiện thao tác này trên Live Tour.')
      return null
    }
    setActionBusy(action)
    setError('')
    setNotice('')
    const rowIds = ids.filter(Boolean)
    const actionPayload = { ...payload }
    if (rowIds.length) {
      actionPayload.employee_ids = rowIds
      if (rowIds.length === 1) actionPayload.employee_id = rowIds[0]
    }
    const requestEntry = requestIdempotencyEntry(requestEntriesRef.current, cacheKey, action, actionPayload, options.idempotencyKey)
    try {
      const body = { action, payload: actionPayload, idempotency_key: requestEntry.key }
      if (data.revision !== null && data.revision !== undefined) body.expected_revision = options.expectedRevision ?? data.revision
      if (rowIds.length) body.row_ids = rowIds
      if (rowIds.length === 1) body.row_id = rowIds[0]
      const result = await veraApi.liveTourAction(body)
      releaseIdempotencyEntry(requestEntriesRef.current, requestEntry)
      if (Array.isArray(result?.records) && Array.isArray(result?.columns)) {
        const next = { ...EMPTY_LIVE_TOUR, ...result }
        latestRevisionRef.current = next.revision
        setData(next)
        saveCachedLiveTour(cacheKey, next)
      } else {
        await load(true, true)
      }
      setSelectedIds(new Set())
      setNotice(result?.message === 'Đã cập nhật Live Tour.' ? '' : result?.message || '')
      return result
    } catch (err) {
      const message = liveTourErrorDetail(err)
      if (isRevisionConflict(err)) {
        setSelectedIds(new Set())
        await load(true, true)
        setError(message)
        setNotice(`${message} Dữ liệu mới nhất đã được tải lại; bạn có thể thử lại thao tác.`)
      } else {
        setError(message)
      }
      return null
    } finally {
      setActionBusy('')
    }
  }, [capabilities.customers_edit, capabilities.customers_delete, capabilities.customer_combo_edit, capabilities.customer_combo_delete, actionBusy, cacheKey, canAdmin, canReorder, isAdmin, canEndBreak, canEditAppointment, canOperate, canPayment, canBook, canInvoiceEdit, canInvoiceDelete, canPaidInvoiceEdit, canPaidInvoiceDelete, canBackup, canCustomers, canImportCombo, data.revision, load, selectedIds])

  const previewExpired = async () => {
    if (!canAdmin || actionBusy || data.revision == null) return
    setActionBusy('clear_expired_preview')
    setExpiredPreview(null)
    setError('')
    try {
      setExpiredPreview(await veraApi.liveTourAction({ action: 'clear_expired_preview', expected_revision: data.revision, payload: { grace_minutes: expiredGrace } }))
    } catch (err) {
      setError(liveTourErrorDetail(err))
    } finally { setActionBusy('') }
  }

  const confirmExpired = async () => {
    if (!canAdmin || !expiredPreview || actionBusy || expiredPreview.base_revision !== data.revision) return
    const result = await executeAction('clear_expired', { grace_minutes: expiredPreview.grace_minutes, confirm_token: expiredPreview.preview_token }, [])
    setExpiredPreview(null)
    if (result) setNotice(`Đã chuyển ${result.result?.marked_for_payment ?? expiredPreview.count} phiên sang chờ thanh toán.`)
  }

  const runSelected = (action, payload = {}) => {
    if (!selectedIds.size) {
      setNotice('Hãy chọn ít nhất một nhân viên trong bảng.')
      return Promise.resolve(null)
    }
    return executeAction(action, payload)
  }

  const cancelSelectedBooking = () => {
    const chosen = validRecords.filter((item) => selectedIds.has(stableEmployeeId(item)))
    if (!chosen.length || chosen.length !== selectedIds.size || chosen.some((item) => !hasGroup(item, 'waiting'))) {
      setError('Chỉ hủy Booking đang chờ. Hãy chọn nhân viên có Booking chưa thực hiện.')
      return
    }
    if (window.confirm(`Hủy Booking của ${chosen.map((item) => cellValue(item, employeeColumn)).join(', ')}?`)) {
      void runSelected('cancel_booking')
    }
  }

  const runSingleSelected = (action, payload = {}) => {
    if (selectedIds.size !== 1) {
      setNotice('Thao tác sắp xếp yêu cầu chọn đúng một nhân viên.')
      return Promise.resolve(null)
    }
    return executeAction(action, payload)
  }

  const openLiveTourInNewTab = () => {
    const url = new URL(window.location.href)
    url.searchParams.set('page', 'live-tour')
    url.searchParams.set('standalone', '1')
    window.open(url.toString(), '_blank', 'noopener,noreferrer')
  }

  const openModal = (kind, context = {}) => {
    if (kind === 'combo_import' && !canImportCombo) {
      setError('Tài khoản chưa được cấp quyền Nhập combo khách hàng.')
      return
    }
    if (kind === 'change_employee' && (data.payment_settings?.employee_change_enabled === false || context.rowIds?.length !== 1 || !canChangeEmployee(validRecords.find((row) => stableEmployeeId(row) === context.rowIds[0]), clockMs))) {
      setError('Chỉ đổi nhân viên đang thực hiện trong thời hạn đổi nhân viên đã cài đặt.'); return
    }
    const capturedRowIds = context.rowIds ?? (['checkout', 'quick_checkout'].includes(kind) ? [...selectedIds] : undefined)
    const capturedEmployees = capturedRowIds?.length
      ? [...asArray(data.state?.employees), ...asArray(data.retained_assignments)].filter((employee) => capturedRowIds.includes(stableEmployeeId(employee)))
      : []
    if (kind === 'checkout' && !(context.item?.entries || capturedEmployees).some((entry) => entry?.service || entry?.service_items?.length)) {
      setError('Không tìm thấy dịch vụ để thanh toán. Hãy làm mới Bảng tua hoặc chọn hóa đơn trong Chờ thanh toán.')
      return
    }
    const capturedCustomerIds = new Set(capturedEmployees.map((employee) => String(employee?.customer_id || '')).filter(Boolean))
    const capturedCustomer = capturedCustomerIds.size <= 1
      ? capturedEmployees.find((employee) => employee?.customer_id) || capturedEmployees[0]
      : null
    const source = context.item || capturedCustomer || {}
    const capturedComboIds = new Set(capturedEmployees.map((employee) => employee.combo_purchase_id || ''))
    const sourceComboId = context.item ? source.combo_purchase_id || '' : capturedComboIds.size === 1 ? [...capturedComboIds][0] : ''
    const sourceIsCapturedEmployee = !context.item && Boolean(capturedCustomer)
    setError('')
    setForm({
      ...EMPTY_FORM,
      print_after: data.payment_settings?.auto_print === true,
      tip_mode: defaultTipMode(tipPreferenceKey),
      booking_date: '', booking_time: bookingDateTime().time,
      ...context.defaults,
      room: source.room ?? (kind === 'room_upsert' ? source.name : source.code) ?? context.defaults?.room ?? '',
      service: source.service ?? source.name ?? context.defaults?.service ?? '',
      customer_id: source.customer_id ?? context.defaults?.customer_id ?? '',
      customer_name: source.customer_name ?? context.defaults?.customer_name ?? '',
      phone: (sourceIsCapturedEmployee ? source.customer_phone : source.customer_phone ?? source.phone) ?? context.defaults?.phone ?? '',
      combo_id: source.combo_id ?? context.defaults?.combo_id ?? '',
      code: source.code ?? (kind === 'room_upsert' ? source.name : '') ?? context.defaults?.code ?? '',
      duration: String(source.duration ?? source.minutes ?? context.defaults?.duration ?? '60'),
      ticket_units: String(source.ticket_units ?? '1'), private_service: Boolean(source.private ?? isPrivateService(source.name)),
      request_eligible: source.request_eligible !== false, non_request_eligible: source.non_request_eligible !== false,
      request_duration: String(source.request_duration ?? ''),
      remaining: String(source.remaining ?? source.balance ?? context.defaults?.remaining ?? ''),
      pending_id: source.pending_id ?? (['checkout', 'quick_checkout'].includes(kind) && context.item ? context.item?._id ?? context.item?.id : '') ?? context.defaults?.pending_id ?? '',
      combo_purchase_id: sourceComboId || context.defaults?.combo_purchase_id || '',
      payment_method: sourceComboId ? 'COMBO' : context.defaults?.payment_method || EMPTY_FORM.payment_method,
      amount: kind === 'combo_purchase' ? '' : String(source.amount ?? source.price ?? context.defaults?.amount ?? '0'),
      quantity: String(source.quantity ?? source.tickets ?? context.defaults?.quantity ?? '1'),
      vip: Boolean(source.is_vip ?? (source.type ? normalizedColumn(source.type) === 'VIP' : context.defaults?.vip)),
      requires_admin_approval: source.requires_admin_approval === true,
    })
    setModal({ kind, ...context, ...(capturedRowIds !== undefined ? { rowIds: capturedRowIds } : {}) })
  }

  const closeModal = () => { if (!actionBusy) setModal(null) }

  const submitModal = async (event) => {
    event.preventDefault()
    if (!modal) return
    if (modal.kind === 'combo_approvals') return
    if (modal.kind === 'quick_checkout' && !manualQuickBooking && !form.pending_id && !selectedQuickCheckoutRecord) {
      setError('Hãy tìm và chọn đúng một nhân viên đang chờ thanh toán.')
      return
    }
    const modalIds = manualQuickBooking || form.pending_id ? [] : modal.kind === 'quick_checkout'
      ? [stableEmployeeId(selectedQuickCheckoutRecord)]
      : modal.rowIds || [...selectedIds]
    let action = modal.kind
    let payload = modal.kind === 'change_employee' ? { target_employee_id: form.target_employee_id } : { ...form }
    if (modal.kind === 'change_employee' && !form.target_employee_id) { setError('Hãy chọn nhân viên thay thế.'); return }
    if (['checkout', 'quick_checkout'].includes(modal.kind)) {
      if (manualQuickBooking && (!canBook || (!quickSteam && (!form.employee_id || !form.room)) || (!form.service_id && !form.combo_purchase_id) || !form.booking_date || !form.booking_time)) {
        setError('Hãy chọn nhân viên, phòng, dịch vụ và ngày giờ booking.'); return
      }
      if (manualQuickBooking && form.booking_date < vietnamDate(clockMs) && (!canAdmin || form.booking_reason.trim().length < 3)) {
        setError('Nhập booking trước hôm nay cần quyền Admin và lý do điều chỉnh.'); return
      }
      const paymentMethod = form.combo_purchase_id ? 'COMBO' : form.payment_method === 'COMBO' ? 'TIỀN MẶT' : form.payment_method
      const ticketPrice = Number(form.ticket_price)
      if (!form.combo_purchase_id && checkoutHasUnresolvedPricing) {
        setError('Có dịch vụ chưa khớp danh mục giá. Hãy sửa dịch vụ hoặc cấu hình giá trước khi thanh toán.')
        return
      }
      if (!form.combo_purchase_id && checkoutHasMixedPricing) {
        setError('Không thể thanh toán chung dịch vụ đã có giá với dịch vụ giá 0. Hãy cấu hình giá hoặc tách lần thanh toán.')
        return
      }
      if (checkoutRequiresTicketPrice && (!Number.isFinite(ticketPrice) || ticketPrice <= 0 || ticketPrice > 1_000_000_000)) {
        setError('Giá vé phải lớn hơn 0 và không vượt quá 1.000.000.000 đ khi dịch vụ chưa có giá danh mục.')
        return
      }
      payload = {
        pending_id: form.pending_id || null,
        ...(manualQuickBooking ? { quick_booking: { employee_id: quickSteam ? '' : form.employee_id, room: quickSteam ? '' : form.room,
          service_items: quickServiceItems,
          booked_at: `${form.booking_date}T${form.booking_time}:00+07:00`,
          correction_reason: form.booking_reason.trim() } } : {}),
        ...(canCustomers ? { customer_id: form.customer_id || null, customer_name: form.customer_name, customer_phone: form.phone } : {}),
        payment_method: paymentMethod, bill_no: form.bill_no, bank_selection: form.bank_selection || 'auto',
        ticket_no: form.ticket_no, discount: form.combo_purchase_id ? 0 : Number(form.discount || 0),
        discount_mode: form.discount_mode, discount_percent: form.combo_purchase_id ? 0 : Number(form.discount_percent || 0),
        tip: form.tip_mode === 'cards' ? 0 : Number(form.tip || 0), tip_card_ids: form.tip_mode === 'cards' ? form.tip_card_ids : [],
        combo_purchase_id: form.combo_purchase_id || null,
        ...(checkoutRequiresTicketPrice ? { ticket_price: ticketPrice } : {}),
        note: form.note,
      }

    } else if (['replace_service', 'add_service'].includes(modal.kind)) {
      payload = { service: form.service, note: form.note }
    } else if (modal.kind === 'combo_purchase') {
      payload = {
        customer_id: form.customer_id, customer_name: form.customer_name, customer_phone: form.phone,
        combo_id: form.combo_id, quantity: Number(form.quantity || 1), payment_method: form.payment_method,
        bill_no: form.bill_no, note: form.note,
      }
    } else if (modal.kind === 'combo_import') {
      payload = { purchases: [{ customer_id: form.customer_id || null, customer_name: form.customer_name, customer_phone: form.phone, combo_id: form.combo_id, total: Number(form.remaining || 0), used: 0, component_remaining: form.component_remaining, note: form.note }] }
    } else if (modal.kind === 'room_upsert') {
      payload = { id: modal.item?._id ?? modal.item?.id, name: form.room || form.code }
    } else if (modal.kind === 'service_upsert') {
      payload = { id: modal.item?._id ?? modal.item?.id, name: form.service, duration: form.duration === '' ? null : Number(form.duration), price: Number(form.amount || 0),
        ticket_units: Number(form.ticket_units), private: form.private_service, request_eligible: form.request_eligible,
        non_request_eligible: form.non_request_eligible, request_duration: form.request_duration === '' ? null : Number(form.request_duration) }
    } else if (modal.kind === 'combo_upsert') {
      payload = { id: modal.item?._id ?? modal.item?.id, name: form.service, tickets: Number(form.quantity || 1), price: Number(form.amount || 0), requires_admin_approval: form.requires_admin_approval === true }
    }
    if (action === 'combo_purchase' && form.backdate_one_day) {
      const correctionReason = form.correction_reason.trim()
      if (!canAdmin) {
        setError('Chỉ Admin được phép ghi nhận giao dịch lùi một ngày.')
        return
      }
      if (correctionReason.length < 3) {
        setError('Hãy nhập lý do điều chỉnh khi lùi ngày giao dịch.')
        return
      }
      payload.backdate_one_day = true
      payload.correction_reason = correctionReason
    }
    const result = await executeAction(action, payload, modalIds, modal.kind === 'change_employee' ? { expectedRevision: modal.revision } : {})
    if (result) {
      if (['checkout', 'quick_checkout'].includes(modal.kind) && result.result?.invoice && (data.payment_settings?.open_receipt !== false || form.print_after)) setReceipt({ invoice: result.result.invoice, autoPrint: form.print_after })
      setModal(null)
    }
  }

  const columns = useMemo(() => {
    const source = asArray(data.columns)
    const appointment = findColumn(source, ['LICH HEN'])
    if (!appointment) return source
    const ordered = source.filter((column) => column !== appointment)
    ordered.splice(ordered.indexOf(employeeNameColumn(source)) + 1, 0, appointment)
    return ordered
  }, [data.columns])
  const appearanceSettings = useMemo(() => mergeLiveTourAppearance(data.appearance_settings || {}), [data.appearance_settings])
  const activeAppearance = appearanceSettings[appearanceMobile ? 'mobile' : 'desktop']
  const appearanceTableColumns = useMemo(() => buildLiveTourTableLayout(columns, activeAppearance, canOperate), [activeAppearance, canOperate, columns])
  const appearanceCss = useMemo(() => buildLiveTourAppearanceCss(activeAppearance), [activeAppearance])
  const validRecords = useMemo(() => asArray(data.records).filter((record) => validLiveTourRecord(record, columns)), [columns, data.records])
  const shiftRecords = useMemo(() => validRecords.filter((record) => shiftFilter === 'all' || shiftBucket(record, columns) === shiftFilter), [columns, shiftFilter, validRecords])
  const searchedRecords = useMemo(() => {
    const roomFiltered = roomFilterIds.size ? shiftRecords.filter((record) => roomFilterIds.has(stableEmployeeId(record))) : shiftRecords
    if (employeePickId) return roomFiltered.filter((record) => stableEmployeeId(record) === employeePickId)
    const needle = normalizedColumn(employeeSearch)
    const employeeColumn = employeeNameColumn(columns)
    return needle ? roomFiltered.filter((record) => searchTextMatches(cellValue(record, employeeColumn), needle)) : roomFiltered
  }, [columns, employeePickId, employeeSearch, roomFilterIds, shiftRecords])
  const displayedRecords = useMemo(() => {
    const filterKey = activeFilter === 'staff' ? 'all' : activeFilter
    const filtered = filterKey === 'all' ? searchedRecords : searchedRecords.filter((record) => hasGroup(record, filterKey))
    return prioritizeRecords(filtered, columns, filterKey)
  }, [activeFilter, columns, searchedRecords])



  const roomColumn = findColumn(columns, ['PHONG'])
  const employeeColumn = employeeNameColumn(columns)
  const appointmentColumn = findColumn(columns, ['LICH HEN'])
  const exactAppointmentMatches = employeeSearch.trim() ? searchedRecords.filter((record) => normalizedColumn(cellValue(record, employeeColumn)) === normalizedColumn(employeeSearch)) : []
  const selectedAppointmentMatches = searchedRecords.filter((record) => selectedIds.has(stableEmployeeId(record)))
  const appointmentTarget = employeePickId ? searchedRecords.find((record) => stableEmployeeId(record) === employeePickId) || null
    : exactAppointmentMatches.length === 1 ? exactAppointmentMatches[0]
    : employeeSearch.trim() && searchedRecords.length === 1 ? searchedRecords[0]
      : selectedAppointmentMatches.length === 1 ? selectedAppointmentMatches[0] : null
  const appointmentEditor = (record, quick = false) => <LiveTourAppointmentInput
    key={stableEmployeeId(record) || 'no-employee'} quick={quick}
    value={record ? cellValue(record, appointmentColumn) : ''}
    employeeName={record ? cellValue(record, employeeColumn) : ''}
    revision={data.revision} busy={Boolean(actionBusy)} disabled={!record || !canEditAppointment}
    onSave={(appointment, expectedRevision) => executeAction('update_appointment', { appointment }, [stableEmployeeId(record)], { expectedRevision })}/>
  const serviceColumn = serviceNameColumn(columns)
  const statusColumn = findColumn(columns, ['TRANG THAI'])
  const remainingColumn = findColumn(columns, ['TG CON LAI', 'THOI GIAN CON LAI'])
  const requestColumn = findColumn(columns, ['YEU CAU'])
  const openEmployeeBooking = (record) => {
    const name = cellValue(record, employeeColumn) || 'Nhân viên'
    setError('')
    if (!['CA 1', 'CA 2'].includes(normalizedColumn(cellValue(record, findColumn(columns, ['VAO CA']))))) {
      setNotice(`${name} chưa vào ca, không thể đặt Booking.`)
      return
    }
    if (hasGroup(record, 'leave')) {
      setNotice(`${name} đang nghỉ phép, không thể đặt Booking.`)
      return
    }
    if (isCurrentlyOnBreak(record)) {
      setNotice(`${name} đang nghỉ giữa ca, chưa thể đặt Booking.`)
      return
    }
    setNotice('')
    setModal(null)
    setBookingContext({ employeeId: stableEmployeeId(record) })
  }
  const manualQuickBooking = modal?.kind === 'quick_checkout' && form.checkout_source === 'manual'
  const selectedQuickCheckoutRecord = validRecords.find((record) => stableEmployeeId(record) === form.employee_id && isQuickCheckoutEligible(record, columns)) || null
  const areaGroups = useMemo(() => new Map(Object.entries(data.room_groups || {}).map(([name, group]) => [normalizedColumn(name), group])), [data.room_groups])
  const areaKey = useCallback((value) => {
    const group = typeof value === 'object' && value ? value.area_name ?? value.group ?? roomValue(value) : value
    return data.service_areas ? normalizedColumn(group).replace(/\s+/g, ' ').trim() : physicalRoomKey(value)
  }, [data.service_areas])
  const assignmentAreaKey = useCallback((value) => areaGroups.has(normalizedColumn(value)) ? areaKey(areaGroups.get(normalizedColumn(value))) : physicalRoomKey(value), [areaGroups, areaKey])
  const areaKind = (value) => asArray(data.service_areas).find((item) => areaKey(item.name) === areaKey(value))?.kind || 'room'
  const isVipArea = (value) => areaKind(value) === 'room' && isVipRoom(value)
  const areaLabel = (value) => {
    const area = asArray(data.service_areas).find((item) => areaKey(item.name) === areaKey(value))
    if (area?.kind === 'bed') return /^giường\s/i.test(area.name) ? area.name : `Giường ${area.name}`
    if (area?.kind === 'table') return /^bàn\s/i.test(area.name) ? area.name : `Bàn ${area.name}`
    if (area?.kind === 'room') return /^(phòng|vip)\s/i.test(area.name) ? area.name : roomLabel(area.name)
    return roomLabel(value)
  }
  const roomRecords = useMemo(() => {
    const grouped = new Map()
    validRecords.forEach((record) => {
      if (!isRoomAssignmentActive(record)) return
      const key = assignmentAreaKey(cellValue(record, roomColumn))
      if (key) grouped.set(key, [...(grouped.get(key) || []), record])
    })
    return grouped
  }, [assignmentAreaKey, roomColumn, validRecords])
  const availableRooms = useMemo(() => asArray(data.available_rooms), [data.available_rooms])
  const catalogRooms = asArray(data.catalogs?.rooms).length ? asArray(data.catalogs.rooms) : asArray(data.state?.rooms)
  const rawRooms = useMemo(() => asArray(data.catalogs?.rooms).length ? asArray(data.catalogs.rooms) : asArray(data.state?.rooms).length ? asArray(data.state.rooms) : Array.isArray(data.rooms) ? data.rooms : asArray(data.rooms?.all), [data.catalogs?.rooms, data.rooms, data.state?.rooms])
  const serverRoomGroups = useMemo(() => asArray(data.rooms?.all), [data.rooms])
  const roomCatalog = useMemo(() => {
    const fallbackGroups = [...rawRooms, ...validRecords.map((record) => cellValue(record, roomColumn))]
    const groupSource = data.service_areas || serverRoomGroups.length ? serverRoomGroups : fallbackGroups
    const unique = new Map(groupSource.map((room) => data.service_areas ? [areaKey(room), String(room)] : [physicalRoomKey(room), physicalRoomValue(room)]))
    if (!data.service_areas) VIP_ROOMS.forEach((room) => unique.set(room, room))
    return [...unique.values()].sort(compareRooms)
  }, [areaKey, data.service_areas, rawRooms, roomColumn, serverRoomGroups, validRecords])
  const standardRooms = roomCatalog.filter((room) => !isVipArea(room))
  const vipRooms = roomCatalog.filter(isVipArea)
  const displayedRooms = roomSegment === 'vip' ? vipRooms : roomSegment === 'standard' ? standardRooms : roomCatalog
  const availableRoomKeys = new Set(availableRooms.map(areaKey))
  const availableRoomCount = displayedRooms.filter((room) => availableRoomKeys.has(areaKey(room))).length
  const occupiedRoomKeys = new Set(asArray(data.rooms?.occupied).map(areaKey))
  const selectedRoom = roomCatalog.find((room) => areaKey(room) === selectedRoomKey) || ''
  const selectedRoomRecords = selectedRoomKey ? roomRecords.get(selectedRoomKey) || [] : []
  const roomActionCounts = new Map(Object.entries(data.room_action_counts || {}).map(([room, counts]) => [areaKey(room), counts]))
  const runRoomAction = async (room, action) => {
    const roomName = typeof room === 'object' && room ? room.area_name ?? room.name : String(room)
    const result = await executeAction(action, { room: roomName }, [])
    if (result) {
      setSelectedRoomKey(areaKey(room))
      setNotice(`${action === 'start_room' ? 'Đã bắt đầu' : 'Đã hoàn thành và chuyển sang chờ thanh toán'} ${result.result?.count || 0} nhân viên · ${areaLabel(room)}.`)
    }
  }
  const roomServiceActions = (room) => {
    const counts = roomActionCounts.get(areaKey(room)) || {}
    return canOperate && <LiveTourServiceActions room target={areaLabel(room)} waiting={counts.waiting} doing={counts.doing} busy={Boolean(actionBusy)} onStart={() => runRoomAction(room, 'start_room')} onFinish={() => runRoomAction(room, 'finish_room')}/>
  }
  const employeeServiceActions = (record) => canOperate && <LiveTourServiceActions target={cellValue(record, employeeColumn)} canStart={!hasGroup(record, 'leave') && ['CA 1', 'CA 2'].includes(normalizedColumn(cellValue(record, findColumn(columns, ['VAO CA']))))} waiting={hasGroup(record, 'waiting') && !hasGroup(record, 'doing') ? 1 : 0} doing={hasGroup(record, 'doing') ? 1 : 0} busy={Boolean(actionBusy) || !stableEmployeeId(record)} onStart={() => executeAction('start', {}, [stableEmployeeId(record)])} onFinish={() => executeAction('finish_to_pending', {}, [stableEmployeeId(record)])}/>
  const searchedRoomKeys = useMemo(() => {
    const needle = normalizedColumn(employeeSearch)
    return new Set(needle ? shiftRecords.flatMap((record) => searchTextMatches(cellValue(record, employeeColumn), needle) ? [assignmentAreaKey(cellValue(record, roomColumn))] : []).filter(Boolean) : [])
  }, [assignmentAreaKey, employeeColumn, employeeSearch, roomColumn, shiftRecords])

  const retainedMetric = data.metric_snapshots?.[shiftFilter] || null
  const totalQuantityColumn = findColumn(columns, ['TONG SL'])
  const customerCount = retainedMetric?.customer_count ?? (
    shiftRecords.reduce((total, record) => total + (Number(record[totalQuantityColumn]) || 0), 0) + groupCount(shiftRecords, 'waiting')
  )
  const breakTotal = retainedMetric?.break_total_count ?? retainedMetric?.break_count ?? groupCount(shiftRecords, 'break')
  const breakActive = retainedMetric?.break_active_count ?? groupCount(shiftRecords, 'break')
  const employeeCount = new Set(shiftRecords.map((record, index) => recordId(record, index))).size
  const metrics = [
    { key: 'all', label: 'Tất cả', value: employeeCount, className: 'tour-all-metric' },
    { key: 'available', label: 'Có thể lên tua', value: groupCount(shiftRecords, 'available'), className: 'tour-available-metric' },
    { key: 'idle', label: 'Đang rảnh', value: groupCount(shiftRecords, 'idle'), className: 'tour-idle-metric' },
    { key: 'finishing', label: 'Sắp xong', value: groupCount(shiftRecords, 'finishing'), className: 'tour-finishing-metric' },
    { key: 'waiting', label: 'Đang chờ', value: groupCount(shiftRecords, 'waiting'), className: 'tour-waiting-metric' },
    { key: 'doing', label: 'Thực hiện', value: groupCount(shiftRecords, 'doing'), className: 'tour-doing-metric' },
    { key: 'staff', label: 'Số nhân viên', value: employeeCount, className: 'tour-staff-metric' },
    { key: 'leave', label: 'Nghỉ phép', value: groupCount(shiftRecords, 'leave'), className: 'tour-leave-metric' },
    { key: 'working', label: 'Đi làm', value: groupCount(shiftRecords, 'working'), className: 'tour-working-metric' },
    { key: 'break', label: 'Nghỉ giữa Ca', value: `${breakTotal}-${breakActive}`, className: 'tour-break-metric' },
  ]
  const weeklyShiftPlan = useMemo(() => {
    const rows = validRecords.map(record => ({
      id: stableEmployeeId(record),
      name: cellValue(record, employeeColumn),
      current: record._scheduled_week_shift || cellValue(record, findColumn(columns, ['VAO CA'])) || 'Chưa xếp',
      next: record._scheduled_next_shift || record._scheduled_week_shift || 'Chưa xếp',
      cycle: record._rotation_cycle || '',
      fixed: normalizedColumn(record._rotation_cycle || '').includes('CO DINH') || normalizedColumn(record._rotation_cycle || '').includes('KHONG DOI'),
    })).filter(row => row.name)
    const start = new Date(clockMs); start.setHours(0,0,0,0); start.setDate(start.getDate() - ((start.getDay() + 6) % 7))
    const finish = new Date(start); finish.setDate(start.getDate() + 6)
    const fmt = value => String(value.getDate()).padStart(2,'0') + '/' + String(value.getMonth()+1).padStart(2,'0')
    return { rows, range: fmt(start) + '–' + fmt(finish) }
  }, [clockMs, columns, employeeColumn, validRecords])
  const selectedWeeklyRows = weeklyShiftPlan.rows.filter(row => selectedIds.has(row.id))
  const selectedWeeklyShift = selectedWeeklyRows.length === 1 && ['Ca 1', 'Ca 2'].includes(selectedWeeklyRows[0].current)
    ? selectedWeeklyRows[0].current
    : ''

  const chooseFilter = (key) => setActiveFilter((current) => current === key ? 'all' : key)
  const allPendingPayments = asArray(data.pending_payments).length ? asArray(data.pending_payments) : asArray(data.pending).length ? asArray(data.pending) : asArray(data.state?.pending)
  const customers = asArray(data.customers).length ? asArray(data.customers) : asArray(data.state?.customers)
  const services = asArray(data.services).length ? asArray(data.services) : asArray(data.catalogs?.services).length ? asArray(data.catalogs?.services) : asArray(data.state?.services)
  const quickCustomer = customers.find(item => String(item.id) === form.customer_id)
  const quickPurchase = customerComboPurchases(quickCustomer || {}).map(item => availableBookingPurchase(item)).find(item => String(item.id) === form.combo_purchase_id)
  const quickServiceItems = form.service_id ? [{ service_id: form.service_id, quantity: 1 }]
    : quickPurchase ? comboBookingItems(quickPurchase, services, form.booking_date || vietnamDate(clockMs)) : []
  const quickSelectedServices = quickServiceItems.map(part => services.find(item => item.id === part.service_id)).filter(Boolean)
  const quickSteam = manualQuickBooking && quickSelectedServices.length > 0 && quickSelectedServices.every(item => /^XONG HOI(?:\b|$)/.test(normalizedColumn(item.name)))
  const chooseQuickCustomer = (customer) => {
    const purchase = preferredBookingCombo(customer, services, form.booking_date || vietnamDate(clockMs))
    const usable = purchase && purchase.remaining > 0 && catalogIsAvailable(purchase, form.booking_date || vietnamDate(clockMs))
    return { service_id: '', combo_purchase_id: usable ? String(purchase.id) : '', payment_method: usable ? 'COMBO' : 'TIỀN MẶT', discount: '0', discount_percent: '0', discount_mode: 'amount' }
  }
  const combos = asArray(data.combo_catalog).length ? asArray(data.combo_catalog) : asArray(data.catalogs?.combos).length ? asArray(data.catalogs?.combos) : asArray(data.state?.combos)
  const pendingComboSaleRequests = asArray(data.combo_sale_requests).filter((item) => item?.status === 'pending')
  const allReports = asArray(data.report_rows).length ? asArray(data.report_rows) : asArray(data.state?.reports).length ? asArray(data.state?.reports) : asArray(data.reports)
  const pendingPayments = filterTourRows(allPendingPayments, listFilters)
  const reports = filterTourRows(allReports, listFilters)
  const visibleInvoices = filterTourRows(asArray(data.state?.invoices), listFilters)
  const reportInvoiceCount = new Set(reports.map((item) => String(item?.invoice_id || item?.bill_no || '')).filter(Boolean)).size

  const historyMatches = (item) => filterTourRows([{
    ...item, effective_at: item.effective_at || item.at || item.created_at || item.timestamp,
    customer_name: item.customer_name || item.before?.name || item.after?.name || '',
    entries: [{ employee_name: item.employee_name || item.actor || '', service: item.service || item.action || item.event_type || '' }],
  }], listFilters).length > 0
  const filteredCustomerChanges = asArray(data.customer_changes).filter(historyMatches)
  const filteredInvoiceChanges = [...asArray(data.pending_changes), ...asArray(data.invoice_changes)].filter(historyMatches)
  const filteredBreakEvents = asArray(data.break_events).filter(historyMatches)
  const backups = (asArray(data.backups).length ? asArray(data.backups) : asArray(data.state?.backups)).filter(historyMatches)
  const filteredCustomers = customers.filter((customer) => customerMatches({ ...customer, name: itemLabel(customer) }, customerSearch))
  const comboLookupCustomers = customers.filter((customer) => customerComboPurchases(customer).length > 0 && customerMatches({ ...customer, name: itemLabel(customer) }, comboLookupSearch))
  const quickCheckoutEmployees = [...asArray(data.state?.employees), ...asArray(data.retained_assignments)]
  const quickCheckoutMatches = validRecords.filter((record) => isQuickCheckoutEligible(record, columns)).map((record) => {
    const id = stableEmployeeId(record), employee = quickCheckoutEmployees.find((row) => stableEmployeeId(row) === id)
    return { value: `employee:${id}`, label: cellValue(record, employeeColumn),
      detail: `${employee?.room || cellValue(record, roomColumn)} · ${employee?.service || cellValue(record, serviceColumn)}`,
      employeeId: id, source: employee || {} }
  })
  const quickCheckoutOptions = [...quickCheckoutMatches, ...(canPending && canInvoiceView ? allPendingPayments.map((pending) => ({
    value: `pending:${pending.id || pending._id}`, label: asArray(pending.entries).map((entry) => entry.employee_name).filter(Boolean).join(', ') || 'Hóa đơn chờ thanh toán',
    detail: asArray(pending.entries).map((entry) => `${entry.room || ''} · ${entry.service || ''}`).join(' / '),
    pending, source: pending,
  })) : [])]
  const chooseQuickCheckout = (value) => {
    const option = quickCheckoutOptions.find((item) => item.value === value)
    const source = option?.source || {}
    setForm((current) => ({ ...current, employee_id: option?.employeeId || '', pending_id: option?.pending?.id || option?.pending?._id || '',
      employee_search: option?.label || '', customer_id: source.customer_id || '', customer_name: source.customer_name || '', phone: source.customer_phone || '',
      combo_purchase_id: source.combo_purchase_id || '', payment_method: source.combo_purchase_id ? 'COMBO' : 'TIỀN MẶT' }))
    setModal((current) => ({ ...current, item: option?.pending, rowIds: [] }))
  }
  const purchasedCombos = customers.flatMap((customer) => customerComboPurchases(customer).map((purchase) => ({ customer, purchase })))
  const checkoutSourceEntries = (() => {
    if (!['checkout', 'quick_checkout'].includes(modal?.kind)) return []
    if (manualQuickBooking) {
      const employee = quickCheckoutEmployees.find((row) => stableEmployeeId(row) === form.employee_id)
      const service = quickSelectedServices.length ? {
        name: quickSelectedServices.map(item => item.name).join(' & '),
        price: quickSelectedServices.reduce((sum, item) => sum + Number(item.price || 0), 0),
      } : quickPurchase && !quickPurchase.component_balances ? { name: `Vé combo · ${quickPurchase.combo_name || 'Combo'}`, price: 0 } : null
      if (!service) return []
      return [{ employee_id: quickSteam ? '' : employee?.id || '', employee_name: quickSteam ? '' : employee?.name || '', room: quickSteam ? '' : form.room,
        service: service.name, price: service.price, price_source: 'catalog',
        booked_at: `${form.booking_date}T${form.booking_time}:00+07:00`,
        service_items: quickServiceItems.map(part => ({ ...part, unit_price: services.find(item => item.id === part.service_id)?.price, ticket_units: services.find(item => item.id === part.service_id)?.ticket_units ?? 1 })) }]
    }
    const pendingEntries = asArray(modal?.item?.entries)
    if (pendingEntries.length) return pendingEntries
    const modalRowIds = asArray(modal?.rowIds)
    const ids = modalRowIds.length
      ? modalRowIds
      : modal?.kind === 'quick_checkout' && selectedQuickCheckoutRecord
        ? [stableEmployeeId(selectedQuickCheckoutRecord)]
        : []
    return ids.map((id) => {
      const employee = [...asArray(data.state?.employees), ...asArray(data.retained_assignments)].find((item) => stableEmployeeId(item) === id)
      if (employee) return {
        employee_id: id, employee_name: employee.name, service: employee.service, room: employee.room, booked_at: employee.booked_at,
        price: employee.service_price, price_source: employee.service_price_source, service_items: employee.service_items,
        combo_purchase_id: employee.combo_purchase_id, combo_reserved_units: employee.combo_reserved_units,
        combo_reserved_components: employee.combo_reserved_components,
      }
      const record = asArray(data.records).find((item) => stableEmployeeId(item) === id)
      return record ? { employee_id: id, employee_name: cellValue(record, employeeColumn), service: cellValue(record, serviceColumn), room: cellValue(record, roomColumn) } : null
    }).filter((entry) => entry?.service)
  })()
  const effectiveCatalogDate = ['checkout', 'quick_checkout'].includes(modal?.kind)
    ? vietnamDate(checkoutBookingTime(checkoutSourceEntries, modal?.item, clockMs))
    : catalogTransactionDate(clockMs, form.backdate_one_day)
  const quickBookingServices = services.filter((item) => catalogIsAvailable(item, form.booking_date || vietnamDate(clockMs)))
  const bookableServices = services.filter((item) => catalogIsAvailable(item, vietnamDate(clockMs)))
  const saleableCombos = combos.filter((item) => catalogIsAvailable(item, effectiveCatalogDate) && asArray(item.components).every((part) => services.some((service) => service.id === part.service_id && catalogIsAvailable(service, effectiveCatalogDate))))
  const eligibleCheckoutCombos = purchasedCombos.map(({ customer, purchase }) => ({ customer, purchase: availableBookingPurchase(purchase, checkoutSourceEntries) })).filter(({ customer, purchase }) => {
    const customerId = String(customer?._id ?? customer?.id ?? customer?.customer_id ?? '')
    return customerId && customerId === String(form.customer_id || '') && (manualQuickBooking && !form.service_id ? catalogIsAvailable(purchase, effectiveCatalogDate) && purchase.remaining > 0 && (!purchase.component_balances || comboBookingItems(purchase, services, effectiveCatalogDate).length > 0) : comboUsagePreview(purchase, checkoutSourceEntries, services, effectiveCatalogDate).eligible)
  })
  const selectedCheckoutCombo = eligibleCheckoutCombos.find(({ purchase }) => String(purchase.id ?? purchase._id) === form.combo_purchase_id)?.purchase
  const selectedComboPreview = comboUsagePreview(selectedCheckoutCombo, checkoutSourceEntries, services, effectiveCatalogDate)
  const checkoutPreviewEntries = checkoutSourceEntries.map((entry) => ({
    ...entry,
    preview_price: previewEntryPrice(entry, services),
    ticket_units: entry.service_items?.length ? entry.service_items.reduce((sum, item) => sum + Number(item.ticket_units ?? 1) * Number(item.quantity), 0) : previewEntryTicketUnits(entry, services),
  }))
  const checkoutPreviewSubtotal = checkoutPreviewEntries.length && checkoutPreviewEntries.every((entry) => Number.isFinite(entry.preview_price))
    ? checkoutPreviewEntries.reduce((sum, entry) => sum + entry.preview_price, 0)
    : null
  const checkoutUsesCombo = Boolean(form.combo_purchase_id)
  const checkoutHasUnresolvedPricing = checkoutPreviewEntries.some((entry) => !Number.isFinite(entry.preview_price))
  const checkoutHasZeroPricing = checkoutPreviewEntries.some((entry) => entry.preview_price === 0)
  const checkoutHasPositivePricing = checkoutPreviewEntries.some((entry) => Number.isFinite(entry.preview_price) && entry.preview_price > 0)
  const checkoutHasMixedPricing = checkoutHasZeroPricing && checkoutHasPositivePricing
  const checkoutAllZeroPricing = checkoutPreviewEntries.length > 0 && checkoutPreviewEntries.every((entry) => entry.preview_price === 0)
  const checkoutRequiresTicketPrice = ['checkout', 'quick_checkout'].includes(modal?.kind)
    && !checkoutUsesCombo && checkoutAllZeroPricing
  const checkoutEffectiveSubtotal = checkoutUsesCombo ? comboExtraSubtotal(selectedCheckoutCombo, checkoutSourceEntries, services) : checkoutRequiresTicketPrice && Number(form.ticket_price) > 0
    ? Number(form.ticket_price)
    : checkoutPreviewSubtotal
  const checkoutTipPreview = form.tip_mode === 'cards' ? form.tip_card_ids.reduce((sum, id) => sum + Number(asArray(data.payment_settings?.tip_cards).find(card => card.id === id)?.amount || 0), 0) : Math.max(0, Number(form.tip || 0))
  const checkoutDiscountPreview = checkoutUsesCombo ? 0 : discountAmount(checkoutEffectiveSubtotal, form.discount_mode, form.discount_mode === 'percent' ? form.discount_percent : form.discount)
  const checkoutPreviewTotal = Number.isFinite(checkoutEffectiveSubtotal)
    ? Math.max(0, checkoutEffectiveSubtotal - checkoutDiscountPreview) + checkoutTipPreview
    : null
  const checkoutPreviewComboUnits = selectedCheckoutCombo?.component_balances ? selectedComboPreview.units : checkoutPreviewEntries.reduce((sum, entry) => sum + Number(entry.ticket_units || 0), 0)
  const selectedComboCatalogItem = combos.find((item, index) => itemId(item, index) === form.combo_id) || null
  const comboPurchasePreviewAmount = selectedComboCatalogItem
    ? Number(selectedComboCatalogItem?.price || 0) * Math.max(1, Number(form.quantity || 1))
    : null
  const customerHistoryData = customerHistoryModal?.data || {}
  const allCustomerComboPurchases = asArray(customerHistoryData.combo_purchases).length
    ? asArray(customerHistoryData.combo_purchases)
    : asArray(customerHistoryData.purchases)
  const customerComboPurchaseHistory = filterTourRows(allCustomerComboPurchases.map((purchase) => ({ ...purchase, created_at: purchase?.effective_at || purchase?.purchased_at || purchase?.created_at })), customerHistoryFilters)
  const customerComboUsageHistory = filterTourRows(asArray(customerHistoryData.combo_usage), customerHistoryFilters)
  const comboPurchaseReceptionist = (purchase) => purchase?.receptionist || purchase?.actor || asArray(customerHistoryData.invoices).find((invoice) => String(invoice?.purchased_combo_id || '') === String(purchase?.id || ''))?.actor || purchase?.lk || purchase?.created_by || 'Chưa có thông tin'
  const selectedRecords = validRecords.filter((record, index) => selectedIds.has(recordId(record, index)))
  const allDisplayedSelected = displayedRecords.length > 0 && displayedRecords.every((record, index) => selectedIds.has(recordId(record, index)))

  const pendingReminderCount = canPending ? Number(data.pending_count ?? pendingPayments.length) : 0
  const hasPendingReminder = pendingReminderCount > 0
  const announcePendingPayments = useCallback((count) => {
    if (count <= 0) return
    setPendingReminder({
      id: ++pendingAnnouncementSequenceRef.current,
      count,
      text: `Có ${count} phiếu chờ thanh toán.`,
    })
  }, [])

  useEffect(() => {
    const previousCount = previousPendingCountRef.current
    previousPendingCountRef.current = pendingReminderCount
    pendingCountRef.current = pendingReminderCount
    if (previousCount === 0 && pendingReminderCount > 0) announcePendingPayments(pendingReminderCount)
    if (pendingReminderCount === 0) setPendingReminder(null)
  }, [announcePendingPayments, pendingReminderCount])

  useEffect(() => {
    if (!hasPendingReminder) return undefined
    pendingReminderTimerRef.current = window.setInterval(() => {
      announcePendingPayments(pendingCountRef.current)
    }, PENDING_REMINDER_INTERVAL_MS)
    return () => {
      window.clearInterval(pendingReminderTimerRef.current)
      pendingReminderTimerRef.current = null
    }
  }, [announcePendingPayments, hasPendingReminder])

  const toggleRow = (id) => { setSelectedRoomKey(''); setSelectedIds((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id); else { next.add(id); setWeeklyShiftOpen(true) }
    return next
  }) }
  const openEmployeeAndShift = (record, index = 0) => {
    const id = stableEmployeeId(record) || recordId(record, index)
    setSelectedRoomKey('')
    setSelectedIds(new Set(id ? [id] : []))
    setWeeklyShiftOpen(true)
    openEmployeeBooking(record)
  }
  const toggleDisplayed = () => { setSelectedRoomKey(''); setSelectedIds((current) => {
    const next = new Set(current)
    displayedRecords.forEach((record, index) => {
      const id = recordId(record, index)
      if (allDisplayedSelected) next.delete(id); else next.add(id)
    })
    return next
  }) }
  const openPendingPanel = () => {
    if (!canPending) return
    setActivePanel('pending')
    setPendingReminder(null)
    window.requestAnimationFrame(() => workspaceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  const summaryRecords = selectedRoomKey ? selectedRoomRecords : selectedRecords
  const selectedSummary = () => (selectedRoomKey ? `${areaLabel(selectedRoom)}\n` : '') + summaryRecords.map((record) => [
    cellValue(record, employeeColumn), cellValue(record, serviceColumn), cellValue(record, requestColumn), cellValue(record, roomColumn),
  ].filter(Boolean).join(' | ')).join('\n')

  const copySelectedSummary = async () => {
    if (!summaryRecords.length) return setNotice(selectedRoomKey ? 'Phòng đang trống, chưa có thông tin để sao chép.' : 'Hãy chọn phòng hoặc nhân viên cần sao chép.')
    try {
      await navigator.clipboard.writeText(selectedSummary())
      setNotice(`Đã sao chép ${summaryRecords.length} dòng Live Tour.`)
    } catch {
      setError('Trình duyệt không cho phép sao chép. Hãy cấp quyền Clipboard và thử lại.')
    }
  }

  const shareSelectedSummary = async () => {
    if (!summaryRecords.length) return setNotice(selectedRoomKey ? 'Phòng đang trống, chưa có thông tin để chia sẻ.' : 'Hãy chọn phòng hoặc nhân viên cần chia sẻ.')
    if (!navigator.share) return copySelectedSummary()
    try { await navigator.share({ title: 'Live Tour · VERA SPA', text: selectedSummary() }) } catch (err) {
      if (err?.name !== 'AbortError') setError('Không chia sẻ được dữ liệu đã chọn.')
    }
  }

  const copyBoardImage = async () => {
    if (actionBusy) return
    if (!canExportKind('board')) {
      setError('Tài khoản chưa được cấp quyền copy bảng tua.')
      return
    }
    setActionBusy('copy-board')
    setError('')
    setNotice('')
    try {
      await copyPngToClipboard(() => veraApi.readLiveTourPng())
    } catch (err) {
      setError(err?.name === 'NotAllowedError'
        ? 'Chưa copy được ảnh. Hãy cho phép truy cập bộ nhớ tạm và bấm Copy B.Tua lại.'
        : err.message || 'Không copy được ảnh bảng tua. Hãy thử lại.')
    } finally {
      setActionBusy('')
    }
  }

  const exportData = async (kind) => {
    if (actionBusy) return
    if (!canExportKind(kind)) {
      setError('Tài khoản chưa được cấp đủ quyền để xuất loại dữ liệu Live Tour này.')
      return
    }
    const query = FILTERED_EXPORT_KINDS.has(kind) ? compactExportQuery({ ...listFilters, preset: '' }) : {}
    if (kind === 'custom') {
      query.columns = (customColumns ?? columns).filter((column) => columns.includes(column))
      if (!query.columns.length) { setError('Hãy chọn ít nhất một cột để xuất.'); return }
      if (customScope !== 'all') {
        query.employee_ids = customScope === 'selected' ? [...selectedIds] : displayedRecords.map(stableEmployeeId).filter(Boolean)
        if (!query.employee_ids.length) { setError('Không có nhân viên trong phạm vi xuất đã chọn.'); return }
      }
    }
    if (query.date_from && query.date_to && query.date_from > query.date_to) {
      setError('Ngày bắt đầu của bộ lọc xuất dữ liệu không được sau ngày kết thúc.')
      return
    }
    setActionBusy(`export-${kind}`)
    setError('')
    try {
      await veraApi.exportLiveTourExcel(kind, query)
      setNotice('Đã tạo file xuất Live Tour.')
    } catch (err) {
      setError(err.message || 'Không xuất được dữ liệu Live Tour.')
    } finally {
      setActionBusy('')
    }
  }

  const openCustomerHistory = async (customer) => {
    if (!canCustomers) {
      setError('Tài khoản chưa được cấp quyền xem lịch sử khách hàng.')
      return
    }
    const customerId = stableCustomerId(customer)
    if (!customerId) {
      setError('Khách hàng này chưa có mã ổn định để xem lịch sử.')
      return
    }
    setCustomerHistoryFilters({ preset: 'month', ...tourDateRange('month') })
    setCustomerHistoryModal({ customerId, customer, data: null, error: '' })
    setCustomerHistoryBusy(true)
    try {
      const history = await veraApi.liveTourCustomerHistory(customerId)
      setCustomerHistoryModal((current) => current?.customerId === customerId ? { ...current, data: history, error: '' } : current)
    } catch (err) {
      setCustomerHistoryModal((current) => current?.customerId === customerId ? { ...current, error: err.message || 'Không tải được lịch sử khách hàng.' } : current)
    } finally {
      setCustomerHistoryBusy(false)
    }
  }

  const exportCustomerHistory = async () => {
    const customerId = customerHistoryModal?.customerId
    if (!customerId || !canExportKind('customer_detail') || actionBusy) return
    setActionBusy('export-customer-detail')
    setError('')
    try {
      await veraApi.exportLiveTourExcel('customer_detail', compactExportQuery({ customer_id: customerId, date_from: customerHistoryFilters.date_from, date_to: customerHistoryFilters.date_to }))
      setNotice('Đã tạo file lịch sử chi tiết khách hàng.')
    } catch (err) {
      setError(err.message || 'Không xuất được lịch sử khách hàng.')
    } finally {
      setActionBusy('')
    }
  }

  const openWorkspacePanel = (panel) => {
    if (panel === 'pending') setListFilters({ ...EMPTY_TOUR_FILTERS, preset: 'all' })
    if (panel === 'reports') setListFilters({ ...EMPTY_TOUR_FILTERS, preset: 'yesterday', ...tourDateRange('yesterday') })
    setActivePanel(panel)
    window.requestAnimationFrame(() => workspaceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  const removeCatalogItem = (action, item) => {
    if (window.confirm(`Xóa “${itemLabel(item)}” khỏi danh mục?`)) void executeAction(action, { id: item?.id, code: item?.code }, [])
  }

  return <div className="feature-page tour-page live-tour-page">
    <style>{appearanceCss}</style>
    <style>{`
      .live-tour-page{--live-tour-section-gap:10px;gap:var(--live-tour-section-gap)}.page-wrap.live-tour-page-wrap{padding-top:0;padding-bottom:0}.live-tour-page>.setup-note{padding:6px 9px;font-size:9px}
      .live-tour-board{min-width:0}.live-tour-board>.tour-records-panel{margin-top:var(--live-tour-section-gap)}
      .live-tour-page .tour-board-top{position:static;display:grid;gap:var(--live-tour-section-gap);background:var(--paper,#f7faf8)}
      .live-tour-page .tour-topbar{display:flex;flex-wrap:nowrap;align-items:center;gap:4px 6px;overflow-x:auto;scrollbar-width:thin}
      .live-tour-customer-count{display:inline-flex;align-items:center;gap:4px;min-height:20px;margin-left:2px;padding:0 6px;border:1px solid #bfd4c7;border-radius:5px;color:#173c30;background:#edf7f1;font-size:9px;font-weight:800;white-space:nowrap}.live-tour-customer-count strong{font-size:13px;line-height:1}
      .live-tour-page .tour-heading-title{min-width:0;display:flex;align-items:center;gap:8px}.live-tour-weekly-shift{position:relative}.live-tour-weekly-shift-button{min-height:28px;padding:4px 12px;border:1px solid #c9a84d;border-radius:8px;background:linear-gradient(180deg,#fff9df,#f6e5a8);color:#6b4a00;font-size:9px;font-weight:950;white-space:nowrap;box-shadow:0 2px 7px rgba(115,82,12,.16);cursor:pointer}.live-tour-weekly-shift-button:hover,.live-tour-weekly-shift-button:focus-visible{background:#f4dda0;border-color:#aa8323;outline:2px solid rgba(170,131,35,.2)}.weekly-mobile{display:none}.live-tour-weekly-shift-popover{position:absolute;z-index:12000;top:calc(100% + 6px);left:0;width:min(420px,90vw);max-height:65vh;overflow:auto;display:grid;gap:8px;padding:12px;border:1px solid #d8c27b;border-radius:12px;background:#fffdf5;box-shadow:0 12px 32px rgba(50,42,18,.22);font-size:11px}.live-tour-weekly-shift-popover>div{display:grid;gap:3px}.live-tour-weekly-shift-popover span{display:block;padding-left:8px}.live-tour-page .tour-heading-title h1{margin:0;color:var(--green-950);font-family:Georgia,serif;font-size:14px;line-height:1}.live-tour-status{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:1px 4px;color:#17603f;background:#dff4e8;font-size:8px;font-weight:900}.live-tour-status:before{content:'';width:7px;height:7px;border-radius:50%;background:#23a861;box-shadow:0 0 0 3px rgba(35,168,97,.16)}
      .live-tour-page .tour-table tr.tour-row-waiting:not(.tour-row-break) td{color:#3f245d;background:var(--tour-row-waiting);font-weight:900}.live-tour-page .tour-table tr.live-tour-selected td{box-shadow:inset 0 2px #173c30,inset 0 -2px #173c30}.live-tour-page .tour-table tr.live-tour-selected td:first-child{box-shadow:inset 2px 0 #173c30,inset 0 2px #173c30,inset 0 -2px #173c30}.live-tour-page .tour-legend-grid .waiting{color:#3f245d;background:var(--tour-row-waiting);border-color:#c9aee7;font-weight:900}.live-tour-page .live-tour-select-col input[type=checkbox]{display:block;min-width:0;min-height:0;margin:auto;padding:0;box-sizing:border-box;accent-color:#173c30}
      .live-tour-page .live-tour-shift-controls{display:flex;align-items:center;gap:6px;min-width:0}.live-tour-page .tour-shift-filter{display:flex;flex:0 0 auto;align-items:center;gap:4px;margin:0}.live-tour-page .tour-shift-filter button{flex:0 0 auto;min-width:48px;min-height:15px;padding:0 6px;border-radius:5px;font-size:9px;line-height:1.1;white-space:nowrap}
      .live-tour-page .tour-heading-actions{display:flex;gap:4px;flex-wrap:nowrap;justify-content:flex-end;margin-left:auto}.live-tour-page .tour-heading-actions button{min-height:24px;padding:3px 8px;font-family:inherit;font-size:10px;line-height:1.15;font-weight:900;border-radius:999px;background:#204e40;color:#fff;border:1px solid #204e40;white-space:nowrap}.live-tour-page .tour-heading-actions .live-tour-combo-approval-button{min-height:28.8px}.live-tour-combo-approvals .live-tour-card-actions button{min-height:32.4px}.live-tour-page .tour-heading-actions button svg{width:13px;height:13px}.live-tour-page .tour-topbar>.icon-button{width:auto;min-width:20px;height:20px;min-height:20px;flex:0 0 auto;padding:0 3px;border-radius:4px;font-size:9px}.live-tour-page .tour-topbar>.icon-button svg{width:14px;height:14px}.live-tour-page .tour-admin-tools-toggle.active{color:#fff;background:#8c6b30;border-color:#8c6b30}
      .live-tour-payment-reminder{display:flex;align-items:center;gap:6px;min-height:23px;margin:0;padding:0 6px;border:1px solid #e9ad57;border-radius:9px;color:#64350d;background:#fff3d7;box-shadow:0 3px 12px rgba(124,73,17,.12);font-size:10px}.live-tour-payment-reminder strong{font-size:10px}.live-tour-payment-reminder>svg{width:12px;height:12px;flex-shrink:0}.live-tour-payment-reminder span{flex:1}.live-tour-payment-reminder button{min-height:20px;padding:0 6px;font-size:9px;line-height:1.1}.live-tour-sr-only{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip-path:inset(50%)!important;white-space:nowrap!important;border:0!important}
      .live-tour-page .tour-control-layout{min-width:0}.live-tour-page .tour-control-layout .tour-metrics{grid-template-columns:repeat(10,minmax(0,1fr));gap:4px;max-width:100%;margin:0;padding:0;overflow:hidden}.live-tour-page .metric-grid.small .metric-card.tour-metric-card{min-width:0;min-height:15px;gap:3px;border-radius:4px;padding:0 3px}.live-tour-page .metric-grid.small .metric-card.tour-metric-card span{min-width:0;font-size:8px;white-space:nowrap}.live-tour-page .metric-grid.small .metric-card.tour-metric-card strong{font-size:13px;line-height:1}
      .live-tour-page .tour-room-segment-buttons{display:flex;flex:0 0 auto;align-items:center;gap:4px}.live-tour-page .tour-room-segment-button{flex:0 0 auto;min-width:0;min-height:15px;border:1px solid transparent;border-radius:4px;padding:0 6px;display:flex;align-items:center;justify-content:center;gap:5px;color:#fff;font-weight:900;text-align:center;white-space:nowrap}.live-tour-page .tour-room-segment-button.all{background:linear-gradient(180deg,#426d5b,#294d3e);border-color:#244638}.live-tour-page .tour-room-segment-button.standard{background:#155b78;border-color:#0d465f}.live-tour-page .tour-room-segment-button.vip{background:linear-gradient(180deg,#bd9243,#92702f);border-color:#7d5c22}.live-tour-page .tour-room-segment-button svg{width:11px;height:11px;flex-shrink:0}.live-tour-page .tour-room-segment-button span{font-size:9px;line-height:1.1}.live-tour-page .tour-room-segment-button.active{outline:2px solid rgba(23,51,41,.18);outline-offset:1px;box-shadow:0 5px 12px rgba(22,51,41,.17)}
      .live-tour-page .tour-table-panel{padding:0;border-radius:4px;box-shadow:none}.live-tour-page .tour-table th,.live-tour-page .tour-table td{padding-top:5px;padding-bottom:5px}.live-tour-page .tour-records-panel{min-height:0;height:auto;max-height:none}.live-tour-page .tour-records-panel .tour-table{max-height:none;height:auto;overflow-x:auto;overflow-y:hidden;scrollbar-gutter:auto}.live-tour-page .tour-records-panel .tour-table thead{position:static;transform:none}.live-tour-page .tour-records-panel .tour-table th{position:static}.live-tour-select-col{width:28px;min-width:28px;text-align:center}.live-tour-select-col input{width:13px;height:13px;accent-color:#173c30}
      .live-tour-page .tour-quick-tools{display:flex;gap:4px 6px;align-items:center;flex-wrap:wrap;margin:0}.live-tour-page .tour-employee-search{position:relative;flex:1 1 260px;max-width:360px}.live-tour-page .tour-employee-search svg{position:absolute;left:8px;top:50%;transform:translateY(-50%);pointer-events:none;color:#60756b}.live-tour-page .tour-employee-search input{width:100%;height:27px;padding:4px 7px 4px 27px;box-sizing:border-box;font-size:9px}.live-tour-selection-summary{font-size:9px;font-weight:850;color:#3d5a4e}.live-tour-quick-button{min-height:27px;padding:4px 8px;font-size:9px}
      .live-tour-page .tour-room-panel{margin:0;padding:0;border:1px solid #cfe1d8;border-radius:4px;background:#f3faf6}.live-tour-page .tour-room-panel-head{display:flex;align-items:center;gap:6px;min-width:0;min-height:30px;box-sizing:border-box;margin:0;padding:0 0 4px;overflow-x:auto;overflow-y:hidden;overscroll-behavior-x:contain;scrollbar-width:thin}.live-tour-page .tour-room-panel-title{display:flex;flex:0 0 auto;align-items:center;gap:4px;color:#173c30;font-size:11px;font-weight:900;white-space:nowrap}.live-tour-page .tour-room-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(108px,1fr));gap:4px 3px}
      .live-tour-page .tour-room-card{--room-segment:#155b78;--room-border:#176b89;--room-glow:rgba(21,91,120,.28);position:relative;isolation:isolate;width:100%;min-width:0;min-height:77.74px;display:flex;flex-direction:column;gap:0;border:2px solid var(--room-border);border-radius:8px;padding:1px;color:inherit;background:#fff;text-align:left;appearance:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.72),inset 0 4px 0 var(--room-segment),0 3px 8px rgba(24,52,42,.16),0 0 0 1px var(--room-glow);transition:transform .2s cubic-bezier(.2,.8,.2,1),box-shadow .2s ease,border-color .2s ease,filter .2s ease}.live-tour-page .tour-room-card:after{content:'';position:absolute;z-index:-1;inset:1px;border-radius:5px;pointer-events:none;background:linear-gradient(135deg,rgba(255,255,255,.28),transparent 42%)}.live-tour-page .tour-room-card.vip{--room-segment:#b88618;--room-border:#c6921e;--room-glow:rgba(184,134,24,.35);border:3px solid var(--room-border);padding:0;box-shadow:inset 0 0 0 1px #fff2b9,inset 0 4px 0 #f3cf72,0 4px 10px rgba(116,78,8,.24),0 0 0 1px rgba(255,211,92,.72)}.live-tour-page .tour-room-card.has-private-service{padding-right:29px}@media(hover:hover) and (pointer:fine){.live-tour-page .tour-room-card:hover{z-index:4;transform:translateY(-3px) scale(1.012);filter:saturate(1.07);box-shadow:inset 0 0 0 1px rgba(255,255,255,.82),inset 0 4px 0 var(--room-segment),0 9px 18px rgba(20,50,39,.25),0 0 0 2px var(--room-glow)}.live-tour-page .tour-room-card.vip:hover{box-shadow:inset 0 0 0 1px #fff5ca,inset 0 4px 0 #ffe08a,0 10px 20px rgba(116,78,8,.3),0 0 0 2px rgba(255,205,66,.78)}}.live-tour-page .tour-room-card:active{transform:translateY(0) scale(.985)}.live-tour-page .tour-room-card.selected{z-index:3;outline:3px solid #143f32;outline-offset:1px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.78),inset 0 4px 0 var(--room-segment),0 7px 16px rgba(20,63,50,.28),0 0 0 3px var(--room-glow)}.live-tour-page .tour-room-card.vip.selected{outline-color:#8d6205;box-shadow:inset 0 0 0 1px #fff4c2,inset 0 4px 0 #ffe08a,0 8px 18px rgba(116,78,8,.3),0 0 0 3px rgba(255,205,66,.68)}
      @keyframes live-tour-room-search-pulse{0%,100%{filter:brightness(1);transform:scale(1);box-shadow:0 0 0 2px #ee3f62,0 2px 6px rgba(28,52,42,.08)}50%{filter:brightness(1.13);transform:scale(1.025);background:#55f0cf;box-shadow:0 0 0 4px #ffd54a,0 7px 15px rgba(238,63,98,.34)}}.live-tour-page .tour-room-card.search-match{position:relative;z-index:3;animation:live-tour-room-search-pulse .8s ease-in-out infinite}
      .live-tour-page .tour-room-card.state-green{--room-segment:#34791a;--room-border:#4a9627;--room-glow:rgba(74,150,39,.34);background:var(--tour-row-green)}.live-tour-page .tour-room-card.state-yellow{--room-segment:#967018;--room-border:#bb8b20;--room-glow:rgba(187,139,32,.32);background:var(--tour-row-yellow)}.live-tour-page .tour-room-card.state-red{--room-segment:#a9212b;--room-border:#ce3541;--room-glow:rgba(206,53,65,.31);background:var(--tour-row-red)}.live-tour-page .tour-room-card.state-break{--room-segment:#a75a17;--room-border:#cf792b;--room-glow:rgba(207,121,43,.3);background:var(--tour-row-break)}.live-tour-page .tour-room-card.state-waiting{--room-segment:#684090;--room-border:#8658b2;--room-glow:rgba(134,88,178,.33);color:#3f245d;background:var(--tour-row-waiting)}.live-tour-page .tour-room-card.state-idle{--room-segment:#587369;--room-border:#708f83;--room-glow:rgba(112,143,131,.26);background:var(--tour-row-idle)}.live-tour-page .tour-room-card.state-leave,.live-tour-page .tour-room-card.state-work,.live-tour-page .tour-room-card.state-default,.live-tour-page .tour-room-card.state-blank{background:#fff}.live-tour-page .tour-room-card.state-leave{color:#8a8a8a}
      .live-tour-page .tour-room-card-head{display:flex;align-items:center;justify-content:space-between;gap:3px}.live-tour-page .tour-room-card-head strong{min-width:0;display:flex;align-items:center;gap:1px;font-size:8px;font-weight:950;line-height:1.1;white-space:nowrap}.live-tour-page .tour-room-type{border-radius:999px;padding:0 2px;color:#fff;background:var(--room-segment);font-size:5px;font-weight:950;letter-spacing:.04em}.live-tour-page .tour-room-countdown{display:flex;align-items:center;gap:3px;font-variant-numeric:tabular-nums;font-size:9px;font-weight:950;line-height:1.1;white-space:nowrap}.live-tour-page .tour-room-countdown svg{width:11px;height:11px;flex:0 0 auto}.live-tour-page .tour-room-meta{min-height:7px;overflow:hidden;font-size:6px;line-height:1.1;font-weight:800;text-overflow:ellipsis;white-space:nowrap;opacity:.8}.live-tour-page .tour-room-private-badge{position:absolute;right:4px;bottom:4px;width:21px;height:21px;display:grid;place-items:center;border:2px solid #fff;border-radius:50%;color:#fff;background:#e30057;box-shadow:0 0 0 2px #ffd447,0 4px 10px rgba(167,0,60,.38);font-size:9px;font-weight:950;line-height:1;letter-spacing:-.02em}.live-tour-page .tour-room-empty{grid-column:1/-1;padding:6px;color:#5d7168;font-size:9px;text-align:center}.live-tour-page .tour-room-detail{margin-top:var(--live-tour-section-gap);padding:2px;border:1px solid #d9e2dd;border-radius:8px;background:#fff}.live-tour-page .tour-room-detail-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px}.live-tour-page .tour-room-detail-head strong{font-size:10px}.live-tour-page .tour-room-detail-head small{color:#68776f;font-size:7px;font-weight:800}.live-tour-page .tour-room-detail-list{display:grid;gap:var(--live-tour-section-gap)}.live-tour-page .tour-room-detail-row{min-width:0;display:grid;grid-template-columns:minmax(90px,.55fr) minmax(120px,1fr);gap:8px;padding:4px 6px;border-radius:6px;background:#f3f6f4;font-size:8px}.live-tour-page .tour-room-detail-row strong,.live-tour-page .tour-room-detail-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.live-tour-page .tour-room-detail-row span{color:#55665e}.live-tour-page .tour-room-detail-empty{padding:4px;color:#68776f;font-size:8px}.live-tour-page .tour-room-detail.vip-19{max-height:none;overflow:visible}
      .live-tour-page .tour-legend{padding:9px}.live-tour-page .tour-legend .panel-title-row{margin-bottom:5px}.live-tour-page .tour-legend .panel-title-row h2{font-size:14px}.live-tour-page .tour-legend .panel-title-row p{font-size:9px}.live-tour-page .tour-legend-grid{gap:4px}.live-tour-page .tour-legend-grid span{padding:4px 7px;font-size:8px}
      .live-tour-operator{padding:10px;overflow:hidden}.live-tour-operator-head{display:flex;align-items:center;justify-content:space-between;gap:8px}.live-tour-operator-title{display:flex;align-items:center;gap:7px}.live-tour-operator-title strong{font-size:14px}.live-tour-pending-badge{display:inline-flex;align-items:center;gap:4px;border:0;border-radius:999px;padding:4px 8px;color:#8c271f;background:#ffe7e3;font-family:inherit;font-size:9px;font-weight:900;cursor:pointer}.live-tour-pending-badge:focus-visible{outline:2px solid #8c271f;outline-offset:2px}.live-tour-pending-badge:disabled{cursor:default;opacity:.65}.live-tour-pending-badge.has-items{animation:live-tour-pulse 1.5s ease-in-out infinite}@keyframes live-tour-pulse{50%{box-shadow:0 0 0 5px rgba(198,53,40,.12)}}.live-tour-panel-tabs{display:flex;gap:5px;overflow-x:auto;padding:3px 0}.live-tour-panel-tabs button{flex:0 0 auto;min-height:31px;padding:5px 10px;font-size:9px}.live-tour-export-filters{display:grid;grid-template-columns:auto repeat(4,minmax(105px,1fr)) auto;align-items:end;gap:6px;margin:7px 0;padding:8px;border:1px solid #dce6e1;border-radius:9px;background:#f7faf8}.live-tour-export-filters>strong{align-self:center;font-size:9px}.live-tour-export-filters label{display:grid;gap:3px;color:#526a60;font-size:8px;font-weight:800}.live-tour-export-filters input{width:100%;min-width:0;box-sizing:border-box;padding:5px 6px;font-size:9px}.live-tour-export-filters small{grid-column:1/-1;color:#6d7e76;font-size:8px}.live-tour-export-filters button{min-height:29px;padding:4px 8px;font-size:9px}.live-tour-panel-body{margin-top:4px;padding:9px;border:1px solid #d9e4de;border-radius:10px;background:#fff}.live-tour-panel-toolbar{display:flex;align-items:center;justify-content:space-between;gap:7px;flex-wrap:wrap;margin-bottom:8px}.live-tour-panel-toolbar h2{margin:0;font-size:14px}.live-tour-panel-toolbar-actions{display:flex;gap:5px;flex-wrap:wrap}.live-tour-panel-toolbar button{min-height:30px;padding:5px 8px;font-size:9px}.live-tour-card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:7px}.live-tour-data-card{display:grid;gap:4px;padding:8px;border:1px solid #dbe5df;border-radius:9px;background:#f8faf9;font-size:9px}.live-tour-data-card strong{font-size:11px}.live-tour-data-card small{color:#66776f}.live-tour-card-actions{display:flex;gap:5px;flex-wrap:wrap;margin-top:3px}.live-tour-card-actions button{min-height:27px;padding:4px 7px;font-size:8px}.live-tour-empty{padding:14px;color:#687970;background:#f6f8f7;border-radius:8px;font-size:10px;text-align:center}.live-tour-report-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:6px;margin-bottom:8px}.live-tour-report-metric{padding:9px;border:1px solid #dce6e1;border-radius:9px;background:#f7faf8}.live-tour-report-metric span{display:block;color:#65766e;font-size:8px}.live-tour-report-metric strong{display:block;margin-top:3px;font-size:14px}.live-tour-catalog-section{margin-top:10px}.live-tour-catalog-section h3{margin:0 0 6px;font-size:11px}.live-tour-customer-search{position:relative;min-width:min(300px,100%)}.live-tour-customer-search svg{position:absolute;left:8px;top:50%;transform:translateY(-50%)}.live-tour-customer-search input{width:100%;height:30px;padding:5px 7px 5px 27px;font-size:9px}
      .live-tour-modal-backdrop{position:fixed;inset:0;z-index:1600;display:grid;place-items:center;padding:12px;background:rgba(14,31,25,.55)}.live-tour-modal{width:min(760px,100%);max-height:calc(100vh - 24px);overflow:auto;border-radius:14px;padding:13px;background:#fff;box-shadow:0 18px 55px rgba(0,0,0,.28)}.live-tour-modal-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}.live-tour-modal-head strong{font:700 18px Georgia,serif;color:#173c30}.live-tour-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.live-tour-form-grid>.wide{grid-column:1/-1}.live-tour-field{display:grid;gap:4px}.live-tour-field.wide{grid-column:1/-1}.live-tour-field span{font-size:9px;font-weight:850;color:#435d52}.live-tour-field input,.live-tour-field select,.live-tour-field textarea{width:100%;min-width:0;box-sizing:border-box;padding:7px 8px;font-size:10px}.live-tour-field textarea{min-height:62px;resize:vertical}.live-tour-check-field{display:flex;align-items:center;gap:7px;font-size:10px;font-weight:800}.live-tour-multi-booking{grid-column:1/-1;display:grid;gap:6px}.live-tour-multi-row{display:grid;grid-template-columns:minmax(105px,.7fr) repeat(3,minmax(95px,1fr));gap:5px;align-items:center;padding:6px;border:1px solid #dce6e1;border-radius:8px;background:#f7faf8}.live-tour-multi-row strong{font-size:9px}.live-tour-multi-row input,.live-tour-multi-row select{width:100%;min-width:0;padding:6px;font-size:9px}.live-tour-modal-actions{display:flex;justify-content:flex-end;gap:7px;margin-top:12px}.live-tour-modal-actions button{min-height:34px}.tour-booking-submit-actions{gap:21px}.tour-booking-submit-actions>button{flex:1 1 0;min-width:0}.tour-booking-submit-actions>.primary-button[type=submit]{flex-grow:3}
      .live-tour-page .tour-table .tour-col-employee,.live-tour-page .tour-table .tour-col-employee .text-button{color:#000;opacity:1}.live-tour-employee-picker{grid-column:1/-1;display:grid;gap:5px;max-height:220px;overflow:auto;padding:5px;border:1px solid #dce6e1;border-radius:9px;background:#f7faf8}.live-tour-employee-picker button{display:grid;grid-template-columns:minmax(130px,.8fr) minmax(150px,1fr);gap:3px 9px;padding:7px 9px;border:1px solid #d9e3dd;border-radius:8px;color:#173c30;background:#fff;text-align:left}.live-tour-employee-picker button.selected{border-color:#173c30;background:#e7f3ed;box-shadow:inset 3px 0 #173c30}.live-tour-employee-picker button strong{font-size:10px}.live-tour-employee-picker button span,.live-tour-employee-picker button small{font-size:8px}.live-tour-employee-picker button small{grid-column:1/-1;color:#697b72}.live-tour-employee-picked{grid-column:1/-1;padding:6px 8px;border-radius:7px;color:#185238;background:#e3f4ea;font-size:9px;font-weight:850}
      .live-tour-checkout-preview{display:grid;gap:6px;padding:9px;border:1px solid #cfe0d7;border-radius:9px;background:#f6faf8}.live-tour-checkout-preview>strong{color:#173c30;font-size:10px}.live-tour-checkout-preview>small{color:#65766e;font-size:8px}.live-tour-checkout-entry{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 8px;padding:6px;border-radius:7px;background:#fff;font-size:9px}.live-tour-checkout-entry span{overflow:hidden;text-overflow:ellipsis}.live-tour-checkout-entry small{grid-column:1/-1;color:#697b72;font-size:8px}.live-tour-checkout-total{display:grid;grid-template-columns:1fr auto;gap:4px 8px;padding-top:6px;border-top:1px solid #d8e4de;font-size:9px}.live-tour-combo-deduction{padding:7px;border-radius:8px;color:#4c3b0c;background:#fff4cf;font-size:9px}.live-tour-customer-selected{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 8px;border-radius:8px;background:#e6f4ec;font-size:9px}.live-tour-customer-selected button{min-height:27px;padding:4px 7px;font-size:8px}.live-tour-customer-picker{display:grid;gap:4px;max-height:150px;overflow:auto;padding:5px;border:1px solid #dce6e1;border-radius:8px;background:#f7faf8}.live-tour-customer-picker button{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 8px;border:1px solid #dce6e1;border-radius:7px;color:#173c30;background:#fff;text-align:left}.live-tour-customer-picker button span{color:#64776e;font-size:8px}.live-tour-correction{display:grid;gap:7px;padding:9px;border:1px solid #e8c985;border-radius:9px;background:#fff9e9}.live-tour-history-sections{display:grid;gap:10px}.live-tour-history-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:6px}.live-tour-history-list{display:grid;gap:5px;max-height:260px;overflow:auto}.live-tour-history-list article{padding:7px;border:1px solid #dce6e1;border-radius:8px;background:#f8faf9;font-size:9px}.live-tour-history-list article strong,.live-tour-history-list article span,.live-tour-history-list article small{display:block;margin-top:2px}
      @media(min-width:641px){.live-tour-page .tour-room-detail{max-height:none;overflow:visible}.live-tour-page .tour-room-detail.vip-19{max-height:none;overflow:visible}}
      @media(prefers-reduced-motion:reduce){.live-tour-page .tour-room-card{transition:none}.live-tour-page .tour-room-card:hover,.live-tour-page .tour-room-card:active{transform:none}.live-tour-page .tour-room-card.search-match{animation:none;outline:4px solid #ee3f62;outline-offset:1px;background:#55f0cf}}
      @media(max-width:760px){.live-tour-export-filters{grid-template-columns:repeat(2,minmax(0,1fr))}.live-tour-export-filters>strong,.live-tour-export-filters small{grid-column:1/-1}.live-tour-form-grid{grid-template-columns:1fr}.live-tour-field.wide{grid-column:auto}.live-tour-multi-row{grid-template-columns:1fr 1fr}.live-tour-multi-row strong{grid-column:1/-1}}
      @media(max-width:640px){
        .live-tour-page{--live-tour-section-gap:12px}
        .live-tour-page .tour-topbar{gap:4px}.live-tour-page .tour-heading-title h1{font-size:13px}.live-tour-page .tour-records-panel .tour-table{max-height:none;height:auto;overflow-x:hidden;overflow-y:hidden}
        .live-tour-page .tour-shift-filter{gap:3px}.live-tour-page .tour-shift-filter button{min-width:40px;padding:0 5px;font-size:9px}
        .live-tour-page .tour-heading-actions{justify-content:flex-start;margin-left:auto}.live-tour-page .tour-heading-actions button{flex:0 0 auto}
        .live-tour-page .metric-grid.small .metric-card.tour-metric-card{min-height:15.5px;padding:0 4px}.live-tour-page .metric-grid.small .metric-card.tour-metric-card span{font-size:8px;line-height:1.05}.live-tour-page .metric-grid.small .metric-card.tour-metric-card strong{font-size:13px}
        .live-tour-page .tour-room-segment-button{padding:0 5px}.live-tour-page .tour-room-segment-button svg{width:12px;height:12px}.live-tour-page .tour-room-segment-button span{font-size:9px}
        .live-tour-page .tour-table-panel{padding:0;border-radius:4px;box-shadow:none}.live-tour-page .tour-quick-tools{display:grid;grid-template-columns:minmax(0,1fr);gap:6px;margin:0}.live-tour-page .tour-employee-search{min-width:0;max-width:none}.live-tour-page .tour-employee-search input{min-width:0;height:29px;padding:5px 5px 5px 27px;font-size:8px}.live-tour-page .tour-employee-search svg{left:8px;width:14px}.live-tour-selection-summary{font-size:8px}.live-tour-select-col{width:18px;min-width:18px}.live-tour-page .live-tour-select-col input[type=checkbox]{width:10px;height:10px}
        .live-tour-page .tour-room-panel{padding:0}.live-tour-page .tour-room-panel-head{gap:4px;margin-bottom:0}.live-tour-page .tour-room-panel-title{font-size:9px}.live-tour-page .tour-room-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:4px 3px}.live-tour-page .tour-room-card{min-height:77.74px;padding:2px}.live-tour-page .tour-room-card.vip{padding:0}.live-tour-page .tour-room-card-head strong{font-size:8px}.live-tour-page .tour-room-type{padding:0 2px;font-size:4px}.live-tour-page .tour-room-countdown{font-size:9px}.live-tour-page .tour-room-countdown svg{width:10px;height:10px}.live-tour-page .tour-room-meta{font-size:6px}.live-tour-page .tour-room-detail-row{grid-template-columns:minmax(75px,.55fr) minmax(0,1fr);gap:4px;padding:4px;font-size:7px}
      }
      @media(max-width:420px){.live-tour-page .tour-room-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
      @media(max-width:430px){.live-tour-selection-summary{grid-column:1/-1}.live-tour-card-grid{grid-template-columns:1fr}}
    `}</style>
    {/* The board expands in document flow to display every employee. */}
    <div className="live-tour-board">
    <div className="tour-board-top">
      {pendingReminder && <div className="live-tour-payment-reminder">
        <BellRing size={16} aria-hidden="true"/><strong>CHỜ THANH TOÁN</strong><span>Hiện có {pendingReminderCount} phiếu cần xử lý.</span>
        <button data-ui-key="u-1d49f95cc184" data-ui-label-default="Mở danh sách" type="button" className="secondary-button" onClick={openPendingPanel} aria-controls="live-tour-pending-panel"><UiCustomText uiKey="u-1d49f95cc184">Mở danh sách</UiCustomText></button>
      </div>}
      <div className="tour-topbar">
        {navigationToggle}
        <div data-ui-key="u-a54bda9ab8fe" className="tour-heading-title"><h1>LIVE TOUR</h1><span className="live-tour-status">TRỰC TIẾP</span></div>
        <div className="tour-shift-filter" role="group" aria-label="Lọc Live Tour theo ca">
          <button data-ui-key="u-ceabeb282b2a" data-ui-label-default="Tất cả" type="button" className={shiftFilter === 'all' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('all')} aria-pressed={shiftFilter === 'all'}><UiCustomText uiKey="u-ceabeb282b2a">Tất cả</UiCustomText></button>
          <button data-ui-key="u-c383815f325c" data-ui-label-default="Ca 1" type="button" className={shiftFilter === 'ca1' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('ca1')} aria-pressed={shiftFilter === 'ca1'}><UiCustomText uiKey="u-c383815f325c">Ca 1</UiCustomText></button>
          <button data-ui-key="u-5355598abb00" data-ui-label-default="Ca 2" type="button" className={shiftFilter === 'ca2' ? 'primary-button' : 'secondary-button'} onClick={() => setShiftFilter('ca2')} aria-pressed={shiftFilter === 'ca2'}><UiCustomText uiKey="u-5355598abb00">Ca 2</UiCustomText></button>
          <span className="live-tour-customer-count"><span>Số khách</span><strong>{customerCount}</strong></span>
        </div>
        <UiToolbar data-ui-key="u-e7045504f8eb" className="tour-heading-actions">
          {isAdmin && <button data-ui-key="u-f09ce13c6d92" type="button" className="secondary-button live-tour-combo-approval-button" onClick={() => openModal('combo_approvals')} disabled={Boolean(actionBusy)}>Duyệt bán combo{pendingComboSaleRequests.length ? ` (${pendingComboSaleRequests.length})` : ''}</button>}
          {privilegedLiveTourRole && canPayment && <button data-ui-key="u-6266ab37be87" data-ui-label-default="Thanh toán nhanh" type="button" className="secondary-button" onClick={() => openModal('quick_checkout', { rowIds: [], defaults: { checkout_source: 'manual' } })} disabled={Boolean(actionBusy)}><UiCustomText uiKey="u-6266ab37be87">Thanh toán nhanh</UiCustomText></button>}
          {privilegedLiveTourRole && canPending && <button data-ui-key="u-34da7924df02" type="button" className="secondary-button" onClick={() => openWorkspacePanel('pending')}>Hóa đơn chờ thanh toán{allPendingPayments.length ? ` (${allPendingPayments.length})` : ''}</button>}
          {privilegedLiveTourRole && canPaidInvoiceView && <button data-ui-key="u-472991dccda4" data-ui-label-default="Hóa đơn đã thanh toán" type="button" className="secondary-button" onClick={() => openWorkspacePanel('invoices')}><UiCustomText uiKey="u-472991dccda4">Hóa đơn đã thanh toán</UiCustomText></button>}
          {privilegedLiveTourRole && canReports && <button data-ui-key="u-526d6f86e6a4" data-ui-label-default="Báo cáo" type="button" className="secondary-button" onClick={() => openWorkspacePanel('reports')}><UiCustomText uiKey="u-526d6f86e6a4">Báo cáo</UiCustomText></button>}
          {privilegedLiveTourRole && canCustomers && <button data-ui-key="u-29cfad1ad280" data-ui-label-default="Khách hàng" type="button" className="secondary-button" onClick={() => openWorkspacePanel('customers')}><UiCustomText uiKey="u-29cfad1ad280">Khách hàng</UiCustomText></button>}
          {privilegedLiveTourRole && canViewComboPackages && <button data-ui-key="u-a7223a00bd17" data-ui-label-default="Gói Combo" type="button" className="secondary-button" onClick={() => { setComboLookupSearch(''); setComboLookupOpen(true) }}><Search size={16}/><UiCustomText uiKey="u-a7223a00bd17"> Gói Combo</UiCustomText></button>}
          <button data-ui-key="u-7cbe5ea7ed62" data-ui-label-default="Mở tab mới" type="button" className="secondary-button live-tour-desktop-only" onClick={openLiveTourInNewTab}><ExternalLink size={16}/><UiCustomText uiKey="u-7cbe5ea7ed62"> Mở tab mới</UiCustomText></button>
          {canExport && <button data-ui-key="u-8063318dcfcb" data-ui-label-default="Copy B.Tua" type="button" className="secondary-button live-tour-desktop-only" disabled={Boolean(actionBusy)} onClick={copyBoardImage}><ClipboardCopy size={16}/><UiCustomText uiKey="u-8063318dcfcb"> Copy B.Tua</UiCustomText></button>}
          <button data-ui-key="u-7859407699f6" data-ui-label-default="Làm mới" type="button" className="secondary-button" onClick={() => load(true)} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''}/><UiCustomText uiKey="u-7859407699f6"> Làm mới</UiCustomText></button>
        </UiToolbar>
      </div>
      {error && <div className="error-box">{error}</div>}
      {notice && notice !== 'Đã cập nhật Live Tour.' && <div className="setup-note">{notice}</div>}
      <div className="live-tour-sr-only" role="status" aria-live="polite" aria-atomic="true">
        {pendingReminder && <span key={pendingReminder.id}>{pendingReminder.text}</span>}
      </div>
      {data.countdown_error && <div className="warning-box">Countdown Live Tour: {data.countdown_error}</div>}
      <div className="tour-control-layout">
        <div className="metric-grid small tour-metrics">{metrics.map(({ key, label, value, className }) => <button data-ui-key="u-0df4cbaff447" type="button" className={`metric-card tour-metric-card ${className} ${activeFilter === key ? 'active' : ''}`.trim()} onClick={() => chooseFilter(key)} aria-pressed={activeFilter === key} title={key === 'all' ? 'Xếp theo TG bắt đầu thực hiện từ sớm đến muộn' : key === 'finishing' ? 'Ưu tiên Đang rảnh và Sắp xong khi cùng TG bắt đầu thực hiện' : `Ưu tiên ${label} khi cùng TG bắt đầu thực hiện`} key={key}><span>{label}</span><strong>{value}</strong></button>)}</div>
      </div>
      <section data-ui-key="u-997a66e64b4b" className="panel tour-table-panel tour-room-table-panel">
        <div className={`tour-room-panel ${roomSegment}`}>
          <div data-ui-key="u-61656593968f" className="tour-room-panel-head"><div data-ui-key="u-461ade8ef586" className="tour-room-panel-title" aria-label={`${availableRoomCount} phòng đang trống`}>{roomSegment === 'vip' ? <Crown size={16}/> : roomSegment === 'standard' ? <DoorOpen size={16}/> : <LayoutGrid size={16}/>} {availableRoomCount} P.Trống</div>
            <div className="tour-room-segment-buttons" role="group" aria-label="Chọn phân khúc phòng">
              <button data-ui-key="u-449d2ecbc358" type="button" className={`tour-room-segment-button all ${roomSegment === 'all' ? 'active' : ''}`} onClick={() => { setRoomSegment('all'); setSelectedRoomKey(''); setRoomFilterIds(new Set()); setSelectedIds(new Set()); setEmployeePickId(''); setEmployeeSearch(''); setActiveFilter('all') }} aria-pressed={roomSegment === 'all'}><LayoutGrid size={18}/><span>TẤT CẢ</span></button>
              <button data-ui-key="u-b3bd7e8a9cd4" type="button" className={`tour-room-segment-button standard ${roomSegment === 'standard' ? 'active' : ''}`} onClick={() => { setRoomSegment('standard'); setSelectedRoomKey('') }} aria-pressed={roomSegment === 'standard'}><DoorOpen size={20}/><span>TIÊU CHUẨN</span></button>
              <button data-ui-key="u-0bc2c5fd701b" type="button" className={`tour-room-segment-button vip ${roomSegment === 'vip' ? 'active' : ''}`} onClick={() => { setRoomSegment('vip'); setSelectedRoomKey('') }} aria-pressed={roomSegment === 'vip'}><Crown size={20}/><span>VIP</span></button>
            </div>
            <div className="tour-room-share-tools" role="group" aria-label="Sao chép và chia sẻ nhân viên đã chọn">
              <span className="tour-room-segment-button tour-room-share-control"><span>{selectedRoomKey ? `${areaLabel(selectedRoom)} · ${selectedRoomRecords.length} nhân viên` : `Đã chọn ${selectedIds.size} nhân viên`}</span></span>
              <button data-ui-key="u-d35850857f8b" type="button" className="tour-room-segment-button tour-room-share-control" onClick={copySelectedSummary}><ClipboardCopy size={14}/><span>Sao chép</span></button>
              <button data-ui-key="u-7ad8ab09af4b" type="button" className="tour-room-segment-button tour-room-share-control" onClick={shareSelectedSummary}><Share2 size={14}/><span>Chia sẻ</span></button>
            </div>
          </div>
          <div className="tour-room-grid" style={{ '--room-columns': Math.max(1, Math.ceil(displayedRooms.length / 2)) }}>
            {displayedRooms.map((room) => {
              const key = areaKey(room)
              const records = roomRecords.get(key) || []
              const record = pickRoomRecord(records, remainingColumn)
              const available = availableRoomKeys.has(key)
              const occupied = occupiedRoomKeys.has(key)
              const countdown = roomCountdown(record, remainingColumn, clockMs, available, occupied)
              const hasPrivateService = records.some((item) => item._private_service || isPrivateService(cellValue(item, serviceColumn)))
              return <div data-room-density={Math.min(records.length, 6)} className={`tour-room-card ${isVipArea(room) ? 'vip' : 'standard'} state-${roomState(record, available, clockMs)} ${hasPrivateService ? 'has-private-service' : records.length ? 'has-standard-service' : ''} ${selectedRoomKey === key ? 'selected' : ''} ${searchedRoomKeys.has(key) ? 'search-match' : ''}`.trim()} key={key}>
                <button data-ui-key="u-4d7d18caf42a" type="button" className="tour-room-booking-button"
                  onClick={() => { const active = records.filter((item) => hasGroup(item, 'waiting') || hasGroup(item, 'doing')); const ids = new Set(active.map((item) => stableEmployeeId(item)).filter(Boolean)); setSelectedRoomKey(key); setRoomFilterIds(ids); setSelectedIds(ids); setEmployeePickId(''); setEmployeeSearch(''); setActiveFilter('all') }}
                  onDoubleClick={() => { if (canBook && !actionBusy) { setError(''); setBookingContext({ roomLabel: areaLabel(room), roomGroup: key }) } }}
                  title="Bấm một lần để lọc nhân viên trong phòng; bấm đúp để đặt lịch" aria-expanded={selectedRoomKey === key}>
                <div data-ui-key="u-31b005c068e3" className="tour-room-card-head"><strong>{areaLabel(room)}</strong><span className="tour-room-type">{areaKind(room) === 'table' ? 'BÀN' : areaKind(room) === 'bed' ? 'GIƯỜNG' : isVipArea(room) ? 'VIP' : 'STANDARD'}</span></div>
                <div className="tour-room-customer-count">{records.filter((item) => hasGroup(item, 'doing') || hasGroup(item, 'waiting')).length} khách</div>
                <div className="tour-room-countdown"><Clock3 size={16}/><span className={countdown === 'Đã hết giờ' ? 'tour-room-countdown-expired' : countdown === 'Đang trống' ? 'tour-room-countdown-empty' : /^(Còn|Đang chờ)/.test(countdown) ? 'tour-room-countdown-label' : undefined}>{countdown}</span></div>
                {records.length ? <div className="tour-room-staff">{records.map((item, index) => <div key={recordId(item, index)}>{cellValue(item, employeeColumn)}</div>)}</div> : <div className="tour-room-meta">{available ? 'Sẵn sàng nhận khách' : 'Chưa có nhân viên'}</div>}
                {hasPrivateService && <span className="tour-room-private-badge" aria-label="Dịch vụ phòng riêng">PR</span>}
                </button>
                {roomServiceActions(room)}
              </div>
            })}
            {!displayedRooms.length && <div className="tour-room-empty">Chưa có dữ liệu phòng.</div>}
          </div>
          {selectedRoomKey && selectedRoom && <div className={`tour-room-detail ${areaKey(selectedRoom) === '19' ? 'vip-19' : ''}`.trim()} role="region" aria-label={`Chi tiết ${areaLabel(selectedRoom)}`}>
            <div className="tour-room-detail-head"><strong>{areaLabel(selectedRoom)} · Danh sách nhân viên</strong>{roomServiceActions(selectedRoom)}<small>{selectedRoomRecords.length} nhân viên · Bấm đúp ô phòng để đặt lịch</small><button data-ui-key="u-485d6567b157" type="button" className="text-button" aria-label="Đóng chi tiết phòng" onClick={() => setSelectedRoomKey('')}><X size={14}/></button></div>
            {selectedRoomRecords.length ? <div className="tour-room-detail-list">{selectedRoomRecords.map((item, index) => {
              const employee = cellValue(item, employeeColumn) || 'Chưa có tên nhân viên'
              const service = cellValue(item, serviceColumn) || 'Chưa có dịch vụ'
              return <div className="tour-room-detail-row" key={`${recordId(item, index)}:${index}`}><div className="tour-room-detail-person"><button data-ui-key="u-a9a6e1b65dc3" type="button" className="text-button" disabled={!canOperate} onClick={() => openEmployeeAndShift(item, index)}><strong title={employee}>{employee}</strong></button>{employeeServiceActions(item)}</div><span title={service}>{service}</span></div>
            })}</div> : <div className="tour-room-detail-empty">Phòng đang trống, chưa có nhân viên và dịch vụ.</div>}
          </div>}
        </div>
        <div className="tour-quick-tools">
          <LiveTourSearchSelect className="tour-employee-search" hideLabel label="Tìm nhanh tên nhân viên" placeholder="Tìm và chọn nhân viên…" emptyLabel="Tất cả nhân viên"
            value={employeePickId} searchValue={employeeSearch}
            filterOption={(option, query) => searchTextMatches(option.label, query)}
            options={shiftRecords.map((record) => ({ value: stableEmployeeId(record), label: cellValue(record, employeeColumn), detail: `${cellValue(record, findColumn(columns, ['VAO CA']))} · ${cellValue(record, statusColumn) || 'Sẵn sàng'}` }))}
            onSearch={(query) => { setEmployeeSearch(query); if (employeePickId) setSelectedIds(new Set()); setEmployeePickId('') }}
            onChange={(id) => { setSelectedRoomKey(''); const record = shiftRecords.find((item) => stableEmployeeId(item) === id); setEmployeePickId(id); setEmployeeSearch(record ? cellValue(record, employeeColumn) : ''); setSelectedIds(new Set(id ? [id] : [])); setWeeklyShiftOpen(Boolean(id)) }}/>
          {canEditAppointment && appointmentEditor(appointmentTarget, true)}
          <div className="live-tour-shift-controls">{isAdmin && <div className="tour-shift-filter" role="group" aria-label="Xếp ca nhân viên đã chọn">{['Ca 1', 'Ca 2'].map((shift) => <button data-ui-key="u-41489b1c782e" type="button" key={shift} className="secondary-button" title={`${shift}: ghi đè ca tự động đến hết hôm nay`} disabled={selectedIds.size !== 1 || Boolean(actionBusy)} onClick={() => runSingleSelected('set_shift', { shift })}>{shift}</button>)}</div>}<div className="live-tour-weekly-shift" onMouseEnter={() => setWeeklyShiftOpen(true)} onMouseLeave={() => setWeeklyShiftOpen(false)}><button data-ui-key="u-a5427bd006ec" type="button" className="live-tour-weekly-shift-button" onClick={() => setWeeklyShiftOpen(current => !current)} aria-expanded={weeklyShiftOpen}><span className="weekly-desktop">CA TUẦN NÀY{selectedWeeklyShift ? ` · ${selectedWeeklyShift.toUpperCase()}` : ''}</span><span className="weekly-mobile">Ca tuần này{selectedWeeklyShift ? ` · ${selectedWeeklyShift}` : ''}</span></button>{weeklyShiftOpen && <div className="live-tour-weekly-shift-popover" role="dialog" aria-label="Ca tuần này"><strong>Ca tuần này · {weeklyShiftPlan.range}</strong>{selectedWeeklyRows.length > 0 && <div className="weekly-shift-group weekly-shift-selected"><b>Nhân viên đã chọn</b>{selectedWeeklyRows.map(row => <span key={row.id || row.name}>{row.name} — <strong>{row.current}</strong>{row.fixed ? ' · không tự đổi' : <> → tuần sau <strong>{row.next}</strong></>}</span>)}</div>}{['Ca 1','Ca 2'].map(shift => { const members = weeklyShiftPlan.rows.filter(row => !row.fixed && row.current === shift); return <div key={shift} className="weekly-shift-group"><b>{shift}: {members.length ? members.map(row => row.name).join(', ') : '—'}</b>{members.map(row => <span key={row.id || row.name}>{row.name} — <strong>{row.current}</strong> → tuần sau <strong>{row.next}</strong></span>)}</div>})}<div className="weekly-shift-group"><b>Cố định: {weeklyShiftPlan.rows.filter(row => row.fixed).map(row => row.name).join(', ') || '—'}</b>{weeklyShiftPlan.rows.filter(row => row.fixed).map(row => <span key={row.id || row.name}>{row.name} — <strong>{row.current}</strong> · không tự đổi</span>)}</div>{weeklyShiftPlan.rows.some(row => !row.fixed && !['Ca 1','Ca 2'].includes(row.current)) && <div className="weekly-shift-group"><b>Chưa xếp / khác</b>{weeklyShiftPlan.rows.filter(row => !row.fixed && !['Ca 1','Ca 2'].includes(row.current)).map(row => <span key={row.id || row.name}>{row.name} — {row.current}</span>)}</div>}</div>}</div></div>
          {isAdmin && <div className="live-tour-admin-controls-toggle">
            <button data-ui-key="u-72d4dc1bc8b9" type="button" className="secondary-button" aria-expanded={adminControlsVisible} aria-controls="live-tour-admin-controls" onClick={() => setAdminControlsVisible((visible) => !visible)}>
              {adminControlsVisible ? 'Ẩn điều khiển' : 'Hiện điều khiển'}
            </button>
          </div>}
        </div>
        {(!isAdmin || adminControlsVisible) && <section data-ui-key="u-129d81667cc2" id="live-tour-admin-controls" className={`panel live-tour-operator live-tour-controls ${privilegedLiveTourRole ? '' : 'live-tour-management-hidden'}`} aria-label="Điều khiển">
          <div className="live-tour-controls-grid">
            <UiToolbar data-ui-key="u-0829e513d224" className="live-tour-controls-actions" role="group" aria-label="Bảng điều khiển Live Tour">
              <button data-ui-key="u-81d78ea14816" data-ui-label-default="Cập nhật lịch nghỉ" type="button" className="secondary-button live-tour-mobile-sync-hidden" disabled={!canOperate || Boolean(actionBusy)} onClick={() => executeAction('sync_daily_status', {}, [])}><UiCustomText uiKey="u-81d78ea14816">Cập nhật lịch nghỉ</UiCustomText></button>
              <button data-ui-key="u-2acb2fc50ca7" data-ui-label-default="Đi làm" type="button" className="secondary-button" disabled={!canOperate || !selectedIds.size || Boolean(actionBusy)} onClick={() => runSelected('set_work_status', { status: 'Đi làm' })}><UiCustomText uiKey="u-2acb2fc50ca7">Đi làm</UiCustomText></button>
              <button data-ui-key="u-73463df1c94c" data-ui-label-default="Nghỉ phép" type="button" className="secondary-button" disabled={!canOperate || !selectedIds.size || Boolean(actionBusy)} onClick={() => runSelected('set_work_status', { status: 'Nghỉ phép' })}><UiCustomText uiKey="u-73463df1c94c">Nghỉ phép</UiCustomText></button>
              <button data-ui-key="u-6c5e0477915b" data-ui-label-default="Hủy Booking" type="button" className="secondary-button danger-button" disabled={!canOperate || !selectedIds.size || Boolean(actionBusy)} onClick={cancelSelectedBooking}><UiCustomText uiKey="u-6c5e0477915b">Hủy Booking</UiCustomText></button>
              {isAdmin && <button data-ui-key="u-41e9cb451151" data-ui-label-default="Hủy Thực hiện" type="button" className="secondary-button danger-button" disabled={selectedIds.size !== 1 || !hasGroup(selectedRecords[0], 'doing') || Boolean(actionBusy)} onClick={() => { if (window.confirm('Hủy lệnh Thực hiện và đưa booking về trạng thái Đang chờ để tính giờ lại?')) void runSingleSelected('restart_booking') }}><UiCustomText uiKey="u-41e9cb451151">Hủy Thực hiện</UiCustomText></button>}
              {data.payment_settings?.employee_change_enabled !== false && <button data-ui-key="u-0d5c922fb38c" data-ui-label-default="Đổi nhân viên" type="button" className="secondary-button" disabled={!canOperate || selectedIds.size !== 1 || !canChangeEmployee(selectedRecords[0], clockMs) || Boolean(actionBusy)} onClick={() => openModal('change_employee', { rowIds: [...selectedIds], revision: data.revision })}><UiCustomText uiKey="u-0d5c922fb38c">Đổi nhân viên</UiCustomText></button>}
              <button data-ui-key="u-efe4ccaa9ecc" data-ui-label-default="Nghỉ giữa ca" type="button" className="secondary-button" disabled={!canOperate || !selectedIds.size || Boolean(actionBusy)} onClick={() => runSelected('start_break')}><PauseCircle size={13}/><UiCustomText uiKey="u-efe4ccaa9ecc"> Nghỉ giữa ca</UiCustomText></button>
              <button data-ui-key="u-43d8b63bda4a" data-ui-label-default="Kết thúc nghỉ" type="button" className="secondary-button" disabled={!(canEndBreak || canOperate) || !selectedIds.size || (!canEndBreak && selectedRecords.some(row => row._break_from_attendance && row._attendance_break_active)) || Boolean(actionBusy)} onClick={() => runSelected('end_break')}><Play size={13}/><UiCustomText uiKey="u-43d8b63bda4a"> Kết thúc nghỉ</UiCustomText></button>
              <button data-ui-key="u-ee4ca793f271" data-ui-label-default="Xuống cuối" type="button" className="secondary-button live-tour-mobile-reorder-hidden" disabled={!canReorder || selectedIds.size !== 1 || Boolean(actionBusy)} onClick={() => runSingleSelected('admin_reorder', { direction: 'bottom', steps: 1 })}><UiCustomText uiKey="u-ee4ca793f271">Xuống cuối</UiCustomText></button>
              <button data-ui-key="u-6e0ea138483a" data-ui-label-default="Lên đầu" type="button" className="secondary-button live-tour-mobile-reorder-hidden" disabled={!canReorder || selectedIds.size !== 1 || Boolean(actionBusy)} onClick={() => runSingleSelected('admin_reorder', { direction: 'top', steps: 1 })}><UiCustomText uiKey="u-6e0ea138483a">Lên đầu</UiCustomText></button>
              {canReorder ? <input type="number" aria-label="STT mới" placeholder="STT" min="1" step="1" value={targetPosition} onChange={event => setTargetPosition(event.target.value)}/> : <span/>}
              <button data-ui-key="u-e588e4f95ca6" data-ui-label-default="Đổi STT" type="button" className="secondary-button" disabled={!canReorder || selectedIds.size !== 1 || Boolean(actionBusy) || !Number.isInteger(Number(targetPosition)) || Number(targetPosition) < 1} onClick={() => runSingleSelected('admin_reorder', { direction: 'position', position: Number(targetPosition) })}><UiCustomText uiKey="u-e588e4f95ca6">Đổi STT</UiCustomText></button>
              <select className="live-tour-mobile-reorder-hidden" value={reorderSteps} onChange={(event) => setReorderSteps(event.target.value)} aria-label="Số vị trí di chuyển"><option value="1">1 dòng</option><option value="3">3 dòng</option><option value="5">5 dòng</option></select>
              <button data-ui-key="u-b17eb0227e1e" type="button" className="secondary-button live-tour-mobile-reorder-hidden" disabled={!canReorder || selectedIds.size !== 1 || Boolean(actionBusy)} onClick={() => runSingleSelected('admin_reorder', { direction: 'up', steps: Number(reorderSteps) })}>Lên {reorderSteps}</button>
              <button data-ui-key="u-4f814f051f53" type="button" className="secondary-button live-tour-mobile-reorder-hidden" disabled={!canReorder || selectedIds.size !== 1 || Boolean(actionBusy)} onClick={() => runSingleSelected('admin_reorder', { direction: 'down', steps: Number(reorderSteps) })}>Xuống {reorderSteps}</button>
            </UiToolbar>
          </div>
        </section>}
      </section>
    </div>

    <section data-ui-key="u-7a0401d60a37" className="panel tour-table-panel tour-records-panel">
      <div className="responsive-data-table tour-table" tabIndex="0" aria-label="Danh sách Live Tour"><table data-ui-key="u-ecfc5f45a158"><thead><tr>{appearanceTableColumns.map((entry) => entry.kind === 'select'
        ? <th data-ui-key="u-60b4eb9caa75" className="live-tour-select-col" data-appearance-key="Ô chọn" key="__select"><input type="checkbox" checked={allDisplayedSelected} onChange={toggleDisplayed} aria-label="Chọn tất cả nhân viên đang hiển thị"/></th>
        : entry.kind === 'actions'
          ? <th data-ui-key="u-231630a4deef" data-ui-label-default="Thao tác" className="live-tour-actions-col" data-appearance-key="Thao tác" key="__actions"><UiCustomText uiKey="u-231630a4deef">Thao tác</UiCustomText></th>
          : <th data-ui-key="u-afa8220f3244" className={columnClass(entry.column)} data-appearance-key={entry.key} key={entry.column}>{entry.column}</th>)}</tr></thead><tbody>{displayedRecords.map((item, index) => {
        const id = recordId(item, index)
        return <tr className={rowClass(item, selectedIds.has(id), data.payment_settings?.shift_ready_times, clockMs)} key={id} onClick={(event) => { if (!event.target.closest('button,input,a,select')) toggleRow(id) }}>{appearanceTableColumns.map((entry) => {
          if (entry.kind === 'select') return <td className="live-tour-select-col" data-appearance-key="Ô chọn" key="__select"><input type="checkbox" checked={selectedIds.has(id)} onChange={() => toggleRow(id)} aria-label={`Chọn ${cellValue(item, employeeColumn)}`}/></td>
          if (entry.kind === 'actions') return <td className="live-tour-actions-col" data-appearance-key="Thao tác" key="__actions">{employeeServiceActions(item)}</td>
          const column = entry.column
          return <td className={columnClass(column)} data-appearance-key={entry.key} key={column}>{column === employeeColumn ? <button data-ui-key="u-b1ca0bd563d7" type="button" className="text-button" title={String(item[column] ?? '')} disabled={!canOperate && !canPayment && !canBook} onClick={() => openEmployeeAndShift(item, index)}>{String(item[column] ?? '')}</button> : column === appointmentColumn && canEditAppointment ? appointmentEditor(item) : column === sttColumn(columns) ? String(item[column] ?? '') : (column === statusColumn && hasGroup(item, 'doing') ? 'Thực hiện' : String(breakCellValue(item, column, clockMs)))}</td>
        })}</tr>
      })}</tbody></table></div>
      {!busy && !displayedRecords.length && <div className="setup-note">Không có nhân viên phù hợp với ca/bộ lọc đang chọn.</div>}
    </section>
    </div>

    {asArray(data.retained_assignments).length > 0 && <section data-ui-key="u-976bfc6719af" className="tour-roster-retained"><strong>Phiên còn mở ngoài danh sách Leader/Nhân viên</strong><p>Hoàn tất các phiên cũ bên dưới; các tài khoản này không nhận booking mới.</p>{data.retained_assignments.map((worker) => <div key={worker.id}><span>{worker.name} · {worker.service || 'Nghỉ giữa ca'} · {worker.room}</span>{worker.break_started_at ? <button data-ui-key="u-1cf4a4467ba4" data-ui-label-default="Kết thúc nghỉ" type="button" className="secondary-button" disabled={!(canEndBreak || canOperate) || Boolean(actionBusy)} onClick={() => executeAction('end_break', { employee_id: worker.id }, [])}><UiCustomText uiKey="u-1cf4a4467ba4">Kết thúc nghỉ</UiCustomText></button> : normalizedColumn(worker.status) === 'CHO THANH TOAN' ? <button data-ui-key="u-8ff3680113d1" data-ui-label-default="Thanh toán" type="button" className="secondary-button" disabled={!canPayment || Boolean(actionBusy)} onClick={async () => { const result = await executeAction('move_pending', { employee_id: worker.id }, []); if (result) openModal('checkout', { item: result.result.pending, rowIds: [] }) }}><UiCustomText uiKey="u-8ff3680113d1">Thanh toán</UiCustomText></button> : <button data-ui-key="u-53ea2191b50e" data-ui-label-default="Xử lý phiên" type="button" className="secondary-button" disabled={!canOperate || Boolean(actionBusy)} onClick={() => { setError(''); setBookingContext({ employeeId: worker.id }) }}><UiCustomText uiKey="u-53ea2191b50e">Xử lý phiên</UiCustomText></button>}</div>)}</section>}
    <section data-ui-key="u-c6f7f7ebdf77" className={`panel live-tour-operator live-tour-workspace ${privilegedLiveTourRole ? '' : 'live-tour-management-hidden'}`} ref={workspaceRef}>
      <UiToolbar data-ui-key="u-34a5893ab8cb" className="live-tour-panel-tabs" role="tablist" aria-label="Không gian vận hành Live Tour">
        {PANEL_TABS.map(([key, label]) => {
          const disabled = !({ pending: canPending, invoices: canPaidInvoiceView, customers: canCustomers, reports: canReports, history: canHistory || canBackup, catalog: canAdmin })[key]
          return <button data-ui-key="u-55cddf9f06ee" type="button" role="tab" disabled={disabled} aria-selected={activePanel === key} className={activePanel === key ? 'primary-button' : 'secondary-button'} onClick={() => openWorkspacePanel(key)} key={key}>{label}{key === 'pending' && allPendingPayments.length ? ` (${allPendingPayments.length})` : ''}</button>
        })}
      </UiToolbar>
      {['pending', 'invoices', 'reports', 'history'].includes(activePanel) && <LiveTourFilters
        value={listFilters}
        onChange={setListFilters}
        rows={activePanel === 'pending' ? allPendingPayments : activePanel === 'invoices' ? asArray(data.state?.invoices) : activePanel === 'reports' ? allReports : [...asArray(data.customer_changes), ...asArray(data.pending_changes), ...asArray(data.invoice_changes), ...asArray(data.break_events), ...asArray(data.backups)]}
        customers={customers}
        services={services}
      />}
      {!activePanel && <div className="live-tour-empty">Tài khoản đang ở chế độ chỉ xem Bảng tua. Liên hệ Admin nếu cần quyền thanh toán, báo cáo hoặc quản trị.</div>}

      {activePanel === 'pending' && canPending && <div data-ui-key="u-5aae89cf5f13" className="live-tour-panel-body" id="live-tour-pending-panel" role="tabpanel" aria-label="Hóa đơn chờ thanh toán">
        <UiToolbar data-ui-key="u-4ccbed71d695" className="live-tour-panel-toolbar"><h2>HÓA ĐƠN CHỜ THANH TOÁN <span className="live-tour-invoice-count" aria-label={`${pendingPayments.length} hóa đơn chờ thanh toán`}>{pendingPayments.length}</span></h2><UiToolbar data-ui-key="u-bc66c94c498e" className="live-tour-panel-toolbar-actions"><button data-ui-key="u-26b22989fcab" data-ui-label-default="Xuất chờ thanh toán" type="button" className="secondary-button" disabled={!canExportKind('pending')} onClick={() => exportData('pending')}><Download size={13}/><UiCustomText uiKey="u-26b22989fcab"> Xuất chờ thanh toán</UiCustomText></button></UiToolbar></UiToolbar>
        {pendingPayments.length ? <div data-ui-key="u-ee50e97f2347" className="live-tour-card-grid">{pendingPayments.map((item, index) => {
          const id = String(item?._id ?? item?.id ?? '')
          const entries = asArray(item?.entries)
          const cardEntries = entries.length ? entries : [{ employee_name: item.employee_name, room: item.room, service: item.service || item.services, booked_at: item.booked_at, started_at: item.started_at }]
          return <article className="live-tour-data-card" key={itemId(item, index)}>
            {cardEntries.map((entry, entryIndex) => <strong key={entryIndex}>{entry.employee_name || 'Chưa có nhân viên'} – {entry.service || 'Chưa ghi dịch vụ'} – {entry.room || 'Chưa có phòng'}</strong>)}
            <small>{item?.customer_name || item?.customer || 'Khách lẻ'} {item?.customer_phone || item?.phone ? `· ${item?.customer_phone || item?.phone}` : ''}</small>
            {cardEntries.map((entry, entryIndex) => <small key={entryIndex}>Booking: {bookingTimeLabel(entry.booked_at || item.effective_at || item.booked_at || item.created_at)} · Thực hiện: {bookingTimeLabel(entry.started_at)}</small>)}
            <UiToolbar data-ui-key="u-5c381f1b69d9" className="live-tour-card-actions"><button data-ui-key="u-d3f310ed4bc5" data-ui-label-default="Thanh toán" type="button" className="primary-button" disabled={!canPayment || Boolean(actionBusy)} onClick={() => openModal('checkout', { item, rowIds: [], defaults: { pending_id: id } })}><UiCustomText uiKey="u-d3f310ed4bc5">Thanh toán</UiCustomText></button>
              {canInvoiceView && <button data-ui-key="u-7e13d63908b4" data-ui-label-default="Xem hóa đơn" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => { setError(''); setPendingContext({ item, mode: 'view', revision: data.revision }) }}><UiCustomText uiKey="u-7e13d63908b4">Xem hóa đơn</UiCustomText></button>}
              {canInvoiceEdit && <button data-ui-key="u-b9839ff6697d" data-ui-label-default="Sửa hóa đơn" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => { setError(''); setPendingContext({ item, mode: 'edit', revision: data.revision }) }}><UiCustomText uiKey="u-b9839ff6697d">Sửa hóa đơn</UiCustomText></button>}
              {canInvoiceDelete && <button data-ui-key="u-c9f44b19c631" data-ui-label-default="Xóa hóa đơn" type="button" className="secondary-button danger-button" disabled={Boolean(actionBusy)} onClick={() => { setError(''); setPendingContext({ item, mode: 'delete', revision: data.revision }) }}><Trash2 size={14}/><UiCustomText uiKey="u-c9f44b19c631"> Xóa hóa đơn</UiCustomText></button>}
            </UiToolbar>
          </article>
        })}</div> : <div className="live-tour-empty">{canInvoiceView ? 'Không có hóa đơn chờ thanh toán.' : `Có ${data.pending_count || 0} phiếu. Cần quyền Xem hóa đơn chờ thanh toán để mở chi tiết.`}</div>}
      </div>}

      {activePanel === 'invoices' && canPaidInvoiceView && <div data-ui-key="u-fc3f9e651c00" className="live-tour-panel-body">
        <UiToolbar data-ui-key="u-be7b585d85e7" className="live-tour-panel-toolbar"><h2>HÓA ĐƠN ĐÃ THANH TOÁN <span className="live-tour-invoice-count" aria-label={`${visibleInvoices.length} hóa đơn đã thanh toán`}>{visibleInvoices.length}</span></h2></UiToolbar>
        <p>Hiển thị hóa đơn còn hiệu lực theo bộ lọc. Hủy hóa đơn được lưu đối soát, không xóa bản gốc và không tự hoàn tiền qua ngân hàng/thẻ.</p>
        <div data-ui-key="u-3f377cb8013a" className="live-tour-card-grid">{visibleInvoices.slice().reverse().map((invoice) => <article className="live-tour-data-card" key={invoice.id}>
          {(asArray(invoice.entries).length ? invoice.entries : [{ employee_name: invoice.employee_name, service: invoice.service || invoice.services, room: invoice.room }]).map((entry, entryIndex) => <strong key={entryIndex}>{entry.employee_name || 'Chưa có nhân viên'} – {entry.service || 'Chưa ghi dịch vụ'} – {entry.room || 'Chưa có phòng'}</strong>)}
          <small>{invoice.bill_no} · {invoice.customer_name || 'Khách lẻ'}</small><span>{formatVeraDateTime(invoice.effective_at || invoice.created_at)} · {invoice.payment_method}</span><strong>{formatMoney(invoice.total)}</strong>
          <UiToolbar data-ui-key="u-ec8f18a16bdd" className="live-tour-card-actions"><button data-ui-key="u-6b5193fbdb97" data-ui-label-default="Xem / in hóa đơn" type="button" className="secondary-button" onClick={() => setReceipt({ invoice, autoPrint: false })}><Printer size={14}/><UiCustomText uiKey="u-6b5193fbdb97"> Xem / in hóa đơn</UiCustomText></button>
            {canPaidInvoiceEdit && <button data-ui-key="u-762a5f45f72c" data-ui-label-default="Sửa hóa đơn" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => { setError(''); setPendingContext({ item: invoice, paid: true, mode: 'edit', revision: data.revision }) }}><UiCustomText uiKey="u-762a5f45f72c">Sửa hóa đơn</UiCustomText></button>}
            {canPaidInvoiceDelete && <button data-ui-key="u-3c72d15ad5c9" data-ui-label-default="Xóa / hủy hóa đơn" type="button" className="secondary-button danger-button" disabled={Boolean(actionBusy)} onClick={() => { setError(''); setPendingContext({ item: invoice, paid: true, mode: 'delete', revision: data.revision }) }}><Trash2 size={14}/><UiCustomText uiKey="u-3c72d15ad5c9"> Xóa / hủy hóa đơn</UiCustomText></button>}
          </UiToolbar>
        </article>)}</div>
        {!visibleInvoices.length && <p>Chưa có hóa đơn đã thanh toán còn hiệu lực.</p>}
      </div>}

      {activePanel === 'customers' && canCustomers && <div data-ui-key="u-649716fc4d68" className="live-tour-panel-body">
        <UiToolbar data-ui-key="u-ae8ed624a03d" className="live-tour-panel-toolbar"><h2>KHÁCH HÀNG</h2><UiToolbar data-ui-key="u-ef65687e6300" className="live-tour-panel-toolbar-actions"><button data-ui-key="u-7aaa167545c1" data-ui-label-default="Mua combo cho khách hàng" type="button" className="primary-button" disabled={!canPayment} onClick={() => openModal('combo_purchase', { rowIds: [] })}><Plus size={13}/><UiCustomText uiKey="u-7aaa167545c1"> Mua combo cho khách hàng</UiCustomText></button>{canImportCombo && <button data-ui-key="u-ab651dafd8bd" data-ui-label-default="Nhập combo" type="button" className="secondary-button" onClick={() => openModal('combo_import')}><UiCustomText uiKey="u-ab651dafd8bd">Nhập combo</UiCustomText></button>}<button data-ui-key="u-ef56fb891e1c" data-ui-label-default="Xuất khách hàng" type="button" className="secondary-button" disabled={!canExportKind('customers')} onClick={() => exportData('customers')}><Download size={13}/><UiCustomText uiKey="u-ef56fb891e1c"> Xuất khách hàng</UiCustomText></button></UiToolbar></UiToolbar>
        <label className="live-tour-customer-search"><Search size={14}/><ClearableSearchInput type="search" aria-label="Tìm tên hoặc số điện thoại khách hàng" autoComplete="off" value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} placeholder="Tìm tên hoặc số điện thoại khách hàng…"/></label>
        <div data-ui-key="u-957d44b6b75e" className="live-tour-card-grid" style={{ marginTop: 8 }}>
          {filteredCustomers.map((customer, index) => <article className="live-tour-data-card live-tour-customer-card" role="button" tabIndex="0" aria-label={`Xem lịch sử ${itemLabel(customer, `Khách hàng ${index + 1}`)}`} onClick={(event) => { if (!event.target.closest('button')) void openCustomerHistory(customer) }} onKeyDown={(event) => { if (event.key === 'Enter' && !event.target.closest('button')) void openCustomerHistory(customer) }} key={itemId(customer, index)}>
            <strong>{itemLabel(customer, `Khách hàng ${index + 1}`)}</strong>
            <span>{customer?.phone || 'Chưa có số điện thoại'}</span>
            <small>Số dư combo: {customer?.combo_balance ?? customer?.remaining_tickets ?? customer?.balance ?? 0}</small>
            {customerComboPurchases(customer).map((combo, comboIndex) => <div key={itemId(combo, comboIndex)}><small>{itemLabel(combo)} · còn {combo?.remaining ?? combo?.balance ?? 0}/{combo?.total ?? ''} vé · mua {bookingTimeLabel(combo?.purchased_at || combo?.created_at)}</small>{isAdmin && capabilities.customer_combo_edit && <button data-ui-key="u-50ce352c9444" data-ui-label-default="Sửa combo" className="text-button" onClick={() => { setError(''); setCustomerContext({ customer, purchase: combo, mode: 'edit', revision: data.revision }) }}><UiCustomText uiKey="u-50ce352c9444">Sửa combo</UiCustomText></button>}{capabilities.customer_combo_delete && <button data-ui-key="u-4205e0d3f38a" data-ui-label-default="Xóa combo" className="text-button" onClick={() => { setError(''); setCustomerContext({ customer, purchase: combo, mode: 'delete', revision: data.revision }) }}><UiCustomText uiKey="u-4205e0d3f38a">Xóa combo</UiCustomText></button>}</div>)}
            <UiToolbar data-ui-key="u-77415787e4c3" className="live-tour-card-actions">{capabilities.customers_edit && <button data-ui-key="u-2df061d02fff" data-ui-label-default="Sửa khách hàng" className="secondary-button" onClick={() => { setError(''); setCustomerContext({ customer, mode: 'edit', revision: data.revision }) }}><UiCustomText uiKey="u-2df061d02fff">Sửa khách hàng</UiCustomText></button>}{capabilities.customers_delete && <button data-ui-key="u-cd9355677b53" data-ui-label-default="Xóa khách hàng" className="secondary-button danger-button" onClick={() => { setError(''); setCustomerContext({ customer, mode: 'delete', revision: data.revision }) }}><UiCustomText uiKey="u-cd9355677b53">Xóa khách hàng</UiCustomText></button>}</UiToolbar>
            <UiToolbar data-ui-key="u-be9313da7745" className="live-tour-card-actions"><button data-ui-key="u-91be5cd41cd8" data-ui-label-default="Lịch sử sử dụng" type="button" className="secondary-button" disabled={!canCustomers} onClick={() => openCustomerHistory(customer)}><History size={12}/><UiCustomText uiKey="u-91be5cd41cd8"> Lịch sử sử dụng</UiCustomText></button><button data-ui-key="u-c1b380bd08b6" data-ui-label-default="Mua combo" type="button" className="secondary-button" disabled={!canPayment} onClick={() => openModal('combo_purchase', { item: customer, rowIds: [], defaults: { customer_id: stableCustomerId(customer), customer_name: itemLabel(customer), phone: customer?.phone || customer?.customer_phone || '' } })}><Plus size={12}/><UiCustomText uiKey="u-c1b380bd08b6"> Mua combo</UiCustomText></button></UiToolbar>
          </article>)}
          {!filteredCustomers.length && <div className="live-tour-empty">Không tìm thấy khách hàng phù hợp.</div>}
        </div>
      </div>}

      {activePanel === 'reports' && canReports && <div data-ui-key="u-78fd579b358b" className="live-tour-panel-body">
        <details className="live-tour-catalog-section">
          <summary>Xuất bảng tùy chỉnh</summary>
          <label>Phạm vi nhân viên<select value={customScope} onChange={(event) => setCustomScope(event.target.value)}><option value="displayed">Đang hiển thị</option><option value="selected">Đã chọn</option><option value="all">Tất cả</option></select></label>
          <UiToolbar data-ui-key="u-9fcd2124e9d0" className="live-tour-panel-toolbar-actions"><button data-ui-key="u-045c84dccf85" data-ui-label-default="Chọn tất cả cột" type="button" className="secondary-button" onClick={() => setCustomColumns(null)}><UiCustomText uiKey="u-045c84dccf85">Chọn tất cả cột</UiCustomText></button><button data-ui-key="u-6835ed3633b1" data-ui-label-default="Bỏ chọn cột" type="button" className="secondary-button" onClick={() => setCustomColumns([])}><UiCustomText uiKey="u-6835ed3633b1">Bỏ chọn cột</UiCustomText></button></UiToolbar>
          <div data-ui-key="u-709b75c050c4" className="live-tour-card-grid">{columns.map((column) => <label key={column}><input type="checkbox" checked={(customColumns ?? columns).includes(column)} onChange={(event) => setCustomColumns((previous) => event.target.checked ? columns.filter((item) => item === column || (previous ?? columns).includes(item)) : (previous ?? columns).filter((item) => item !== column))}/>{column}</label>)}</div>
          <button data-ui-key="u-a4134718e40e" data-ui-label-default="Xuất Excel tùy chỉnh" type="button" className="secondary-button" disabled={!canExportKind('custom') || Boolean(actionBusy)} onClick={() => exportData('custom')}><Download size={13}/><UiCustomText uiKey="u-a4134718e40e"> Xuất Excel tùy chỉnh</UiCustomText></button>
          <p>Bộ lọc ngày/giờ báo cáo không áp dụng cho bảng tua hiện tại.</p>
        </details>
        <UiToolbar data-ui-key="u-9c36d2dbb4d9" className="live-tour-panel-toolbar"><h2>BÁO CÁO · DOANH THU · TIỀN TIP</h2><UiToolbar data-ui-key="u-c3776eda40b8" className="live-tour-panel-toolbar-actions">{EXPORT_KINDS.map(([kind, label]) => <button data-ui-key="u-25d830c3b45e" type="button" className="primary-button" disabled={!canExportKind(kind)} onClick={() => exportData(kind)} key={kind}><Download size={13}/> {label}</button>)}<button data-ui-key="u-7c09c9a51c17" data-ui-label-default="Copy B.Tua" type="button" className="primary-button live-tour-desktop-only" disabled={!canExportKind('board') || Boolean(actionBusy)} onClick={copyBoardImage}><ClipboardCopy size={13}/><UiCustomText uiKey="u-7c09c9a51c17"> Copy B.Tua</UiCustomText></button></UiToolbar></UiToolbar>
        <LiveTourRevenueSummary rows={reports} invoiceCount={reportInvoiceCount}/>
        {!reports.length && <div className="live-tour-empty">Chưa có số liệu báo cáo.</div>}
        {reports.length > 0 && <div data-ui-key="u-dc15b1c36418" className="live-tour-card-grid">{reports.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{item?.employee_name || itemLabel(item, `Báo cáo ${index + 1}`)}</strong><span>{item?.service || 'Dịch vụ'} · {formatMoney(item?.total ?? item?.revenue ?? item?.amount)}</span><small>TIP: {formatMoney(item?.tip ?? 0)} · {formatVeraDateTime(item?.effective_at || item?.created_at)}</small>{canPaidInvoiceView && asArray(data.state?.invoices).some((invoice) => invoice.id === item.invoice_id) && <button data-ui-key="u-fdc0ceae7323" data-ui-label-default="Xem / in hóa đơn" type="button" className="secondary-button" onClick={() => setReceipt({ invoice: data.state.invoices.find((invoice) => invoice.id === item.invoice_id), autoPrint: false })}><Printer size={14}/><UiCustomText uiKey="u-fdc0ceae7323"> Xem / in hóa đơn</UiCustomText></button>}</article>)}</div>}
      </div>}

      {activePanel === 'history' && (canHistory || canBackup) && <div data-ui-key="u-65e23a4355d1" className="live-tour-panel-body">
        {canHistory && canCustomers && filteredCustomerChanges.length > 0 && <div className="live-tour-catalog-section"><h3>Lịch sử sửa / xóa khách hàng và combo</h3>{filteredCustomerChanges.slice().reverse().map(change => <details className="live-tour-data-card" key={change.id}><summary>{formatVeraDateTime(change.at)} · {change.actor} · {change.before?.name || change.before?.combo_name}</summary><p>Lý do: {change.reason}</p><p>{change.before?.remaining != null ? `Số vé: ${change.before.remaining} → ${change.after?.deleted_at ? 'Đã xóa' : change.after?.remaining}` : `${change.before?.name} → ${change.after?.deleted_at ? 'Đã xóa' : change.after?.name}`}</p></details>)}</div>}
        {canHistory && <LiveTourInvoiceChanges changes={filteredInvoiceChanges}/>}
        {canHistory && <div className="live-tour-catalog-section">
          <UiToolbar data-ui-key="u-110ca1e95d1c" className="live-tour-panel-toolbar"><h3>LỊCH SỬ NGHỈ GIỮA CA</h3><button data-ui-key="u-79ff49120d1a" data-ui-label-default="Xuất nghỉ giữa ca" type="button" className="secondary-button" disabled={!canExportKind('breaks')} onClick={() => exportData('breaks')}><Download size={13}/><UiCustomText uiKey="u-79ff49120d1a"> Xuất nghỉ giữa ca</UiCustomText></button></UiToolbar>
          <div className="live-tour-history-list">{filteredBreakEvents.slice().reverse().map((event, index) => <article key={event.id || index}>
            <strong>{event.employee_name} · {event.event_type === 'start' ? 'Bắt đầu nghỉ' : 'Vào lại'}</strong>
            <span>{formatVeraDateTime(event.at)} · {event.outcome || 'Định mức 90 phút'}{event.minutes != null ? ` · ${event.minutes} phút` : ''}</span>
            <small>{event.actor}</small>
          </article>)}{!filteredBreakEvents.length && <div className="live-tour-empty">Chưa có lịch sử nghỉ giữa ca trong bộ lọc.</div>}</div>
        </div>}
        <UiToolbar data-ui-key="u-9f2705675a28" className="live-tour-panel-toolbar"><h2>LỊCH SỬ & SAO LƯU</h2><UiToolbar data-ui-key="u-dde9e54568c0" className="live-tour-panel-toolbar-actions">{canBackup && <button data-ui-key="u-7bc66b66d171" data-ui-label-default="Tạo bản sao lưu" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => executeAction('backup', { name: `Backup ${formatVeraDateTime(Date.now())}` }, [])}><History size={13}/><UiCustomText uiKey="u-7bc66b66d171"> Tạo bản sao lưu</UiCustomText></button>}{canHistory && <button data-ui-key="u-24479c9977be" data-ui-label-default="Xuất lịch sử" type="button" className="secondary-button" disabled={!canExportKind('history')} onClick={() => exportData('history')}><Download size={13}/><UiCustomText uiKey="u-24479c9977be"> Xuất lịch sử</UiCustomText></button>}</UiToolbar></UiToolbar>
        {canBackup && <div className="live-tour-catalog-section"><h3>Bản sao lưu</h3>{backups.length ? <div data-ui-key="u-334b0dee496c" className="live-tour-card-grid">{backups.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{itemLabel(item, `Bản sao ${index + 1}`)}</strong><small>{formatVeraDateTime(item?.created_at || item?.timestamp)}</small><UiToolbar data-ui-key="u-e9f0d291335d" className="live-tour-card-actions"><button data-ui-key="u-dacfd97fd33b" data-ui-label-default="Khôi phục" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => { if (window.confirm('Khôi phục bản sao này? Chỉ phục hồi cấu hình/bảng tua khi không còn phiên mở; sổ hóa đơn, vé và lịch sử không bị quay lùi.')) void executeAction('restore', { backup_id: item?._id ?? item?.id }, []) }}><UiCustomText uiKey="u-dacfd97fd33b">Khôi phục</UiCustomText></button></UiToolbar></article>)}</div> : <div className="live-tour-empty">Chưa có bản sao lưu.</div>}</div>}
      </div>}

      {activePanel === 'catalog' && canAdmin && <div data-ui-key="u-c412dc5c7747" className="live-tour-panel-body">
        <UiToolbar data-ui-key="u-07b105a3b9d3" className="live-tour-panel-toolbar"><h2>DANH MỤC LIVE TOUR</h2></UiToolbar>
        {canAdmin && <div className="live-tour-catalog-section">
          <h3>Chuyển phiên quá hạn sang chờ thanh toán</h3>
          <label>Quá giờ dịch vụ ít nhất (phút)<input type="number" min="0" max="1440" step="1" value={expiredGrace} disabled={Boolean(actionBusy)} onChange={(event) => { setExpiredGrace(event.target.value); setExpiredPreview(null) }}/></label>
          <button data-ui-key="u-6e6911625b75" data-ui-label-default="Xem trước phiên quá hạn" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={previewExpired}><UiCustomText uiKey="u-6e6911625b75">Xem trước phiên quá hạn</UiCustomText></button>
          {expiredPreview && <div className="warning-box">
            <strong>{expiredPreview.count} phiên quá hạn từ {expiredPreview.grace_minutes} phút</strong>
            <p>Các phiên được chuyển sang chờ thanh toán; chưa ghi nhận thu tiền.</p>
            <div className="live-tour-history-list">{asArray(expiredPreview.employees).map((item) => <article key={item.employee_id}><strong>{item.employee_name}</strong><span>{item.service} · Phòng {item.room}</span><small>Hết giờ: {item.ends_at}</small></article>)}</div>
            {expiredPreview.base_revision !== data.revision && <p>Bảng đã thay đổi. Hãy xem trước lại.</p>}
            <button data-ui-key="u-3eeac560ed56" type="button" className="primary-button" disabled={Boolean(actionBusy) || !expiredPreview.count || expiredPreview.base_revision !== data.revision} onClick={confirmExpired}>Xác nhận chuyển {expiredPreview.count} phiên</button>
            <button data-ui-key="u-00594babb6dd" data-ui-label-default="Hủy" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => setExpiredPreview(null)}><UiCustomText uiKey="u-00594babb6dd">Hủy</UiCustomText></button>
          </div>}
        </div>}
        {!canManageCatalog && <div className="live-tour-empty">Chỉ Admin hoặc tài khoản được cấp quyền mới được sửa danh mục.</div>}
        {canAdmin && <LiveTourPaymentSettings key={JSON.stringify(data.payment_settings)} value={data.payment_settings} busy={Boolean(actionBusy)} onSave={(payload) => executeAction('payment_settings_update', payload, [])}/>}
        {canManageCatalog && <>
          <div className="live-tour-catalog-section"><UiToolbar data-ui-key="u-d9d3789a8ef4" className="live-tour-panel-toolbar"><h3>Phòng / giường</h3><button data-ui-key="u-ce823dd69517" data-ui-label-default="Thêm phòng" type="button" className="secondary-button" onClick={() => openModal('room_upsert')}><Plus size={12}/><UiCustomText uiKey="u-ce823dd69517"> Thêm phòng</UiCustomText></button></UiToolbar><div data-ui-key="u-30db9a0dfabf" className="live-tour-card-grid">{catalogRooms.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{roomLabel(item)}</strong><small>{isVipRoom(item) ? 'VIP' : 'Standard'}</small><UiToolbar data-ui-key="u-f31c06ec5c21" className="live-tour-card-actions"><button data-ui-key="u-de2a37e5a5c1" data-ui-label-default="Sửa" type="button" className="secondary-button" onClick={() => openModal('room_upsert', { item })}><UiCustomText uiKey="u-de2a37e5a5c1">Sửa</UiCustomText></button><button data-ui-key="u-36871ed520b8" data-ui-label-default="Xóa" type="button" className="secondary-button danger-button" onClick={() => removeCatalogItem('room_delete', item)}><UiCustomText uiKey="u-36871ed520b8">Xóa</UiCustomText></button></UiToolbar></article>)}</div></div>
          <div className="live-tour-catalog-section"><UiToolbar data-ui-key="u-70b2ade51fb2" className="live-tour-panel-toolbar"><h3>Dịch vụ</h3><button data-ui-key="u-67dbc64dfa55" data-ui-label-default="Thêm dịch vụ" type="button" className="secondary-button" onClick={() => openModal('service_upsert')}><Plus size={12}/><UiCustomText uiKey="u-67dbc64dfa55"> Thêm dịch vụ</UiCustomText></button></UiToolbar>{services.length ? <div data-ui-key="u-ad9c4a0dfba6" className="live-tour-card-grid">{services.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{itemLabel(item)}</strong><span>{item?.duration ?? item?.minutes ?? 0} phút · {formatMoney(item?.price ?? item?.amount ?? 0)}</span><UiToolbar data-ui-key="u-927e28a1d633" className="live-tour-card-actions"><button data-ui-key="u-661481c5beff" data-ui-label-default="Sửa" type="button" className="secondary-button" onClick={() => openModal('service_upsert', { item })}><UiCustomText uiKey="u-661481c5beff">Sửa</UiCustomText></button><button data-ui-key="u-07a2c7cd4a22" data-ui-label-default="Xóa" type="button" className="secondary-button danger-button" onClick={() => removeCatalogItem('service_delete', item)}><UiCustomText uiKey="u-07a2c7cd4a22">Xóa</UiCustomText></button></UiToolbar></article>)}</div> : <div className="live-tour-empty">Chưa có dịch vụ.</div>}</div>
          <div className="live-tour-catalog-section"><UiToolbar data-ui-key="u-9ced5b68f52c" className="live-tour-panel-toolbar"><h3>Combo</h3><button data-ui-key="u-86d6070de0aa" data-ui-label-default="Thêm combo" type="button" className="secondary-button" onClick={() => openModal('combo_upsert')}><Plus size={12}/><UiCustomText uiKey="u-86d6070de0aa"> Thêm combo</UiCustomText></button></UiToolbar>{combos.length ? <div data-ui-key="u-5b550ecfc1ea" className="live-tour-card-grid">{combos.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{itemLabel(item)}</strong><span>{item?.quantity ?? item?.tickets ?? 0} lượt · {formatMoney(item?.price ?? item?.amount ?? 0)}</span>{item.requires_admin_approval === true && <small>Admin duyệt bán</small>}<UiToolbar data-ui-key="u-9fcb9f514a8e" className="live-tour-card-actions"><button data-ui-key="u-83b8b20fc4ed" data-ui-label-default="Sửa" type="button" className="secondary-button" onClick={() => openModal('combo_upsert', { item })}><UiCustomText uiKey="u-83b8b20fc4ed">Sửa</UiCustomText></button><button data-ui-key="u-7dc6d1f7e697" data-ui-label-default="Xóa" type="button" className="secondary-button danger-button" onClick={() => removeCatalogItem('combo_delete', item)}><UiCustomText uiKey="u-7dc6d1f7e697">Xóa</UiCustomText></button></UiToolbar></article>)}</div> : <div className="live-tour-empty">Chưa có combo.</div>}</div>
        </>}
      </div>}
    </section>

    {comboLookupOpen && canViewComboPackages && <LiveTourModal className="live-tour-combo-modal" title="Kiểm tra Gói Combo khách hàng" onClose={() => setComboLookupOpen(false)}>
      <div className="live-tour-combo-lookup">
        <UiToolbar data-ui-key="u-6948e5d17d87" className="live-tour-panel-toolbar"><p>Tìm khách hàng để xem số vé còn lại, ngày mua và toàn bộ lịch sử sử dụng combo.</p><button data-ui-key="u-7e34d298e21b" data-ui-label-default="Xuất Excel" type="button" className="secondary-button" disabled={!canExportKind('customers') || Boolean(actionBusy)} onClick={() => exportData('customers')}><Download size={13}/><UiCustomText uiKey="u-7e34d298e21b"> Xuất Excel</UiCustomText></button></UiToolbar>
        <label className="live-tour-customer-search"><Search size={14}/><ClearableSearchInput autoFocus type="search" aria-label="Tìm khách hàng trong Gói Combo" autoComplete="off" value={comboLookupSearch} onChange={(event) => setComboLookupSearch(event.target.value)} placeholder="Tìm theo tên khách hàng hoặc số điện thoại…"/></label>
        <div data-ui-key="u-3a71c9cca2d1" className="live-tour-card-grid live-tour-combo-lookup-grid">
          {comboLookupCustomers.map((customer, index) => <button data-ui-key="u-9aa9421c024d" type="button" className="live-tour-data-card live-tour-combo-customer" onClick={() => openCustomerHistory(customer)} key={itemId(customer, index)}>
            <strong>{itemLabel(customer, `Khách hàng ${index + 1}`)}</strong><span>{customer?.phone || 'Chưa có số điện thoại'}</span>
            <small>Tổng vé còn lại: {customerComboPurchases(customer).reduce((sum, combo) => sum + Number(combo?.remaining ?? combo?.balance ?? 0), 0)}</small>
            {customerComboPurchases(customer).map((combo, comboIndex) => <small key={itemId(combo, comboIndex)}><b>{itemLabel(combo)}</b> · còn {combo?.remaining ?? combo?.balance ?? 0}/{combo?.total ?? ''} vé · mua {bookingTimeLabel(combo?.purchased_at || combo?.created_at)}</small>)}
            <span className="live-tour-combo-history-link"><History size={13}/> Xem lịch sử mua và sử dụng</span>
          </button>)}
          {!comboLookupCustomers.length && <div className="live-tour-empty">Không tìm thấy khách hàng có Gói Combo phù hợp.</div>}
        </div>
      </div>
      <UiToolbar data-ui-key="u-22e0a300a413" className="live-tour-modal-actions"><button data-ui-key="u-46a5808aa1ad" data-ui-label-default="Đóng" type="button" className="secondary-button" onClick={() => setComboLookupOpen(false)}><UiCustomText uiKey="u-46a5808aa1ad">Đóng</UiCustomText></button></UiToolbar>
    </LiveTourModal>}

    {customerHistoryModal && canCustomers && <LiveTourModal title={`Lịch sử khách hàng · ${itemLabel(customerHistoryData.customer || customerHistoryModal.customer, 'Khách hàng')}`} onClose={() => setCustomerHistoryModal(null)}>
      {customerHistoryBusy && <div className="live-tour-empty">Đang tải lịch sử chính xác theo mã khách hàng…</div>}
      {customerHistoryModal.error && <div className="error-box">{customerHistoryModal.error}</div>}
      {!customerHistoryBusy && customerHistoryModal.data && <div className="live-tour-history-sections">
        {(!canPaidInvoiceView || !canInvoiceView || !canPending || !canReports) && <p>Chỉ hiển thị các phần được cấp quyền. Nội dung hóa đơn hoặc báo cáo chưa được cấp quyền sẽ không được tải.</p>}
        <div className="live-tour-customer-history-filter" role="group" aria-label="Lọc thời gian lịch sử Combo">
          <label><span>Thời gian</span><select value={customerHistoryFilters.preset} onChange={(event) => { const preset = event.target.value; setCustomerHistoryFilters({ preset, ...tourDateRange(preset) }) }}><option value="all">Tất cả</option><option value="month">Tháng này</option><option value="last-month">Tháng trước</option><option value="custom">Tùy chỉnh</option></select></label>
          {customerHistoryFilters.preset === 'custom' && <><label><span>Từ ngày</span><VeraDateInput value={customerHistoryFilters.date_from} max={customerHistoryFilters.date_to || undefined} onChange={(event) => setCustomerHistoryFilters((current) => ({ ...current, date_from: event.target.value }))}/></label><label><span>Đến ngày</span><VeraDateInput value={customerHistoryFilters.date_to} min={customerHistoryFilters.date_from || undefined} onChange={(event) => setCustomerHistoryFilters((current) => ({ ...current, date_to: event.target.value }))}/></label></>}
        </div>
        <section data-ui-key="u-0f49bb433a85" className="live-tour-catalog-section live-tour-combo-purchase-history"><h3>Lịch sử mua Combo ({customerComboPurchaseHistory.length})</h3>
          {customerComboPurchaseHistory.length ? <div className="live-tour-combo-purchase-list">{customerComboPurchaseHistory.map((purchase, index) => <article className="live-tour-combo-purchase-detail" key={itemId(purchase, index)}>
            <dl>
              <div><dt>Ngày mua:</dt><dd>{bookingTimeLabel(purchase?.effective_at || purchase?.purchased_at || purchase?.created_at)}</dd></div>
              <div><dt>Gói dịch vụ combo:</dt><dd>{purchase?.combo_name || itemLabel(purchase, `Combo ${index + 1}`)}</dd></div>
              <div><dt>Số vé đã mua:</dt><dd>{purchase?.total ?? 0}</dd></div>
              <div><dt>Thành tiền:</dt><dd>{formatMoney(purchase?.price ?? purchase?.amount ?? 0)}</dd></div>
              <div><dt>Lễ tân:</dt><dd>{comboPurchaseReceptionist(purchase)}</dd></div>
              <div><dt>Số vé đã sử dụng:</dt><dd>{purchase?.used ?? Math.max(0, Number(purchase?.total || 0) - Number(purchase?.remaining || 0))}</dd></div>
              <div><dt>Số vé còn lại:</dt><dd>{purchase?.remaining ?? purchase?.balance ?? 0}</dd></div>
            </dl>
          </article>)}</div> : <div className="live-tour-empty">Khách hàng chưa mua combo.</div>}
        </section>
        <section data-ui-key="u-36156c1cfbe7" className="live-tour-catalog-section"><h3>Lịch sử sử dụng vé Combo ({customerComboUsageHistory.length})</h3>
          {customerComboUsageHistory.length ? <div className="live-tour-history-list">{customerComboUsageHistory.slice(0, 100).map((usage, index) => {
            const purchase = customerComboPurchaseHistory.find((item) => String(item?.id || '') === String(usage?.combo_purchase_id || ''))
            const usedServices = asArray(usage?.entries).map((entry) => `${entry?.service || 'Dịch vụ'}${entry?.units ? ` (${entry.units} vé)` : ''}`).join(' · ')
            return <article key={itemId(usage, index)}><strong>{purchase?.combo_name || 'Gói Combo'} · sử dụng {usage?.units ?? 0} vé</strong><span>{usedServices || 'Chưa ghi dịch vụ'}</span><small>Ngày sử dụng: {bookingTimeLabel(usage?.effective_at || usage?.created_at || usage?.at)}</small><small>Hóa đơn: {usage?.bill_no || usage?.invoice_id || 'Chưa có'} · Lễ tân: {usage?.actor || 'Chưa có thông tin'}</small><small>Số vé: {usage?.remaining_before ?? '—'} → {usage?.remaining_after ?? '—'}</small></article>
          })}</div> : <div className="live-tour-empty">Khách hàng chưa sử dụng vé Combo.</div>}
        </section>
      </div>}
      <UiToolbar data-ui-key="u-2b85edff763d" className="live-tour-modal-actions"><button data-ui-key="u-f4cd4af6d32a" data-ui-label-default="Đóng" type="button" className="secondary-button" onClick={() => setCustomerHistoryModal(null)}><UiCustomText uiKey="u-f4cd4af6d32a">Đóng</UiCustomText></button><button data-ui-key="u-45936ff4c709" data-ui-label-default="Xuất chi tiết khách hàng" type="button" className="primary-button" disabled={!canExportKind('customer_detail') || customerHistoryBusy || Boolean(actionBusy)} onClick={exportCustomerHistory}><Download size={13}/><UiCustomText uiKey="u-45936ff4c709"> Xuất chi tiết khách hàng</UiCustomText></button></UiToolbar>
    </LiveTourModal>}

    {modal && <LiveTourModal title={{
      checkout: 'Thanh toán', quick_checkout: 'Thanh toán nhanh',
      combo_approvals: 'Duyệt yêu cầu bán combo',
      change_employee: 'Đổi nhân viên', replace_service: 'Đổi dịch vụ', add_service: 'Thêm dịch vụ',
      combo_purchase: 'Mua combo cho khách hàng', combo_import: 'Nhập combo', room_upsert: modal.item ? 'Sửa phòng' : 'Thêm phòng',
      service_upsert: modal.item ? 'Sửa dịch vụ' : 'Thêm dịch vụ', combo_upsert: modal.item ? 'Sửa combo' : 'Thêm combo',
    }[modal.kind] || 'Live Tour'} onClose={closeModal} fitViewport={['checkout', 'quick_checkout'].includes(modal.kind)} busy={Boolean(actionBusy)}>
      {['checkout', 'quick_checkout', 'change_employee'].includes(modal.kind) && error && <p className="error-box" role="alert">{error}</p>}
      <form onSubmit={submitModal}>
        <div className="live-tour-form-grid">
          {modal.kind === 'change_employee' && <>
            <p className="wide">Chuyển dịch vụ đang thực hiện của <strong>{cellValue(validRecords.find((row) => stableEmployeeId(row) === modal.rowIds[0]), employeeColumn)}</strong> sang nhân viên mới trong thời hạn cho phép. Giữ nguyên phòng, dịch vụ, thông tin khách và thời gian còn lại; nhân viên cũ trở về vị trí tua trước khi bắt đầu.</p>
            <LiveTourSearchSelect className="wide" label="Nhân viên thay thế" placeholder="Tìm và chọn nhân viên đang rảnh…" value={form.target_employee_id}
              options={validRecords.filter((row) => stableEmployeeId(row) !== modal.rowIds[0] && hasGroup(row, 'available') && !cellValue(row, serviceColumn) && !hasGroup(row, 'break') && normalizedColumn(cellValue(row, statusColumn)) !== 'CHO THANH TOAN').map((row) => ({ value: stableEmployeeId(row), label: cellValue(row, employeeColumn) }))}
              onChange={(id) => setForm((current) => ({ ...current, target_employee_id: id }))} disabled={Boolean(actionBusy)} required/>
          </>}
          {['checkout', 'quick_checkout'].includes(modal.kind) && <>
            {modal.kind === 'quick_checkout' && <>
              {canBook && !modal.item && <div className="tour-checkout-source wide">
                <button data-ui-key="u-bb0f107e16d1" data-ui-label-default="Thanh toán nhanh" type="button" className="secondary-button" aria-pressed={manualQuickBooking} onClick={() => setForm(current => ({ ...current, checkout_source: 'manual' }))}><UiCustomText uiKey="u-bb0f107e16d1">Thanh toán nhanh</UiCustomText></button>
                <button data-ui-key="u-20b67774132d" data-ui-label-default="Mua combo cho khách hàng" type="button" className="secondary-button" onClick={() => openModal('combo_purchase', { rowIds: [], defaults: { customer_id: form.customer_id, customer_name: form.customer_name, phone: form.phone } })}><UiCustomText uiKey="u-20b67774132d">Mua combo cho khách hàng</UiCustomText></button>
              </div>}
              {!manualQuickBooking && <div className="wide"><LiveTourSearchSelect className="live-tour-employee-picker" label="Tìm nhân viên / phòng / dịch vụ chờ thanh toán" required
                value={form.pending_id ? `pending:${form.pending_id}` : form.employee_id ? `employee:${form.employee_id}` : ''}
                options={quickCheckoutOptions} onChange={chooseQuickCheckout} placeholder="Tìm nhân viên, phòng hoặc dịch vụ…"/>
                {selectedQuickCheckoutRecord && <small className="live-tour-employee-picked">{cellValue(selectedQuickCheckoutRecord, employeeColumn)} · {checkoutSourceEntries[0]?.service || cellValue(selectedQuickCheckoutRecord, serviceColumn)}</small>}
              </div>}
              {manualQuickBooking && <>
                {!quickSteam && <>
                <LiveTourSearchSelect label="Nhân viên" required value={form.employee_id} options={quickCheckoutEmployees.filter((row, index, rows) => row.roster_eligible !== false && rows.findIndex((candidate) => stableEmployeeId(candidate) === stableEmployeeId(row)) === index).map((row) => ({ value: stableEmployeeId(row), label: row.name, detail: row.role || row.shift || 'Nhân viên' }))} onChange={(id) => setForm((current) => ({ ...current, employee_id: id }))}/>
                </>}
                <LiveTourSearchSelect label={form.combo_purchase_id ? "Dịch vụ (tự động từ combo)" : "Dịch vụ"} required={!form.combo_purchase_id} placeholder={quickSelectedServices.map(item => item.name).join(" & ") || (quickPurchase ? "Dùng 1 vé combo" : "Tìm và chọn…")} value={form.service_id} options={quickBookingServices.map((service) => ({ value: service.id, label: service.name, detail: formatMoney(service.price) }))} onChange={(id) => setForm((current) => ({ ...current, service_id: id }))}/>
                {!quickSteam && <>
                <LiveTourSearchSelect label="Phòng / giường" showAllOptions filterOption={roomOptionMatches} required value={form.room} options={catalogRooms.filter((room) => room.active !== false).map((room) => ({ value: room.name, label: room.name, group: bookingRoomGroup(room.name, catalogRooms) }))} onChange={(room) => setForm((current) => ({ ...current, room }))}/>
                </>}
                <div className="tour-booking-datetime"><label className="live-tour-field"><span>Ngày booking</span><VeraDateInput required min={canAdmin ? '2000-01-01' : vietnamDate(clockMs)} max={vietnamDate(clockMs)} value={form.booking_date} onChange={(event) => setForm((current) => ({ ...current, booking_date: event.target.value }))}/></label><label className="live-tour-field"><span>Giờ booking</span><input type="time" required value={form.booking_time} onChange={(event) => setForm((current) => ({ ...current, booking_time: event.target.value }))}/></label></div>
                {form.booking_date && form.booking_date < vietnamDate(clockMs) && <label className="live-tour-field wide"><span>Lý do nhập lùi ngày</span><input required minLength={3} value={form.booking_reason} onChange={(event) => setForm((current) => ({ ...current, booking_reason: event.target.value }))}/></label>}
              </>}
            </>}
            {!quickSteam && <div className="tour-checkout-context wide" aria-label="Nhân viên và phòng thanh toán">
              {checkoutSourceEntries.length ? <LiveTourPageItems items={checkoutSourceEntries} label="Nhân viên thanh toán">{(entry, index) => <div key={`${entry.employee_id}:${index}`}><strong>{entry.employee_name || 'Chưa có nhân viên'}</strong><span>Phòng: <strong>{entry.room || '—'}</strong></span></div>}</LiveTourPageItems> : <span>Chọn nhân viên và phòng ở trên.</span>}
            </div>}
            <LiveTourCheckoutCustomer customers={customers} form={form} setForm={setForm} disabled={!canCustomers} onSelectCustomer={manualQuickBooking ? chooseQuickCustomer : undefined}/>
            <div className="live-tour-checkout-preview wide">
              <strong>Dịch vụ</strong>
              <LiveTourPageItems items={checkoutPreviewEntries} label="Dịch vụ thanh toán">{(entry, index) => <div className="live-tour-checkout-entry" key={`${entry.employee_id || 'entry'}:${index}`}><span>{entry.employee_name || `Dòng ${index + 1}`} · {entry.service || 'Chưa có dịch vụ'}{entry.room ? ` · ${entry.room}` : ''}</span><strong>{Number.isFinite(entry.preview_price) ? formatMoney(checkoutUsesCombo ? comboExtraSubtotal(selectedCheckoutCombo, [entry], services) : entry.preview_price) : 'Server sẽ xác nhận giá'}</strong><small>{entry.ticket_units} vé combo theo định mức dịch vụ</small></div>}</LiveTourPageItems>
              {!checkoutPreviewEntries.length && <div className="live-tour-empty">Không có dịch vụ hợp lệ để xem trước thanh toán.</div>}
              {!checkoutUsesCombo && checkoutHasUnresolvedPricing && <div className="warning-box">Có dịch vụ chưa khớp danh mục. Cần sửa dịch vụ hoặc danh mục trước khi thanh toán.</div>}
              {!checkoutUsesCombo && checkoutHasMixedPricing && <div className="warning-box">Không thể gộp dịch vụ đã có giá và dịch vụ giá 0. Hãy cấu hình giá hoặc tách lần thanh toán.</div>}
              <div className="live-tour-checkout-total" aria-live="polite"><span>Tiền dịch vụ</span><strong>{Number.isFinite(checkoutEffectiveSubtotal) ? formatMoney(checkoutEffectiveSubtotal) : 'Chọn dịch vụ'}</strong><span>Tiền Tip</span><strong>{formatMoney(checkoutTipPreview)}</strong><span>Tổng thanh toán</span><strong>{Number.isFinite(checkoutPreviewTotal) ? formatMoney(checkoutPreviewTotal) : 'Chọn dịch vụ'}</strong></div>
            </div>
            <label className="live-tour-field"><span>Phương thức thanh toán</span><select value={form.payment_method} onChange={(event) => setForm((current) => ({ ...current, payment_method: event.target.value, ...(event.target.value === 'COMBO' ? {} : { combo_purchase_id: '' }) }))}><option>TIỀN MẶT</option><option>CHUYỂN KHOẢN</option><option>THẺ</option><option value="COMBO" disabled={!form.combo_purchase_id}>COMBO · chọn combo đã mua</option></select></label>
            <label className="live-tour-field"><span>Trừ vé combo</span><select value={form.combo_purchase_id} onChange={(event) => {
              setForm((current) => ({
                ...current, ...(manualQuickBooking ? { service_id: '' } : {}), combo_purchase_id: event.target.value, discount: event.target.value ? '0' : current.discount, discount_mode: 'amount', discount_percent: '0',
                payment_method: event.target.value ? 'COMBO' : current.payment_method === 'COMBO' ? 'TIỀN MẶT' : current.payment_method,
              }))
            }} disabled={!form.customer_id}><option value="">Không trừ combo</option>{eligibleCheckoutCombos.map(({ purchase }, index) => {
              const purchaseId = String(purchase?._id ?? purchase?.id ?? '')
              return <option value={purchaseId} key={purchaseId || index}>{purchase.combo_name || 'Combo'} · còn {purchase.remaining} {purchase.component_balances ? 'lượt' : 'vé'}{purchase.unlimited === false && purchase.expires_on ? ` · HSD ${purchase.expires_on.split('-').reverse().join('/')}` : ''}</option>
            })}</select></label>
            {form.combo_purchase_id && <div className="live-tour-combo-deduction wide">Trừ <strong>{checkoutPreviewComboUnits} {selectedCheckoutCombo?.component_balances ? 'lượt dịch vụ trong combo' : 'vé combo'}</strong>.{selectedCheckoutCombo?.component_balances && ' Dịch vụ đã trả trước; thanh toán TIP.'}</div>}
            {selectedCheckoutCombo?.component_balances && <LiveTourPageItems className="wide" items={selectedCheckoutCombo.component_balances} label="Số lượt combo" pageSize={1}>{(item) => <small key={item.service_id}>{services.find((service) => service.id === item.service_id)?.name || item.service_name}: còn {item.remaining} / {item.total} lượt</small>}</LiveTourPageItems>}
            {form.combo_purchase_id && !selectedCheckoutCombo && <p className="error-box wide" role="alert">Combo không còn phù hợp với dịch vụ hoặc ngày thanh toán. Hãy chọn lại.</p>}
            {checkoutRequiresTicketPrice && <label className="live-tour-field wide"><span>Giá vé (dịch vụ chưa có giá danh mục)</span><input type="number" min="1" max="1000000000" step="1000" value={form.ticket_price} onChange={(event) => setForm((current) => ({ ...current, ticket_price: event.target.value }))} required/></label>}
            <label className="live-tour-field"><span>Số hóa đơn</span><input value={form.bill_no} onChange={(event) => setForm((current) => ({ ...current, bill_no: event.target.value }))}/></label>
            <label className="live-tour-field"><span>Số vé</span><input value={form.ticket_no} onChange={(event) => setForm((current) => ({ ...current, ticket_no: event.target.value }))}/></label>
            <label className="live-tour-field"><span>Loại giảm giá</span><select value={form.discount_mode} disabled={checkoutUsesCombo} onChange={(event) => setForm((current) => ({ ...current, discount_mode: event.target.value }))}><option value="amount">Số tiền (đ)</option><option value="percent">Tỷ lệ (%)</option></select></label>
            <label className="live-tour-field"><span>Giảm giá {form.discount_mode === 'percent' ? '(%)' : '(đ)'}</span><input type="number" min="0" max={form.discount_mode === 'percent' ? '100' : undefined} step={form.discount_mode === 'percent' ? '0.01' : '1'} readOnly={checkoutUsesCombo} value={checkoutUsesCombo ? '0' : form.discount_mode === 'percent' ? form.discount_percent : form.discount} onChange={(event) => setForm((current) => ({ ...current, [current.discount_mode === 'percent' ? 'discount_percent' : 'discount']: event.target.value }))}/><small>{Number.isFinite(checkoutDiscountPreview) ? formatMoney(checkoutDiscountPreview) : ''}</small></label>
            <p className="wide">Tài khoản người thanh toán: {data.payment_settings?.user_bank ? `${data.payment_settings.user_bank.account_name} · ${data.payment_settings.user_bank.bank_id} · ${data.payment_settings.user_bank.account_no}` : 'Chưa cấu hình ngân hàng trong hồ sơ người thanh toán.'}</p>
            {!checkoutHasUnresolvedPricing && <LiveTourPaymentQr screenSettings={data.payment_settings?.customer_screen} bank={data.payment_settings?.user_bank} amount={checkoutPreviewTotal} reference={form.bill_no || 'VERA SPA'}/>}
            <LiveTourTipInput key={tipPreferenceKey} form={form} setForm={setForm} cards={asArray(data.payment_settings?.tip_cards)} preferenceKey={tipPreferenceKey} total={checkoutTipPreview}/>
            <label className="live-tour-check-field wide"><input type="checkbox" checked={form.print_after} onChange={(event) => setForm((current) => ({ ...current, print_after: event.target.checked }))}/> In hóa đơn sau khi thanh toán</label>
            <label className="live-tour-field wide"><span>Ghi chú</span><textarea value={form.note} onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}/></label>
          </>}


          {['replace_service', 'add_service'].includes(modal.kind) && <><label className="live-tour-field wide"><span>Dịch vụ</span><input list="live-tour-service-change-options" value={form.service} onChange={(event) => setForm((current) => ({ ...current, service: event.target.value }))} required autoFocus/><datalist id="live-tour-service-change-options">{bookableServices.map((service, index) => <option value={itemLabel(service)} key={itemId(service, index)}/>)}</datalist></label><label className="live-tour-field wide"><span>Ghi chú</span><textarea value={form.note} onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}/></label></>}

          {modal.kind === 'combo_approvals' && <div className="wide live-tour-combo-approvals">
            {pendingComboSaleRequests.length ? pendingComboSaleRequests.map((request) => <article className="live-tour-data-card" key={request.id}>
              <strong>{request.combo_name} × {request.quantity || 1}</strong>
              <span>Khách hàng: <strong>{request.customer_name || 'Chưa có tên'}</strong>{request.customer_phone ? ` · ${request.customer_phone}` : ''}</span>
              <span>{formatMoney(request.amount)} · {request.payment_method}</span>
              <small>Người gửi: {request.requested_by || '—'} · {formatVeraDateTime(request.requested_at)}</small>
              <UiToolbar data-ui-key="u-61ede12cfdbe" className="live-tour-card-actions">
                <button data-ui-key="u-4d4241e126de" data-ui-label-default="Duyệt bán" type="button" className="primary-button" disabled={Boolean(actionBusy)} onClick={() => executeAction('combo_sale_decide', { request_id: request.id, decision: 'approve' }, [])}><UiCustomText uiKey="u-4d4241e126de">Duyệt bán</UiCustomText></button>
                <button data-ui-key="u-d227edba5ce3" data-ui-label-default="Không duyệt" type="button" className="secondary-button danger-button" disabled={Boolean(actionBusy)} onClick={() => { const reason = window.prompt('Lý do từ chối (không bắt buộc):', ''); if (reason !== null) void executeAction('combo_sale_decide', { request_id: request.id, decision: 'reject', reason }, []) }}><UiCustomText uiKey="u-d227edba5ce3">Không duyệt</UiCustomText></button>
              </UiToolbar>
            </article>) : <div className="live-tour-empty">Không có yêu cầu bán combo đang chờ duyệt.</div>}
          </div>}

          {modal.kind === 'combo_purchase' && <>
            <div className="tour-checkout-source wide"><button data-ui-key="u-1c05ca82fbfb" data-ui-label-default="Thanh toán nhanh" type="button" className="secondary-button" onClick={() => openModal('quick_checkout', { rowIds: [], defaults: { checkout_source: 'manual', customer_id: form.customer_id, customer_name: form.customer_name, phone: form.phone } })}><UiCustomText uiKey="u-1c05ca82fbfb">Thanh toán nhanh</UiCustomText></button><button data-ui-key="u-707543a70377" data-ui-label-default="Mua combo cho khách hàng" type="button" className="secondary-button" aria-pressed="true"><UiCustomText uiKey="u-707543a70377">Mua combo cho khách hàng</UiCustomText></button></div>
            <LiveTourCheckoutCustomer customers={customers} form={form} setForm={setForm} customerRequired/>
            <LiveTourSearchSelect label="Combo" required value={form.combo_id} options={saleableCombos.map((combo, index) => ({ value: itemId(combo, index), label: itemLabel(combo) }))} onChange={id => setForm(current => ({ ...current, combo_id: id }))}/>
            {selectedComboCatalogItem?.components?.length > 0 && <div className="wide">{selectedComboCatalogItem.components.map((part) => <p key={part.service_id}>{services.find((service) => service.id === part.service_id)?.name || part.service_name}: {part.quantity * Math.max(1, Number(form.quantity || 1))} lượt</p>)}<small>{selectedComboCatalogItem.unlimited === false ? `Hạn dùng: ${selectedComboCatalogItem.expires_on.split('-').reverse().join('/')}` : 'Vô thời hạn'}</small></div>}
            <label className="live-tour-field"><span>Số combo</span><input type="number" min="1" max="1000" value={form.quantity} onChange={(event) => setForm((current) => ({ ...current, quantity: event.target.value }))} required/></label>
            <label className="live-tour-field wide"><span>Thành tiền</span><input type="text" value={comboPurchasePreviewAmount === null ? 'Chọn combo để xem giá' : formatMoney(comboPurchasePreviewAmount)} readOnly aria-readonly="true"/></label>
            <label className="live-tour-field"><span>Phương thức thanh toán</span><select value={form.payment_method} onChange={(event) => setForm((current) => ({ ...current, payment_method: event.target.value }))}><option>TIỀN MẶT</option><option>CHUYỂN KHOẢN</option><option>THẺ</option></select></label>
            <label className="live-tour-field"><span>Số hóa đơn</span><input value={form.bill_no} onChange={(event) => setForm((current) => ({ ...current, bill_no: event.target.value }))}/></label>
            <label className="live-tour-field wide"><span>Ghi chú</span><textarea value={form.note} onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))}/></label>
          </>}

          {canAdmin && modal.kind === 'combo_purchase' && <div className="live-tour-correction wide">
            <label className="live-tour-check-field"><input type="checkbox" checked={form.backdate_one_day} onChange={(event) => setForm((current) => ({ ...current, backdate_one_day: event.target.checked, correction_reason: event.target.checked ? current.correction_reason : '' }))}/> Lùi 1 ngày (Admin)</label>
            {form.backdate_one_day && <label className="live-tour-field"><span>Lý do điều chỉnh</span><textarea value={form.correction_reason} minLength="3" onChange={(event) => setForm((current) => ({ ...current, correction_reason: event.target.value }))} required placeholder="Bắt buộc ghi rõ lý do…"/></label>}
          </div>}

          {modal.kind === 'combo_import' && <LiveTourComboImportFields customers={customers} combos={combos} form={form} setForm={setForm}/>}

          {modal.kind === 'room_upsert' && <><label className="live-tour-field"><span>Mã phòng / giường</span><input value={form.code} onChange={(event) => setForm((current) => ({ ...current, code: event.target.value, room: event.target.value }))} required autoFocus/></label><p>Phòng 16–21 tự động thuộc nhóm VIP; các phòng khác là Standard.</p></>}
          {modal.kind === 'service_upsert' && <><label className="live-tour-field"><span>Mã dịch vụ</span><input value={form.code} onChange={(event) => setForm((current) => ({ ...current, code: event.target.value }))}/></label><label className="live-tour-field"><span>Tên dịch vụ</span><input value={form.service} onChange={(event) => setForm((current) => ({ ...current, service: event.target.value }))} required/></label><label className="live-tour-field"><span>Thời lượng (phút)</span><input type="number" min="0" value={form.duration} onChange={(event) => setForm((current) => ({ ...current, duration: event.target.value }))}/></label><label className="live-tour-field"><span>Đơn giá</span><input type="number" min="0" value={form.amount} onChange={(event) => setForm((current) => ({ ...current, amount: event.target.value }))}/></label></>}
          {modal.kind === 'service_upsert' && <>
            <label className="live-tour-field"><span>Số vé combo trừ</span><input type="number" min="0" max="100000" step="1" value={form.ticket_units} required onChange={(event) => setForm((current) => ({ ...current, ticket_units: event.target.value }))}/></label>
            <label className="live-tour-field"><span>Thời lượng khi YC (để trống = mặc định)</span><input type="number" min="0" max="1440" value={form.request_duration} onChange={(event) => setForm((current) => ({ ...current, request_duration: event.target.value }))}/></label>
            <label className="live-tour-check-field"><input type="checkbox" checked={form.private_service} onChange={(event) => setForm((current) => ({ ...current, private_service: event.target.checked }))}/> Khóa toàn phòng (PR)</label>
            <label className="live-tour-check-field"><input type="checkbox" checked={form.request_eligible} onChange={(event) => setForm((current) => ({ ...current, request_eligible: event.target.checked }))}/> Cho phép YC</label>
            <label className="live-tour-check-field"><input type="checkbox" checked={form.non_request_eligible} onChange={(event) => setForm((current) => ({ ...current, non_request_eligible: event.target.checked }))}/> Cho phép không YC</label>
          </>}
          {modal.kind === 'combo_upsert' && modal.item?.components?.length > 0 && <p className="wide">Số lượt được tính từ dịch vụ thành phần. Để thay đổi thành phần, mở Cài đặt → Cài đặt dịch vụ.</p>}
          {modal.kind === 'combo_upsert' && <><label className="live-tour-field"><span>Mã combo</span><input value={form.code} onChange={(event) => setForm((current) => ({ ...current, code: event.target.value }))}/></label><label className="live-tour-field"><span>Tên combo</span><input value={form.service} onChange={(event) => setForm((current) => ({ ...current, service: event.target.value }))} required/></label><label className="live-tour-field"><span>Số lượt</span><input type="number" min="1" readOnly={Boolean(modal.item?.components?.length)} value={form.quantity} onChange={(event) => setForm((current) => ({ ...current, quantity: event.target.value }))}/></label><label className="live-tour-field"><span>Giá combo</span><input type="number" min="0" value={form.amount} onChange={(event) => setForm((current) => ({ ...current, amount: event.target.value }))}/></label><label className="live-tour-check-field wide"><input type="checkbox" checked={form.requires_admin_approval === true} onChange={(event) => setForm((current) => ({ ...current, requires_admin_approval: event.target.checked }))}/> Admin duyệt bán khi Lễ tân hoặc Quản lý bán combo</label></>}
        </div>
        <UiToolbar data-ui-key="u-65d2d0e255f5" className="live-tour-modal-actions"><button data-ui-key="u-6a2d8b069fd1" type="button" className="secondary-button" onClick={closeModal}>{modal.kind === 'combo_approvals' ? 'Đóng' : 'Hủy'}</button>{modal.kind !== 'combo_approvals' && <button data-ui-key="u-8c3b981efa82" type="submit" className="primary-button" disabled={Boolean(actionBusy) || (checkoutUsesCombo && !selectedCheckoutCombo) || (modal.kind === 'quick_checkout' && !manualQuickBooking && !form.pending_id && !selectedQuickCheckoutRecord) || (['checkout', 'quick_checkout'].includes(modal.kind) && !checkoutUsesCombo && (checkoutHasUnresolvedPricing || checkoutHasMixedPricing))}>{actionBusy ? 'Đang lưu…' : 'Lưu thay đổi'}</button>}</UiToolbar>
      </form>
    </LiveTourModal>}

{bookingContext && <LiveTourBookingDialog key={bookingContext.employeeId || bookingContext.roomGroup} data={data} context={bookingContext} canAdmin={canAdmin} canSharePrivateRoom={['admin', 'quanly', 'letan'].includes(normalizedRole)} canOperate={canOperate} canBook={canBook} canCustomers={canCustomers} canPayment={canPayment && canInvoiceView && canPending} busy={Boolean(actionBusy)} error={error} onAction={executeAction} onClose={() => { if (!actionBusy) setBookingContext(null) }} onCheckout={(pending, worker) => { setBookingContext(null); openModal('checkout', pending ? { item: pending, rowIds: [] } : { rowIds: [worker.id] }) }}/>} 
    {pendingContext && !pendingContext.paid && canPending && canInvoiceView && <LiveTourPendingDialog key={`${pendingContext.item.id}:${pendingContext.mode}`} context={pendingContext} catalog={data.services || []} canEditDate={capabilities.invoice_date_edit === true} busy={Boolean(actionBusy)} error={error} onAction={executeAction} onClose={() => setPendingContext(null)}/>}
    {customerContext && <LiveTourCustomerDialog context={customerContext} comboCatalog={combos} busy={Boolean(actionBusy)} error={error} onAction={executeAction} onClose={() => setCustomerContext(null)}/>}
    {pendingContext?.paid && canPaidInvoiceView && <LiveTourPaidInvoiceDialog key={`${pendingContext.item.id}:${pendingContext.mode}`} context={pendingContext} canEditDate={capabilities.invoice_date_edit === true} busy={Boolean(actionBusy)} error={error} onAction={executeAction} onClose={() => setPendingContext(null)}/>}
    {receipt && canPaidInvoiceView && <LiveTourReceipt key={receipt.invoice.id} invoice={receipt.invoice} paymentSettings={data.payment_settings} autoPrint={receipt.autoPrint} onClose={() => setReceipt(null)}/>}
    {isAdmin && <LiveTourPartialLeaveSettings key={JSON.stringify(data.payment_settings?.partial_leave_times)} value={data.payment_settings} busy={Boolean(actionBusy)} onSave={payload => executeAction('payment_settings_update', payload, [])}/>}
  </div>
}
