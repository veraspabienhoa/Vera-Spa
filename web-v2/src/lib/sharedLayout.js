import { visualCss } from './uiVisualStyle.js'
export const layoutCandidates = 'strong, small, b, em, blockquote, figure, figcaption, details, summary, img, div, span, main, nav, aside, footer, form, h4, h5, h6, article, ul, ol, li, table, th, header, [role=heading], p, span[data-ui-key], [role=listbox], [role=combobox], h1, h2, h3, section, fieldset, .box, [role=combobox], .vera-date-input, .searchable-select, .nav-list > a, [role="tab"], button, input:not([type="hidden"]), select, textarea, label, .panel, .metric-card, .training-card, .training-tabs > button, .spa-tabs > button, .training-report-filter, .staff-toolbar, .page-heading, .page-heading-row'
export function legacyLayoutKey(element, page) {
  const parts = []
  for (let node = element; node && !node.classList?.contains('app-shell'); node = node.parentElement) {
    if (node.dataset?.veraNode) parts.push(`${node.dataset.veraNode}:${node.dataset.veraItem || ''}`)
  }
  if (!parts.length) return ''
  let hash = 2166136261
  for (const char of `${element.closest('.sidebar') ? 'menu' : page}|${parts.join('/')}`) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619)
  return `l-${(hash >>> 0).toString(36)}`
}
export function layoutKey(element, page) {
  return element.dataset.uiKey || legacyLayoutKey(element, page)
}
export function layoutCss(items) {
  const rules = []
  for (const [key, value] of Object.entries(items || {})) {
    if (!/^(l|u)-[a-z0-9-]+$/.test(key)) continue
    const declarations = []
    if (value.hidden === true) declarations.push('display:none!important')
    if (Number.isInteger(value.order) && value.order >= 0 && value.order <= 10000) declarations.push(`order:${value.order}!important`)
    if (Number.isInteger(value.width) && value.width >= 32 && value.width <= 2400) declarations.push(`width:min(${value.width}px,100%)!important;max-width:100%!important;min-width:0!important;box-sizing:border-box;flex:0 1 auto!important`)
    if (Number.isInteger(value.height) && value.height >= 24 && value.height <= 1600) declarations.push(`min-height:${value.height}px!important;height:auto!important;overflow-wrap:anywhere`)
    if (['left','center','right','justify'].includes(value.text_align)) declarations.push(`text-align:${value.text_align}!important`)
    if (['start','center','end'].includes(value.content_align)) declarations.push(`align-content:${value.content_align}!important`)
    if (['start','center','end','space-between','space-around','space-evenly'].includes(value.justify_content)) declarations.push(`justify-content:${value.justify_content}!important`)
    if (['start','center','end','stretch'].includes(value.align_items)) declarations.push(`align-items:${value.align_items}!important`)
    const selector = `[data-layout-key="${key}"],[data-layout-legacy="${key}"],[data-ui-key="${key}"]`
    if (Number.isInteger(value.font_size) && value.font_size >= 12 && value.font_size <= 24) declarations.push(`font-size:${value.font_size}px!important`)
    if (!value.hidden && [0,1,2,3,4].includes(value.rows)) declarations.push('display:grid!important;grid-template-columns:repeat(var(--ui-columns,2),minmax(0,1fr))!important;gap:6px!important;max-width:100%;min-width:0')
    if (Number.isInteger(value.gap) && value.gap >= 0 && value.gap <= 100) declarations.push(`gap:${value.gap}px!important`)
    rules.push(`${selector}{${declarations.join(';')}}`)
    if (['start','center','end'].includes(value.content_align)) rules.push(`:is(${selector}):is(button,a,[role="tab"]){align-items:${value.content_align}!important}`)
    if (['left','center','right'].includes(value.text_align)) rules.push(`:is(${selector}):is(button,a,[role="tab"]){justify-content:${{left:'flex-start',center:'center',right:'flex-end'}[value.text_align]}!important}`)
    if (value.appearance && typeof value.appearance === 'object') rules.push(visualCss(selector, value.appearance))
    if (value.width != null || value.height != null) rules.push(`:is(${selector}):is(span,strong,small,b,em){display:inline-block!important}`)
    if (value.width != null) rules.push(`table:has(th[data-layout-key="${key}"]){table-layout:fixed;width:100%;max-width:100%}`)
    if (value.rows != null) rules.push(`[data-layout-key="${key}"]>button,[data-layout-key="${key}"]>a{min-width:0!important;max-width:100%;white-space:normal!important;overflow-wrap:anywhere;min-height:36px}`)
    if (value.parent && /^(l|u)-[a-z0-9-]+$/.test(value.parent)) rules.push(`[data-layout-key="${value.parent}"][data-layout-block="true"]{display:flex!important;flex-direction:column!important;min-width:0;max-width:100%}`)
  }
  return rules.join('\n')
}
