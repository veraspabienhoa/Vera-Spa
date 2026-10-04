export function canSharePdf(file, browser = navigator) {
  try { return Boolean(browser.share && browser.canShare?.({ files: [file] })) } catch { return false }
}

// Keep this call directly inside a user click: downloading first can consume
// the transient activation required by Safari/iOS and other share sheets.
export function shareCustomerCountPdf(file, browser = navigator) {
  if (!canSharePdf(file, browser)) throw new Error('Thiết bị không hỗ trợ chia sẻ file. Hãy tải PDF rồi gửi qua Zalo.')
  return browser.share({ files: [file], title: 'VERA SPA - Báo cáo số lượng khách' })
}
