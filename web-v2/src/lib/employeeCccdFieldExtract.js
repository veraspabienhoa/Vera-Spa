import { staffSecurityApi } from './staffSecurityApi'

const normalizeText = (value) => String(value || '').replace(/\s+/g, ' ').trim()
const foldText = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLowerCase()

function validVnDate(value) {
  const match = String(value || '').match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/)
  if (!match) return ''
  const day = Number(match[1])
  const month = Number(match[2])
  const year = Number(match[3])
  const date = new Date(year, month - 1, day)
  if (date.getFullYear() !== year || date.getMonth() + 1 !== month || date.getDate() !== day) return ''
  return `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}`
}

function extractCccdNumber(rawText) {
  const folded = foldText(rawText)
  const labeled = folded.match(/(?:\bso\b|\bno\b)[^0-9]{0,24}([0-9][0-9 .-]{9,24}[0-9])/i)
  if (labeled) {
    const digits = labeled[1].replace(/\D/g, '')
    if (digits.length === 12) return digits
  }

  const blocks = String(rawText || '').match(/[0-9][0-9 .-]{10,28}[0-9]/g) || []
  for (const block of blocks) {
    const digits = block.replace(/\D/g, '')
    if (digits.length === 12) return digits
  }
  return ''
}

function extractIssueDate(rawText) {
  const folded = foldText(rawText)
  const labeled = folded.match(/(?:ngay\s*cap|date\s*of\s*issue|ngay\s*,?\s*thang\s*,?\s*nam|date\s*,?\s*month\s*,?\s*year)[^0-9]{0,80}(\d{1,2}[./-]\d{1,2}[./-]\d{4})/i)
  const labeledDate = validVnDate(labeled?.[1])
  if (labeledDate) return labeledDate

  const candidates = folded.match(/\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b/g) || []
  for (const candidate of candidates) {
    const parsed = validVnDate(candidate)
    if (parsed) return parsed
  }
  return ''
}

function extractIssuePlace(rawText) {
  const rawLines = String(rawText || '').split(/\r?\n/).map((line) => normalizeText(line)).filter(Boolean)
  const foldedLines = rawLines.map((line) => foldText(line))

  for (let index = 0; index < foldedLines.length; index += 1) {
    const folded = foldedLines[index]
    if (!folded.includes('noi cap') && !folded.includes('place of issue')) continue
    const raw = rawLines[index]
    const afterColon = raw.includes(':') ? normalizeText(raw.split(':').slice(1).join(':')) : ''
    if (afterColon.length >= 5) return afterColon.slice(0, 240)
    const next = normalizeText(rawLines[index + 1] || '')
    if (next.length >= 5) return next.slice(0, 240)
  }

  const folded = foldText(rawText)
  if (folded.includes('quan ly hanh chinh ve trat tu xa hoi')) {
    return 'Cục Cảnh sát quản lý hành chính về trật tự xã hội'
  }
  if (folded.includes('dlqg ve dan cu') || folded.includes('dang ky quan ly cu tru') || folded.includes('dkql cu tru')) {
    return 'Cục Cảnh sát đăng ký, quản lý cư trú và dữ liệu quốc gia về dân cư'
  }
  return ''
}

function parseTargetedFields(rawText, side) {
  if (side === 'front') {
    const cccdNumber = extractCccdNumber(rawText)
    return cccdNumber ? { cccd_number: cccdNumber } : {}
  }
  const issueDate = extractIssueDate(rawText)
  const issuePlace = extractIssuePlace(rawText)
  return {
    ...(issueDate ? { cccd_issue_date: issueDate } : {}),
    ...(issuePlace ? { cccd_issue_place: issuePlace } : {}),
  }
}

function cardSide(card) {
  const title = foldText(card?.querySelector('.employee-id-side-head strong')?.textContent)
  if (title.includes('mat truoc')) return 'front'
  if (title.includes('mat sau')) return 'back'
  return ''
}

function findViewButton(card) {
  return Array.from(card?.querySelectorAll('.employee-id-actions button') || [])
    .find((button) => normalizeText(button.textContent).toLowerCase() === 'xem') || null
}

function waitForImage(card, timeoutMs = 5000) {
  const current = card?.querySelector('.employee-id-preview img')
  if (current?.src) return Promise.resolve(current)
  return new Promise((resolve) => {
    const started = Date.now()
    const timer = window.setInterval(() => {
      const image = card?.querySelector('.employee-id-preview img')
      if (image?.src || Date.now() - started >= timeoutMs) {
        window.clearInterval(timer)
        resolve(image || null)
      }
    }, 80)
  })
}

async function imageBlobForCard(card) {
  let image = card?.querySelector('.employee-id-preview img')
  if (!image?.src) {
    const viewButton = findViewButton(card)
    if (!viewButton || viewButton.disabled) throw new Error('Chưa có ảnh CCCD đã lưu để đọc.')
    viewButton.click()
    image = await waitForImage(card)
  }
  if (!image?.src) throw new Error('Không tải được ảnh CCCD để nhận dạng.')
  const response = await fetch(image.src)
  if (!response.ok) throw new Error(`Không đọc được ảnh CCCD (HTTP ${response.status}).`)
  return response.blob()
}

function profileUsername(card) {
  const panel = card?.closest('.staff-form-panel')
  const heading = normalizeText(panel?.querySelector('h2')?.textContent)
  return heading.startsWith('SỬA HỒ SƠ ·') ? normalizeText(heading.slice('SỬA HỒ SƠ ·'.length)) : ''
}

function nativeSetValue(control, value) {
  if (!control) return false
  const prototype = control instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : control instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set
  if (setter) setter.call(control, value)
  else control.value = value
  control.dispatchEvent(new Event('input', { bubbles: true }))
  control.dispatchEvent(new Event('change', { bubbles: true }))
  return true
}

function findProfileControl(card, labelPrefix) {
  const scope = card?.closest('.profile-form') || card?.closest('.staff-form-panel')
  if (!scope) return null
  const labels = Array.from(scope.querySelectorAll('label'))
  const label = labels.find((item) => normalizeText(item.childNodes?.[0]?.textContent || item.textContent).startsWith(labelPrefix))
  if (!label) return null
  return label.querySelector('input:not([type="hidden"]):not(.vera-native-date-picker), select, textarea')
}

function applyFieldsToVisibleProfile(card, fields) {
  if (fields.cccd_number) nativeSetValue(findProfileControl(card, 'Số Căn cước'), fields.cccd_number)
  if (fields.cccd_issue_date) nativeSetValue(findProfileControl(card, 'Ngày cấp'), fields.cccd_issue_date)
  if (fields.cccd_issue_place) nativeSetValue(findProfileControl(card, 'Nơi cấp'), fields.cccd_issue_place)
}

function applyTargetedFields(card, fields) {
  const username = profileUsername(card)
  if (username) {
    window.dispatchEvent(new CustomEvent('vera-identity-extracted', { detail: { username, fields } }))
  } else {
    applyFieldsToVisibleProfile(card, fields)
  }
}

function setStatus(card, message, type = '') {
  let status = card.querySelector('[data-vera-cccd-target-status="true"]')
  if (!status) {
    status = document.createElement('div')
    status.dataset.veraCccdTargetStatus = 'true'
    status.className = 'vera-cccd-target-status'
    card.appendChild(status)
  }
  status.className = `vera-cccd-target-status ${type}`.trim()
  status.textContent = message
}

async function runTargetedExtraction(card, button) {
  const side = cardSide(card)
  if (!side) return
  const original = button.textContent
  button.disabled = true
  button.textContent = 'Đang đọc…'
  setStatus(card, 'Đang nhận dạng thông tin từ ảnh CCCD…')
  try {
    const blob = await imageBlobForCard(card)
    const result = await staffSecurityApi.extractImageText(blob)
    const fields = parseTargetedFields(result?.text || '', side)
    if (side === 'front' && !fields.cccd_number) {
      throw new Error('Không nhận dạng được Số Căn cước. Hãy Crop sát thẻ hoặc dùng ảnh rõ hơn.')
    }
    if (side === 'back' && !fields.cccd_issue_date && !fields.cccd_issue_place) {
      throw new Error('Không nhận dạng được Ngày cấp hoặc Nơi cấp. Hãy Crop sát thẻ hoặc dùng ảnh rõ hơn.')
    }
    applyTargetedFields(card, fields)
    if (side === 'front') {
      setStatus(card, `Đã gắn Số Căn cước: ${fields.cccd_number}`, 'ok')
    } else {
      const details = [fields.cccd_issue_date && `Ngày cấp: ${fields.cccd_issue_date}`, fields.cccd_issue_place && `Nơi cấp: ${fields.cccd_issue_place}`].filter(Boolean)
      const missing = [!fields.cccd_issue_date && 'Ngày cấp', !fields.cccd_issue_place && 'Nơi cấp'].filter(Boolean)
      setStatus(card, `${details.join(' · ')}${missing.length ? ` · Chưa đọc được ${missing.join(' và ')}` : ''}`, missing.length ? 'warn' : 'ok')
    }
  } catch (error) {
    setStatus(card, error?.message || 'Không nhận dạng được thông tin CCCD.', 'error')
  } finally {
    button.disabled = false
    button.textContent = original
  }
}

function ensureStyle() {
  if (document.getElementById('vera-cccd-targeted-extract-style')) return
  const style = document.createElement('style')
  style.id = 'vera-cccd-targeted-extract-style'
  style.textContent = `
    .vera-cccd-target-status{margin-top:8px;padding:7px 9px;border-radius:8px;background:#f1f5f3;color:#53645d;font-size:11px;line-height:1.4}
    .vera-cccd-target-status.ok{background:#edf8f2;color:#17603b;font-weight:800}
    .vera-cccd-target-status.warn{background:#fff8df;color:#875f00;font-weight:800}
    .vera-cccd-target-status.error{background:#fff1f0;color:#a62a20;font-weight:800}
  `
  document.head.appendChild(style)
}

function refreshTargetButtons() {
  document.querySelectorAll('.employee-id-side:not(.draft)').forEach((card) => {
    const side = cardSide(card)
    if (!side) return
    const actions = card.querySelector('.employee-id-actions')
    const hasSavedImage = Boolean(findViewButton(card))
    if (!actions || !hasSavedImage) return
    if (actions.querySelector('[data-vera-cccd-target-extract="true"]')) return

    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'secondary-button compact'
    button.dataset.veraCccdTargetExtract = 'true'
    button.textContent = side === 'front' ? 'Lấy Số CCCD' : 'Lấy Ngày cấp & Nơi cấp'
    button.title = side === 'front'
      ? 'Đọc Số Căn cước từ ảnh mặt trước và gắn vào ô Số Căn cước'
      : 'Đọc Ngày cấp và Nơi cấp từ ảnh mặt sau rồi gắn vào hồ sơ'
    button.addEventListener('click', () => void runTargetedExtraction(card, button))

    const deleteButton = Array.from(actions.querySelectorAll('button')).find((item) => normalizeText(item.textContent).includes('Xóa'))
    if (deleteButton) actions.insertBefore(button, deleteButton)
    else actions.appendChild(button)
  })
}

let scheduled = false
function scheduleRefresh() {
  if (scheduled) return
  scheduled = true
  window.requestAnimationFrame(() => {
    scheduled = false
    refreshTargetButtons()
  })
}

export function startEmployeeCccdFieldExtract() {
  if (window.__veraEmployeeCccdFieldExtractStarted) return
  window.__veraEmployeeCccdFieldExtractStarted = true
  ensureStyle()
  scheduleRefresh()
  const observer = new MutationObserver(scheduleRefresh)
  observer.observe(document.body, { childList: true, subtree: true })
}
