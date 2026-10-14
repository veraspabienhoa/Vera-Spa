export async function copyPngToClipboard(loadImage) {
  if (!globalThis.navigator?.clipboard?.write || !globalThis.ClipboardItem) {
    throw new Error('Trình duyệt chưa hỗ trợ copy ảnh. Hãy mở bằng Safari hoặc Chrome mới nhất và thử lại.')
  }
  const image = Promise.resolve().then(loadImage).then(blob => {
    if (blob?.type !== 'image/png' || !blob.size) throw new Error('Không nhận được ảnh PNG hợp lệ. Hãy thử lại.')
    return new Blob([blob], { type: 'image/png' })
  })
  // Browsers may translate a rejected item-data promise to NotAllowedError.
  // Retain the real image failure, and consume late rejections after a denial.
  let imageFailure
  image.catch(error => { imageFailure = { error } })
  // Start clipboard.write during the original click. Waiting for SVG/image/canvas
  // rendering first loses transient user activation on Chrome/Windows, so the
  // button appears to do nothing and the PNG cannot be pasted into Zalo.
  try {
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': image })])
  } catch (error) {
    if (imageFailure) throw imageFailure.error
    // Older implementations may reject Promise-backed values with TypeError.
    // Never retry a permission/security denial or wait for an image after one:
    // callers use the original error name to show the appropriate recovery UI.
    if (error?.name !== 'TypeError') throw error
    const png = await image
    if (navigator.userActivation?.isActive === false) throw error
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })])
  }
}


function cloneWithComputedStyles(source) {
  if (source.nodeType !== 1) return source.cloneNode(true)
  const clone = source.cloneNode(false)
  const computed = globalThis.getComputedStyle?.(source)
  if (computed) {
    const declarations = []
    for (const property of computed) declarations.push(`${property}:${computed.getPropertyValue(property)};`)
    clone.setAttribute('style', declarations.join(''))
  }
  for (const child of source.childNodes) clone.appendChild(cloneWithComputedStyles(child))
  return clone
}

// Draw report bars from their already-filtered, sorted DOM data. No SVG
// foreignObject, external fonts/images or blob-backed SVG can taint this canvas.
export async function employeeChartPng(element, { scale = 2, background = '#ffffff' } = {}) {
  const rows = [...element.querySelectorAll('.employee-revenue-chart-row')]
  const width = 1100, rowHeight = 42, height = 100 + Math.max(1, rows.length) * rowHeight
  const ratio = Math.max(1, Math.min(2, Number(scale) || 1))
  if (width * height * ratio * ratio > 36000000) throw new Error('Biểu đồ quá lớn. Hãy thu hẹp bộ lọc trước khi chụp.')
  const canvas = document.createElement('canvas')
  canvas.width = width * ratio; canvas.height = height * ratio
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Trình duyệt không tạo được ảnh báo cáo.')
  ctx.scale(ratio, ratio); ctx.fillStyle = background; ctx.fillRect(0, 0, width, height)
  ctx.fillStyle = '#173d2f'; ctx.font = 'bold 24px sans-serif'
  ctx.fillText(element.querySelector('h4')?.textContent || 'Báo cáo theo nhân viên', 24, 38)
  ctx.font = 'bold 15px sans-serif'
  if (rows.length) {
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('STT', 44, 60)
    ctx.textAlign = 'left'; ctx.fillText('Nhân viên', 80, 60)
  }
  ctx.textBaseline = 'alphabetic'; ctx.font = '17px sans-serif'
  if (!rows.length) ctx.fillText('Không có dữ liệu phù hợp bộ lọc.', 24, 92)
  rows.forEach((row, index) => {
    const y = 82 + index * rowHeight
    const name = row.querySelector('.employee-revenue-chart-name')?.textContent || ''
    const percent = Math.max(0, Math.min(100, parseFloat(row.querySelector('i')?.style.width) || 0))
    ctx.fillStyle = '#173d2f'
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText(String(index + 1), 44, y - 2, 40)
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'
    ctx.fillText(name, 80, y + 5, 224)
    ctx.fillStyle = '#e6eee9'; ctx.fillRect(320, y - 14, 620, 24)
    ctx.fillStyle = '#205540'; ctx.fillRect(320, y - 14, 620 * percent / 100, 24)
    const value = row.querySelector('strong:not([data-snapshot-ignore])')
    if (value) { ctx.textAlign = 'right'; ctx.fillText(value.textContent, width - 24, y + 5, 120); ctx.textAlign = 'left' }
  })
  return new Promise((resolve, reject) => {
    try { canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Không tạo được ảnh PNG.')), 'image/png') }
    catch (error) { reject(error) }
  })
}

export async function elementToPngBlob(element, { scale = 2, background = '#ffffff' } = {}) {
  if (!element || !globalThis.document) throw new Error('Không tìm thấy khu vực cần chụp ảnh.')
  if (element.matches?.('.employee-revenue-chart')) return employeeChartPng(element, { scale, background })
  const width = Math.max(1, Math.ceil(Math.max(element.scrollWidth || 0, element.getBoundingClientRect?.().width || 0)))
  const height = Math.max(1, Math.ceil(Math.max(element.scrollHeight || 0, element.getBoundingClientRect?.().height || 0)))
  const clone = cloneWithComputedStyles(element)
  clone.querySelectorAll?.('[data-snapshot-ignore]').forEach(node => node.remove())
  if (clone.style) {
    clone.style.width = `${width}px`
    clone.style.maxWidth = 'none'
    clone.style.height = 'auto'
    clone.style.maxHeight = 'none'
    clone.style.overflow = 'visible'
    clone.style.background = background
  }
  const wrapper = document.createElement('div')
  wrapper.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml')
  wrapper.style.width = `${width}px`
  wrapper.style.minHeight = `${height}px`
  wrapper.style.background = background
  wrapper.appendChild(clone)
  const markup = new XMLSerializer().serializeToString(wrapper)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><foreignObject x="0" y="0" width="100%" height="100%">${markup}</foreignObject></svg>`
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }))
  try {
    const image = new Image()
    await new Promise((resolve, reject) => {
      image.onload = resolve
      image.onerror = () => reject(new Error('Không dựng được ảnh báo cáo từ giao diện hiện tại.'))
      image.src = url
    })
    const canvas = document.createElement('canvas')
    const safeScale = Math.max(1, Math.min(3, Number(scale) || 1))
    canvas.width = Math.max(1, Math.round(width * safeScale))
    canvas.height = Math.max(1, Math.round(height * safeScale))
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Trình duyệt không tạo được ảnh báo cáo.')
    context.scale(safeScale, safeScale)
    context.fillStyle = background
    context.fillRect(0, 0, width, height)
    context.drawImage(image, 0, 0, width, height)
    const png = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
    if (!png) throw new Error('Không tạo được ảnh PNG của báo cáo.')
    return png
  } finally {
    URL.revokeObjectURL(url)
  }
}
