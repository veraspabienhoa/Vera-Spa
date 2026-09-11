export const tipAmount = value => Number(String(value ?? '').replace(/\D/g, ''))
export const tipMoney = value => `${Number(value || 0).toLocaleString('vi-VN')} đ`
export const sortedTipCards = cards => [...(cards || [])].sort((a, b) => Number(a.amount) - Number(b.amount))
export const receiptNumber = value => String(value || '').replace(/^LIVE-/, 'VERA-')
export function paymentQrUrl(bank, amount, reference = 'VERA SPA') {
  if (!bank?.enabled || !/^[a-zA-Z0-9]{2,20}$/.test(bank.bank_id || '') || !/^\d{6,19}$/.test(bank.account_no || '') || !Number.isSafeInteger(amount) || amount <= 0 || amount > 10000000000) return ''
  const params = new URLSearchParams({ amount: String(amount), addInfo: receiptNumber(reference), accountName: bank.account_name || '' })
  return `https://img.vietqr.io/image/${bank.bank_id}-${bank.account_no}-compact2.png?${params}`
}
