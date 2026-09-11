import { tourNameKey } from './liveTourBooking.js'
import { searchTextMatches } from './searchText.js'

const roomNumber = value => tourNameKey(value).replace(/^(phong|vip)\s*/, '').split('.')[0]
export function bookingRoomGroup(name, rooms) {
  const room = rooms.find(row => tourNameKey(row.name) === tourNameKey(name))
  return tourNameKey(room?.area_name || roomNumber(name))
}
export function roomOptionMatches(option, query) {
  const text = tourNameKey(query).replace(/^(phong|vip)\s*/, '')
  if (!text) return true
  if (/^\d+$/.test(text)) return roomNumber(option.group || option.value) === text
  if (/^\d+\.\d*$/.test(text)) return tourNameKey(option.value).replace(/^(phong|vip)\s*/, '').startsWith(text)
  return searchTextMatches([option.label, option.group], query)
}
export function isPrivateBooking(service, catalog) {
  const name = tourNameKey(service)
  return /(^|[^a-z0-9])pr(?=$|[^a-z0-9])/.test(name)
    || /(^|[^a-z0-9])p\s*\.?\s*rieng(?=$|[^a-z0-9])/.test(name)
    || catalog.some(item => item.private && name.split(/\s*&\s*/).includes(tourNameKey(item.name)))
}
export function bookingRoomState(rooms, employees, catalog, employeeId, selectedRoom, items = []) {
  const active = employees.filter(row => row.id !== employeeId && row.room && ['dang cho', 'dang thuc hien', 'dang su dung'].includes(tourNameKey(row.status)))
  const group = bookingRoomGroup(selectedRoom, rooms)
  const occupants = active.filter(row => bookingRoomGroup(row.room, rooms) === group)
  const requestedPrivate = items.some(item => {
    const service = catalog.find(row => row.id === item.service_id)
    return service && (service.private || isPrivateBooking(service.name, catalog))
  })
  const locked = occupants.some(row => (row.private || isPrivateBooking(row.service, catalog)))
  const error = !selectedRoom ? '' : locked ? `Phòng ${group} đang bị khóa toàn phòng bởi dịch vụ PR.`
    : requestedPrivate && occupants.length ? `Không thể đặt dịch vụ PR: Phòng ${group} đang có khách. PR cần toàn phòng trống.`
    : occupants.some(row => tourNameKey(row.room) === tourNameKey(selectedRoom)) ? `Giường/phòng ${selectedRoom} đang được sử dụng.` : ''
  const options = rooms.filter(row => row.active !== false).flatMap(row => {
    const roomGroup = bookingRoomGroup(row.name, rooms)
    const busy = active.filter(worker => bookingRoomGroup(worker.room, rooms) === roomGroup)
    if (busy.some(worker => (worker.private || isPrivateBooking(worker.service, catalog)))) return []
    return [{ value: row.name, label: row.name, group: roomGroup,
      className: busy.length ? 'tour-room-option-occupied' : '',
      detail: [row.area_name, ...busy.map(worker => `${worker.room}: ${worker.service} · ${worker.status}`)].filter(Boolean).join(' · ') }]
  })
  return { options, error }
}
