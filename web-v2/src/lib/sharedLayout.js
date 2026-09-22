export const layoutCandidates = '.nav-list > a, [role="tab"], button, input:not([type="hidden"]), select, textarea, label, .panel, .metric-card, .training-card, .training-tabs > button, .spa-tabs > button, .training-report-filter, .staff-toolbar, .page-heading, .page-heading-row'
export function layoutKey(element, page) {
  const parts = []
  for (let node = element; node && !node.classList?.contains('app-shell'); node = node.parentElement) {
    if (node.dataset?.veraNode) parts.push(`${node.dataset.veraNode}:${node.dataset.veraItem || ''}`)
  }
  if (!parts.length) return ''
  let hash = 2166136261
  for (const char of `${element.closest('.sidebar') ? 'menu' : page}|${parts.join('/')}`) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619)
  return `l-${(hash >>> 0).toString(36)}`
}
export function layoutCss(items) {
  const rules = []
  for (const [key, value] of Object.entries(items || {})) {
    if (!/^l-[a-z0-9-]+$/.test(key)) continue
    const declarations = []
    if (Number.isInteger(value.order) && value.order >= 0 && value.order <= 10000) declarations.push(`order:${value.order}!important`)
    if (Number.isInteger(value.width) && value.width >= 32 && value.width <= 2400) declarations.push(`width:min(${value.width}px,100%)!important;max-width:100%!important;min-width:0!important;box-sizing:border-box`)
    if (Number.isInteger(value.height) && value.height >= 24 && value.height <= 1600) declarations.push(`min-height:${value.height}px!important;height:auto!important;overflow-wrap:anywhere`)
    rules.push(`[data-layout-key="${key}"]{${declarations.join(';')}}`)
    if (value.parent && /^l-[a-z0-9-]+$/.test(value.parent)) rules.push(`[data-layout-key="${value.parent}"][data-layout-block="true"]{display:flex!important;flex-direction:column!important;min-width:0;max-width:100%}`)
  }
  return rules.join('\n')
}
