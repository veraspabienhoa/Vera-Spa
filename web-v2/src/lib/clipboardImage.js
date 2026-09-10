export async function copyPngToClipboard(loadImage) {
  if (!globalThis.navigator?.clipboard?.write || !globalThis.ClipboardItem) {
    throw new Error('Trình duyệt chưa hỗ trợ copy ảnh. Hãy mở bằng Safari hoặc Chrome mới nhất và thử lại.')
  }
  const image = Promise.resolve().then(loadImage).then(blob => {
    if (blob?.type !== 'image/png' || !blob.size) throw new Error('Không nhận được ảnh bảng tua hợp lệ. Hãy thử lại.')
    return blob
  })
  // Observe fetch failures even if clipboard permission is denied immediately.
  image.catch(() => {})
  // Start the write during the click; awaiting the image first loses Safari's
  // user gesture. The PNG stays in memory and is never offered as a download.
  await navigator.clipboard.write([new ClipboardItem({ 'image/png': image })])
}
