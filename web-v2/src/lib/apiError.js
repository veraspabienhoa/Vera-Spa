const isPresent = (value) => value !== undefined && value !== null && value !== ''

const locationLabel = (location) => {
  if (!Array.isArray(location)) return ''
  return location
    .filter((part) => !['body', 'query', 'path'].includes(String(part)))
    .join('.')
}

const detailMessage = (detail) => {
  if (!isPresent(detail)) return ''
  if (typeof detail === 'string' || typeof detail === 'number' || typeof detail === 'boolean') {
    return String(detail)
  }
  if (Array.isArray(detail)) {
    return detail.map(detailMessage).filter(Boolean).join(' · ')
  }
  if (typeof detail === 'object') {
    const message = detail.msg || detail.message || detail.detail || detail.error
    if (isPresent(message)) {
      const field = locationLabel(detail.loc)
      return field ? `${field}: ${detailMessage(message)}` : detailMessage(message)
    }
    try {
      return JSON.stringify(detail)
    } catch {
      return ''
    }
  }
  return String(detail)
}

export function apiErrorMessage(payload, status) {
  const message = detailMessage(payload?.detail) || detailMessage(payload?.message)
  return message || `HTTP ${status}`
}
