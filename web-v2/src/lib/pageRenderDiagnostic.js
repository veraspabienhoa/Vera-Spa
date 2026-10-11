/* global __VERA_BUILD_REVISION__ */

export const loadedPageRevision = typeof __VERA_BUILD_REVISION__ === 'string' && /^[a-f0-9]{40}$/i.test(__VERA_BUILD_REVISION__)
  ? __VERA_BUILD_REVISION__.slice(0, 12) : 'development'

// Only fixed categories reach the screen. Messages and stacks can contain
// customer data, credentials or private URLs, so never display or transmit them.
export function pageRenderDiagnostic(error) {
  const message = typeof error?.message === 'string' ? error.message : ''
  if (/Objects are not valid as a React child|Minified React error #31;/.test(message)) return 'RENDER_OBJECT_CHILD'
  if (/toLocaleString/.test(message)) return 'RENDER_NUMBER_FORMAT'
  if (/not iterable|Spread syntax requires/.test(message)) return 'RENDER_COLLECTION'
  if (/Rendered (?:more|fewer) hooks|Invalid hook call/.test(message)) return 'RENDER_HOOKS'
  switch (error?.name) {
    case 'TypeError': return 'RENDER_TYPE'
    case 'ReferenceError': return 'RENDER_REFERENCE'
    case 'RangeError': return 'RENDER_RANGE'
    default: return 'RENDER_OTHER'
  }
}
