export async function copyPngToClipboard(loadImage) {
  if (!globalThis.navigator?.clipboard?.write || !globalThis.ClipboardItem) {
    throw new Error('Trình duyệt chưa hỗ trợ copy ảnh. Hãy mở bằng Safari hoặc Chrome mới nhất và thử lại.')
  }
  const image = Promise.resolve().then(loadImage).then(blob => {
    if (blob?.type !== 'image/png' || !blob.size) throw new Error('Không nhận được ảnh PNG hợp lệ. Hãy thử lại.')
    return new Blob([blob], { type: 'image/png' })
  })
  const userAgent = String(globalThis.navigator?.userAgent || '')
  const safari = /Safari/i.test(userAgent) && !/(Chrome|Chromium|CriOS|Edg|OPR)/i.test(userAgent)
  if (safari) {
    // Safari must start clipboard.write while the click still owns transient activation.
    image.catch(() => {})
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': image })])
    return
  }
  // Chromium/Windows exposes the PNG to native applications (including Zalo)
  // reliably when ClipboardItem receives a concrete Blob instead of a Promise.
  const png = await image
  await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })])
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

export async function elementToPngBlob(element, { scale = 2, background = '#ffffff' } = {}) {
  if (!element || !globalThis.document) throw new Error('Không tìm thấy khu vực cần chụp ảnh.')
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
