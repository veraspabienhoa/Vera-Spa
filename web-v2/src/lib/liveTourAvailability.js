import { tourNameKey } from './liveTourBooking.js'

const doing = (status) => ['dang thuc hien', 'dang su dung'].includes(tourNameKey(status))
const conflicts = (room, group, privateService, other) => tourNameKey(room) === tourNameKey(other.room) || (tourNameKey(group) === tourNameKey(other.group) && (privateService || other.private))

export function isPrivateCatalogService(service) {
  const name = tourNameKey(service?.name || service)
  return service?.private === true || /(^|[^a-z0-9])pr(?=$|[^a-z0-9])|(^|[^a-z0-9])p\s*\.?\s*rieng(?=$|[^a-z0-9])/.test(name)
}

export function bookingPlaceStatus(occupancy, { room, group, privateService = false, employeeId, now = Date.now(), reserve = true }) {
  const own = occupancy.find((row) => row.employee_id === employeeId) || {}
  const remaining = []
  let unknown = false
  for (const other of occupancy) {
    if (other.employee_id === employeeId || !conflicts(room, group, privateService, other)) continue
    const oldConflict = Boolean(own.room) && conflicts(own.room, own.group, own.private, other)
    if (doing(own.status) && tourNameKey(other.status) === 'dang cho' && oldConflict) continue
    if (tourNameKey(other.status) === 'dang cho') return { allowed: false, can_start: false, reason: 'waiting', remaining_seconds: null }
    const parsed = other.deadline ? (Date.parse(other.deadline) - now) / 1000 : NaN
    const seconds = Number.isFinite(parsed) ? parsed : null
    const held = tourNameKey(own.status) === 'dang cho' && oldConflict
    if (!reserve || (!held && (seconds === null || seconds >= 1800))) return { allowed: false, can_start: false, reason: 'occupied', remaining_seconds: seconds }
    if (seconds === null) unknown = true
    else remaining.push(seconds)
  }
  if (remaining.length || unknown) return { allowed: true, can_start: false, reason: 'finishing', remaining_seconds: unknown ? null : Math.max(...remaining) }
  return { allowed: true, can_start: true, reason: 'ready', remaining_seconds: 0 }
}

export function bookingPlaceNotice(place) {
  if (!place || place.can_start) return ''
  const seconds = place.remaining_seconds
  if (seconds === null) return 'Chờ phiên trước hoàn thành; chưa thể Thực hiện.'
  if (seconds <= 0) return 'Phiên trước đã hết giờ; chờ Hoàn thành để bắt đầu lịch mới.'
  const whole = Math.max(1, Math.floor(seconds))
  return `Phiên trước còn ${Math.floor(whole / 60)} phút ${whole % 60} giây · Có thể đặt lịch chờ.`
}

export function bookingPlaces(data, options = {}) {
  const rooms = data.catalogs?.rooms || data.state?.rooms || []
  // Older/cached responses without occupancy must not advertise busy beds.
  const occupancy = data.booking_occupancy
  return rooms.filter((room) => room.active !== false).flatMap((room) => {
    const group = data.room_groups?.[room.name] || room.area_name || tourNameKey(room.name).replace(/^(phong|vip)\s*/, '').split('.')[0]
    const status = Array.isArray(occupancy) ? bookingPlaceStatus(occupancy, { ...options, room: room.name, group })
      : { allowed: (data.available_beds || []).includes(room.name), can_start: true }
    return status.allowed ? [{ ...room, ...status, notice: bookingPlaceNotice(status) }] : []
  })
}
