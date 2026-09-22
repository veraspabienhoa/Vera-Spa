const color = value => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)
const bounded = (value, min, max) => Number.isInteger(value) && value >= min && value <= max
export const visualPreset = {
  normal: { background: '#ffffff', gradient: '#f4f7f6', text: '#1b5e20', border: '#1b5e20', shadow: 'raised' },
  hover: { background: '#f0fdf4', text: '#14532d', shadow: 'raised' },
  pressed: { shadow: 'soft' },
  selected: { background: '#1b5e20', gradient: '#0f3813', text: '#ffffff', border: '#0f3813', shadow: 'medium' },
  focus: { border: '#1b5e20', shadow: 'soft' },
  radius: 10, padding_x: 14, padding_y: 8, border_width: 2, font_weight: 600,
  font_family: 'system', font_size: 14, glass_blur: 8, glass_opacity: 92,
  depth: 3, transition_ms: 200, hover_lift: 2, press_sink: 2,
}
export function visualCss(selector, style = {}) {
  const base = `:is(${selector}):not(.danger-button,.danger,.vip,.vip-gold,.live-tour-employee-name,.schedule-employee-name)`
  const depth = bounded(style.depth, 0, 8) ? style.depth : 3
  const shadows = { none: 'none', soft: '0 2px 6px #00000018', medium: '0 6px 18px #00000026', strong: '0 12px 30px #00000033', inset: 'inset 0 1px 4px #00000020', raised: `0 ${depth}px 0 ${color(style.normal?.border) ? style.normal.border : '#134216'},0 5px 12px #00000020` }
  const stateCss = state => {
    const parts = []
    if (color(state?.background)) {
      const alpha = bounded(style.glass_opacity, 20, 100) ? Math.round(style.glass_opacity * 2.55).toString(16).padStart(2,'0') : 'ff'
      parts.push(`background:${color(state.gradient) ? `linear-gradient(135deg,${state.background}${alpha},${state.gradient}${alpha})` : state.background + alpha}!important`)
    }
    if (color(state?.text)) parts.push(`color:${state.text}!important`)
    if (color(state?.border)) parts.push(`border-color:${state.border}!important`)
    if (Object.hasOwn(shadows, state?.shadow)) parts.push(`box-shadow:${shadows[state.shadow]}!important`)
    return parts.join(';')
  }
  const common = []
  for (const [key, prop, max] of [['radius','border-radius',40],['padding_x','padding-inline',40],['padding_y','padding-block',32],['border_width','border-width',6],['glass_blur','backdrop-filter',20]]) {
    if (bounded(style[key], key === 'border_width' ? 1 : 0, max)) common.push(`${prop}:${key === 'glass_blur' ? `blur(${style[key]}px)` : `${style[key]}px`}!important`)
  }
  const typography = []
  if (typeof style.font_size === 'number' && Number.isFinite(style.font_size) && style.font_size >= 0) typography.push(`font-size:${style.font_size}px!important`)
  if (['normal','italic'].includes(style.font_style)) typography.push(`font-style:${style.font_style}!important`)
  if ([400,500,600,700,800].includes(style.font_weight)) typography.push(`font-weight:${style.font_weight}!important`)
  const fonts = { system: 'system-ui,sans-serif', segoe: '"Segoe UI",sans-serif', roboto: 'Roboto,Arial,sans-serif', serif: 'Georgia,serif' }
  if (Object.hasOwn(fonts,style.font_family)) typography.push(`font-family:${fonts[style.font_family]}!important`)
  const selected = ':is(.active,.selected,[aria-selected="true"],[aria-pressed="true"],[aria-current="page"])'
  // Normal styling must not erase existing selection/disabled feedback.
  const normal = `${base}:not(:disabled,[aria-disabled="true"]):not(${selected})`
  const enabled = `${base}:not(:disabled,[aria-disabled="true"])`
  const rules = [`:is(${selector}){${typography.join(';')}}`,`${base}{${common.join(';')}}`,`${normal}{${stateCss(style.normal)}}`]
  rules.push(`@media(hover:hover){${enabled}:hover{${stateCss(style.hover)}}}`)
  rules.push(`${enabled}:active{${stateCss(style.pressed)}}`,`${enabled}${selected}{${stateCss(style.selected)}}`,`${enabled}:focus-visible{${stateCss(style.focus)};outline:3px solid #b88616!important;outline-offset:3px}`)
  const motion = `${enabled}:not(.date-link,.date-picker-control,.vera-date-picker-button,.schedule-icon-button,.clear-button):not(.date-toolbar *):not([aria-label*="Clear"]):not([aria-label*="Xóa"])`
  const effects = []
  if (bounded(style.transition_ms,0,600)) effects.push(`${base}{transition:background-color ${style.transition_ms}ms ease,box-shadow ${style.transition_ms}ms ease,transform ${style.transition_ms}ms ease!important}`)
  if (bounded(style.hover_lift,0,6)) effects.push(`@media(hover:hover){${motion}:hover{transform:translateY(-${style.hover_lift}px)!important}}`)
  if (bounded(style.press_sink,0,6)) effects.push(`${motion}:active{transform:translateY(${style.press_sink}px)!important}`)
  rules.push(`@media(prefers-reduced-motion:no-preference){${effects.join('')}}`)
  rules.push(`@media(prefers-reduced-motion:reduce){${base}{transition:none!important;transform:none!important}}`)
  return rules.join('\n')
}
