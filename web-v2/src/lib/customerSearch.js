import { tourNameKey } from './liveTourBooking.js'

const phoneDigits = (value) => String(value || '').replace(/\D/g, '')
const localPhone = (digits) => /^84\d{9}$/.test(digits) ? `0${digits.slice(2)}` : digits

export function customerMatches(customer, query) {
  // Keep a formatted phone number together while allowing name + phone searches.
  const terms = tourNameKey(query).replace(/[+(]*\d(?:[\d\s().-]*\d)?\)*/g, phoneDigits).trim().split(/\s+/).filter(Boolean)
  const name = tourNameKey(customer?.name || customer?.customer_name)
  const phone = phoneDigits(customer?.phone || customer?.customer_phone)
  return terms.every((term) => name.includes(term) || (/^\d+$/.test(term)
    && (phone.includes(term) || localPhone(phone).includes(localPhone(term)))))
}

export const customerOptionMatches = (option, query) => customerMatches({ name: option.label, phone: option.detail }, query)
