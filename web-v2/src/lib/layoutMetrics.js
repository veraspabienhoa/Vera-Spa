export function readLayoutMetrics(element) {
  if (!element?.isConnected) return null
  const css = getComputedStyle(element), rect = element.getBoundingClientRect()
  const number = value => Math.round(parseFloat(value) || 0)
  const color = value => { if (!value || value === 'transparent' || /rgba\([^)]*,\s*0(?:\.0+)?\)$/.test(value)) return undefined; const rgb = value?.match(/^rgba?\(\s*(\d+)[, ]+\s*(\d+)[, ]+\s*(\d+)/); return rgb ? '#' + rgb.slice(1,4).map(v => Number(v).toString(16).padStart(2,'0')).join('') : /^#[0-9a-f]{6}$/i.test(value) ? value : undefined }
  let background = color(css.backgroundColor)
  for (let parent=element.parentElement; !background && parent; parent=parent.parentElement) background=color(getComputedStyle(parent).backgroundColor)
  const font = css.fontFamily.toLowerCase()
  return { width: Math.round(rect.width), height: Math.round(rect.height), rawFont: css.fontFamily,
    appearance: { font_size: parseFloat(css.fontSize) || 0, font_style: css.fontStyle, font_family: font.includes('segoe') ? 'segoe' : /roboto|arial/.test(font) ? 'roboto' : /georgia/.test(font) ? 'serif' : 'system', font_weight: css.fontWeight === 'bold' ? 700 : number(css.fontWeight) || 400, radius: number(css.borderTopLeftRadius), border_width: number(css.borderTopWidth), padding_x: number(css.paddingLeft), padding_y: number(css.paddingTop), normal: { text: color(css.color), background: background || '#ffffff', border: color(css.borderTopColor) } } }
}
export function resizeDimensions(width, height, dx, dy, parentWidth) {
  return { width: Math.round(Math.max(32,Math.min(2400,parentWidth || 2400,width+dx))), height: Math.round(Math.max(24,Math.min(1600,height+dy))) }
}
