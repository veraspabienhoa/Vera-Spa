import { EMPTY_TOUR_FILTERS, TOUR_DATE_PRESETS, tourDateRange } from './liveTourFilters.js'

export const TOUR_DATE_SECTIONS = ['pending', 'invoices', 'reports', 'history']
export const TOUR_DATE_PRESET_IDS = TOUR_DATE_PRESETS.map(([id]) => id)
const SECTION_GRANTS = {
  pending: [['pending_view'], ['invoice_view']],
  invoices: [['paid_invoice_view']],
  reports: [['reports_view']],
  history: [['history_view', 'backup']],
}
const validDay = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') && Number.isFinite(new Date(`${value}T12:00:00+07:00`).getTime())
  && tourDateRange('today', new Date(`${value}T12:00:00+07:00`)).date_from === value
const serverNow = value => validDay(value) ? new Date(`${value}T12:00:00+07:00`) : new Date()
const has = (object, key) => Object.prototype.hasOwnProperty.call(object || {}, key)

export function tourAccountKey(user) {
  return String(user?.id || user?.employee_username || user?.email || '')
}

export function tourProfileKey(user) {
  return JSON.stringify([tourAccountKey(user), user?.role, user?.permissions || {}])
}

export function tourDateSectionReadable(user, capabilities = {}, section) {
  if (String(user?.role || '').trim().toLowerCase() === 'admin') return TOUR_DATE_SECTIONS.includes(section)
  const permissions = user?.permissions || {}
  const readGrant = name => permissions[`live_tour_${name}`] === false ? false : has(capabilities, name) ? capabilities[name] === true : permissions[`live_tour_${name}`] === true
  return Boolean(SECTION_GRANTS[section]?.every(alternatives => alternatives.some(readGrant)))
}

// The profile gives first-render grants. Once supplied, the versioned server
// contract is authoritative, intersected with explicit profile revocations.
export function resolveTourDatePolicy(user, capabilities = {}) {
  const admin = String(user?.role || '').trim().toLowerCase() === 'admin'
  const permissions = user?.permissions || {}
  const contract = capabilities?.date_filters
  const hasContract = has(capabilities, 'date_filters')
  const validContract = contract?.version === 1 && contract.sections && typeof contract.sections === 'object'
  const sections = Object.fromEntries(TOUR_DATE_SECTIONS.map(section => {
    if (admin) return [section, [...TOUR_DATE_PRESET_IDS]]
    const sectionAllowed = tourDateSectionReadable(user, capabilities, section)
    const serverPresets = hasContract ? validContract && Array.isArray(contract.sections[section]) ? contract.sections[section] : [] : TOUR_DATE_PRESET_IDS
    return [section, sectionAllowed ? TOUR_DATE_PRESET_IDS.filter(preset => {
      const feature = `live_tour_${section}_date_${preset.replaceAll('-', '_')}`
      return serverPresets.includes(preset) && (!has(permissions, feature) || permissions[feature] === true)
    }) : []]
  }))
  return { version: 1, sections, server_today: validContract && validDay(contract.server_today) ? contract.server_today : '' }
}

export function allowedTourPresets(policy, section) {
  return Array.isArray(policy?.sections?.[section]) ? policy.sections[section] : []
}

export function tourDatePolicyKey(user, policy) {
  return JSON.stringify([tourProfileKey(user), policy])
}

export function normalizeTourDateFilters(filters, allowed, { preferredPreset, serverToday } = {}) {
  const choices = TOUR_DATE_PRESET_IDS.filter(preset => allowed?.includes(preset))
  const source = { ...EMPTY_TOUR_FILTERS, ...filters }
  const requested = filters?.preset || preferredPreset || source.preset
  const preset = choices.includes(requested) ? requested : choices[0] || ''
  if (!preset) return { ...source, preset: '', date: '', date_from: '', date_to: '' }
  if (preset === 'custom') {
    // A newly selected custom-only permission never silently sends all time.
    // Operators can then edit the explicit bounded range.
    const today = tourDateRange('today', serverNow(serverToday)).date_from
    return { ...source, preset, date: source.preset === 'custom' ? source.date : '',
      date_from: source.preset === 'custom' ? source.date_from : today,
      date_to: source.preset === 'custom' ? source.date_to : today }
  }
  const now = serverNow(serverToday)
  // Named ranges are server-calendar based. Never reuse arbitrary stored dates
  // after a custom grant is revoked or a different account signs in.
  return { ...source, preset, date: '', ...tourDateRange(preset, now) }
}

export function tourDateFiltersReady(filters) {
  if (!TOUR_DATE_PRESET_IDS.includes(filters?.preset)) return false
  if (filters.preset !== 'custom') return true
  return validDay(filters.date_from) && validDay(filters.date_to) && filters.date_from <= filters.date_to
}

export function tourDateSelectionStorageKey(user, section) {
  return `vera-live-tour-date-selection:v1:${encodeURIComponent(tourAccountKey(user))}:${section}`
}

export function readTourDateSelection(user, section, storage = globalThis.sessionStorage) {
  try {
    const value = JSON.parse(storage?.getItem(tourDateSelectionStorageKey(user, section)) || 'null')
    // Store dates/preset only. Customer names and other private searches stay in memory.
    return value && typeof value === 'object' ? { preset: value.preset, date: value.date || '', date_from: value.date_from || '', date_to: value.date_to || '' } : null
  } catch { return null }
}

export function saveTourDateSelection(user, section, filters, storage = globalThis.sessionStorage) {
  if (!tourAccountKey(user) || !TOUR_DATE_SECTIONS.includes(section) || !filters?.preset) return
  try { storage?.setItem(tourDateSelectionStorageKey(user, section), JSON.stringify({ preset: filters.preset, date: filters.date || '', date_from: filters.date_from || '', date_to: filters.date_to || '' })) } catch { /* optional preferences */ }
}

export function tourExportSection(kind) {
  if (kind === 'paid') return 'invoices'
  if (['revenue', 'reports', 'tip', 'employee', 'performance'].includes(kind)) return 'reports'
  if (['history', 'breaks'].includes(kind)) return 'history'
  return kind === 'pending' ? 'pending' : ''
}
