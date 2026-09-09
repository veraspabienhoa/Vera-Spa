export function vietnamDate(value = Date.now()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value)).map((part) => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function catalogTransactionDate(value, backdated = false) {
  if (!backdated) return vietnamDate(value)
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(value)).map((part) => [part.type, part.value]))
  const days = Number(parts.hour) * 60 + Number(parts.minute) < 11 * 60 + 10 ? 2 : 1
  return vietnamDate(new Date(value).getTime() - days * 86400000)
}

export function newCatalogForm(kind, item) {
  return structuredClone({
    name: '', group: '', price: '0', duration: '60', sessions: '1', steps: [],
    ticket_units: '1', request_duration: '', private: false, request_eligible: true, non_request_eligible: true,
    active: true, starts_on: item ? '' : vietnamDate(), unlimited: true, expires_on: '', loyalty_points: '0', description: '',
    tickets: '1', ...item,
    combo_mode: item && !item.components?.length ? 'generic' : 'components',
    components: item?.components?.length ? item.components : kind === 'combo' && !item ? [{ service_id: '', quantity: '1' }] : [],
  })
}

export function catalogPayload(kind, form, existing) {
  const common = {
    create_only: !existing, id: form.id, name: form.name, group: form.group, price: Number(form.price),
    starts_on: form.starts_on, unlimited: form.unlimited, expires_on: form.unlimited ? '' : form.expires_on,
    loyalty_points: Number(form.loyalty_points || 0), description: form.description, active: form.active,
  }
  if (kind === 'combo') return {
    ...common, ...(form.combo_mode === 'generic' ? { tickets: Number(form.tickets) } : {
      components: form.components.map((row) => ({ service_id: row.service_id, quantity: Number(row.quantity) })),
    }),
  }
  return {
    ...common, sessions: Number(form.sessions), steps: form.steps.map((row) => ({ name: row.name, duration: Number(row.duration || 0) })),
    duration: form.duration === '' || form.duration == null ? null : Number(form.duration), ticket_units: Number(form.ticket_units),
    request_duration: form.request_duration === '' || form.request_duration == null ? null : Number(form.request_duration),
    private: form.private, request_eligible: form.request_eligible, non_request_eligible: form.non_request_eligible,
  }
}

export function catalogIsAvailable(item, day = vietnamDate()) {
  return item.active !== false && (!item.starts_on || item.starts_on <= day) && (item.unlimited !== false || !item.expires_on || item.expires_on >= day)
}

const key = (name) => String(name || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').trim().toLowerCase().replace(/\s+/g, ' ')

export function comboUsagePreview(purchase, entries, services, day = vietnamDate()) {
  if (!purchase || !catalogIsAvailable(purchase, day)) return { eligible: false, units: 0 }
  if (!Array.isArray(purchase.component_balances)) return { eligible: Number(purchase.remaining) > 0, units: null }
  const required = new Map()
  for (const entry of entries) {
    if (entry.service_items?.length) {
      for (const item of entry.service_items) required.set(item.service_id, (required.get(item.service_id) || 0) + Number(item.quantity))
      continue
    }
    const exact = services.find((service) => key(service.name) === key(entry.service))
    const parts = exact ? [exact.name] : String(entry.service || '').split('&').map((part) => part.trim()).filter(Boolean)
    for (const part of parts) {
      const service = services.find((item) => key(item.name) === key(part))
      if (!service) return { eligible: false, units: 0 }
      required.set(service.id, (required.get(service.id) || 0) + 1)
    }
  }
  const units = [...required.values()].reduce((sum, count) => sum + count, 0)
  return { units, eligible: units > 0 && units <= Number(purchase.remaining) && [...required].every(([id, count]) => purchase.component_balances.some((row) => row.service_id === id && Number(row.remaining) >= count)) }
}
