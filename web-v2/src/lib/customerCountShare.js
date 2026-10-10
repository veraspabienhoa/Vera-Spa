function canShareReport(file, browser) {
  try { return Boolean(file && typeof browser?.share === 'function' && browser.canShare?.({ files: [file] })) } catch { return false }
}

export function canSharePdf(file, browser = globalThis.navigator) {
  return canShareReport(file, browser)
}

export function canSharePng(file, browser = globalThis.navigator) {
  return canShareReport(file, browser)
}

function shareReport(file, format, browser) {
  if (!canShareReport(file, browser)) throw new Error(`Thiết bị không hỗ trợ chia sẻ file. Hãy tải ${format} rồi gửi qua Zalo.`)
  return browser.share({ files: [file], title: 'VERA SPA - Báo cáo số lượng khách' })
}

// Keep these calls synchronous inside a user click: preparing/downloading first
// consumes the transient activation required by Safari/iOS and other share sheets.
export function shareCustomerCountPdf(file, browser = globalThis.navigator) {
  return shareReport(file, 'PDF', browser)
}

export function shareCustomerCountPng(file, browser = globalThis.navigator) {
  return shareReport(file, 'PNG', browser)
}
