import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import ShiftBreakSettingsPanel from './ShiftBreakSettingsPanel'
import { staffSecurityApi } from '../lib/staffSecurityApi'

function downloadPortrait(image, username = 'Nhan_Vien') {
  const src = String(image?.src || '')
  if (!src) return
  const anchor = document.createElement('a')
  anchor.href = src
  anchor.download = `${username || 'Nhan_Vien'}_Anh_Nhan_Vien.webp`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

async function copyPlainText(value) {
  const text = String(value || '')
  if (!text) return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch (_) {
    // Safari/private browsing may deny Clipboard API; use the legacy fallback.
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;'
  document.body.appendChild(textarea)
  textarea.select()
  let copied = false
  try { copied = document.execCommand('copy') } catch (_) { copied = false }
  textarea.remove()
  return copied
}

function renderPortraitTextPanel(card, text, statusText, statusType = '') {
  let panel = card.querySelector('[data-portrait-text-panel="true"]')
  if (!panel) {
    panel = document.createElement('div')
    panel.dataset.portraitTextPanel = 'true'
    panel.style.cssText = 'display:grid;gap:8px;margin-top:12px;padding:12px;border:1px solid #cfdcd6;border-radius:12px;background:#f6faf8;'
    card.appendChild(panel)
  }
  panel.textContent = ''

  const heading = document.createElement('strong')
  heading.textContent = 'CHỮ NHẬN DẠNG TỪ ẢNH'
  const status = document.createElement('div')
  status.textContent = statusText
  status.style.cssText = `font-size:11px;font-weight:${statusType ? '800' : '500'};color:${statusType === 'ok' ? '#17603b' : statusType === 'error' ? '#a62a20' : '#4c6259'};`
  panel.append(heading, status)
  if (!text) return

  const textarea = document.createElement('textarea')
  textarea.readOnly = true
  textarea.value = text
  textarea.style.cssText = 'width:100%;min-height:140px;resize:vertical;border:1px solid #c8d6d0;border-radius:9px;background:#fff;padding:10px;font:500 13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#17251f;user-select:text;-webkit-user-select:text;'
  textarea.addEventListener('focus', () => textarea.select())

  const copyButton = document.createElement('button')
  copyButton.type = 'button'
  copyButton.className = 'secondary-button compact'
  copyButton.textContent = 'Sao chép toàn bộ'
  copyButton.onclick = async () => {
    const copied = await copyPlainText(text)
    status.textContent = copied
      ? 'Đã sao chép toàn bộ chữ vào clipboard.'
      : 'Không tự sao chép được. Hãy chọn văn bản rồi dùng Ctrl/Cmd+C.'
    status.style.color = copied ? '#17603b' : '#a62a20'
    status.style.fontWeight = '800'
    textarea.focus()
  }
  panel.append(textarea, copyButton)
}

function findActionButton(side, text) {
  return Array.from(side?.querySelectorAll('.employee-id-actions button') || [])
    .find((button) => String(button.textContent || '').trim().includes(text)) || null
}

function currentPortraitUsername(side) {
  const panel = side?.closest('.staff-form-panel')
  const heading = String(panel?.querySelector('h2')?.textContent || '')
  if (heading.includes('·')) return heading.split('·').slice(1).join('·').trim()
  return String(side?.dataset?.portraitUsername || '').trim()
}

function openPortraitViewer(image, side, username) {
  if (!image?.src || document.querySelector('[data-portrait-viewer="true"]')) return

  const overlay = document.createElement('div')
  overlay.dataset.portraitViewer = 'true'
  overlay.style.cssText = 'position:fixed;inset:0;z-index:12000;background:rgba(7,18,14,.88);display:flex;align-items:center;justify-content:center;padding:16px;'

  const card = document.createElement('div')
  card.style.cssText = 'width:min(920px,100%);max-height:96vh;overflow:auto;background:#fff;border-radius:18px;padding:14px;box-shadow:0 24px 70px rgba(0,0,0,.35);'

  const header = document.createElement('div')
  header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;'
  const title = document.createElement('strong')
  title.textContent = `ẢNH NHÂN VIÊN · ${username || ''}`
  const close = document.createElement('button')
  close.type = 'button'
  close.className = 'secondary-button compact'
  close.textContent = 'Đóng'
  close.onclick = () => overlay.remove()
  header.append(title, close)

  const large = document.createElement('img')
  large.src = image.src
  large.alt = image.alt || 'Ảnh nhân viên'
  large.style.cssText = 'display:block;max-width:100%;max-height:72vh;margin:0 auto;border-radius:14px;object-fit:contain;background:#111;'

  const actions = document.createElement('div')
  actions.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:12px;'

  const addAction = (label, originalText, className = 'secondary-button compact') => {
    const original = findActionButton(side, originalText)
    if (!original) return
    const button = document.createElement('button')
    button.type = 'button'
    button.className = className
    button.textContent = label
    button.onclick = () => {
      overlay.remove()
      original.click()
    }
    actions.appendChild(button)
  }

  addAction('Chụp ảnh', 'Chụp ảnh')
  addAction('Thay ảnh', 'Thay ảnh')

  const download = document.createElement('button')
  download.type = 'button'
  download.className = 'secondary-button compact'
  download.textContent = 'Tải ảnh'
  download.onclick = () => downloadPortrait(image, currentPortraitUsername(side) || username)
  actions.appendChild(download)

  const copyText = document.createElement('button')
  copyText.type = 'button'
  copyText.className = 'secondary-button compact'
  copyText.textContent = 'Sao chép chữ'
  copyText.title = 'Nhận dạng chữ trên ảnh và cho phép chọn/sao chép'
  copyText.onclick = async () => {
    const originalLabel = copyText.textContent
    copyText.disabled = true
    copyText.textContent = 'Đang đọc chữ…'
    renderPortraitTextPanel(card, '', 'Đang nhận dạng chữ trên ảnh…')
    try {
      const response = await fetch(image.src)
      if (!response.ok) throw new Error(`Không đọc được ảnh (HTTP ${response.status}).`)
      const blob = await response.blob()
      const result = await staffSecurityApi.extractImageText(blob)
      const text = String(result?.text || '').trim()
      if (!text) {
        renderPortraitTextPanel(card, '', 'Không nhận dạng được chữ trên ảnh.', 'error')
        return
      }
      const copied = await copyPlainText(text)
      renderPortraitTextPanel(
        card,
        text,
        copied ? 'Đã nhận dạng và sao chép toàn bộ chữ vào clipboard.' : 'Đã nhận dạng. Có thể chọn từng phần văn bản để sao chép.',
        copied ? 'ok' : '',
      )
    } catch (error) {
      renderPortraitTextPanel(card, '', `Không đọc được chữ từ ảnh: ${error?.message || 'lỗi OCR'}`, 'error')
    } finally {
      copyText.disabled = false
      copyText.textContent = originalLabel
    }
  }
  actions.appendChild(copyText)

  addAction('Crop / Xoay', 'Crop / Xoay')
  addAction('Xóa', 'Xóa', 'danger-button compact')

  card.append(header, large, actions)
  overlay.appendChild(card)
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) overlay.remove()
  })
  document.body.appendChild(overlay)
}

export default function EmployeeManagementEnhancements({ user }) {
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const [breakTarget, setBreakTarget] = useState(null)

  useEffect(() => {
    let cancelled = false
    let ownedBreakHost = null
    let timer = null

    const synchronize = () => {
      if (cancelled) return

      // Desktop: keep Hồ sơ immediately before Khóa as requested.
      const table = document.querySelector('.staff-desktop-table .staff-table')
      const headRow = table?.querySelector('thead tr')
      if (headRow) {
        const headers = Array.from(headRow.children)
        const profileIndex = headers.findIndex((cell) => String(cell.textContent || '').trim() === 'Hồ sơ')
        const lockIndex = headers.findIndex((cell) => String(cell.textContent || '').trim() === 'Khóa')
        if (profileIndex >= 0 && lockIndex >= 0 && profileIndex > lockIndex) {
          headRow.insertBefore(headers[profileIndex], headers[lockIndex])
          table.querySelectorAll('tbody tr').forEach((row) => {
            const cells = Array.from(row.children)
            if (cells[profileIndex] && cells[lockIndex]) row.insertBefore(cells[profileIndex], cells[lockIndex])
          })
        }
      }

      // Hồ sơ nhân viên no longer uses Quận/Huyện. Keep the stored legacy value
      // untouched in the database, but remove the field from the edit UI.
      document.querySelectorAll('.staff-form-panel label').forEach((label) => {
        const text = String(label.textContent || '').trim()
        if (text.startsWith('Quận/Huyện')) label.style.display = 'none'
      })

      // There is already one native EmployeeIdentityPanel rendered by EmployeePage.
      // Remove any legacy injected host so the image/CCCD/password section appears once.
      document.querySelectorAll('[data-staff-security-host="true"]').forEach((host) => host.remove())

      // Make the employee portrait itself the primary viewer trigger and add a
      // dedicated download button next to the existing camera/upload/edit controls.
      document.querySelectorAll('.employee-portrait-side').forEach((side) => {
        const image = side.querySelector('.employee-portrait-preview img')
        const actions = side.querySelector('.employee-id-actions')
        const username = currentPortraitUsername(side)
        side.dataset.portraitUsername = username

        if (image) {
          image.style.cursor = 'zoom-in'
          image.title = 'Bấm để phóng to ảnh nhân viên'
          if (!image.dataset.portraitViewerBound) {
            image.dataset.portraitViewerBound = 'true'
            image.addEventListener('click', () => {
              const liveUsername = currentPortraitUsername(side)
              openPortraitViewer(image, side, liveUsername)
            })
          }
        }

        if (image && actions && !actions.querySelector('[data-portrait-download="true"]')) {
          const button = document.createElement('button')
          button.type = 'button'
          button.className = 'secondary-button compact'
          button.dataset.portraitDownload = 'true'
          button.textContent = 'Tải ảnh'
          button.addEventListener('click', () => downloadPortrait(image, currentPortraitUsername(side)))
          const cropButton = findActionButton(side, 'Crop / Xoay')
          if (cropButton) actions.insertBefore(button, cropButton)
          else actions.appendChild(button)
        }
      })

      // Admin-only break configuration belongs at the very bottom of NHÂN VIÊN.
      const staffPage = document.querySelector('.staff-page')
      const listPanel = staffPage?.querySelector('.staff-list-panel')
      if (isAdmin && staffPage && listPanel) {
        let host = staffPage.querySelector('[data-shift-break-settings-host="true"]')
        if (!host) {
          host = document.createElement('div')
          host.dataset.shiftBreakSettingsHost = 'true'
          ownedBreakHost = host
        }
        if (staffPage.lastElementChild !== host) staffPage.appendChild(host)
        setBreakTarget((current) => current === host ? current : host)
      } else {
        if (ownedBreakHost?.isConnected) ownedBreakHost.remove()
        ownedBreakHost = null
        setBreakTarget(null)
      }
    }

    const schedule = () => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(synchronize, 20)
    }
    synchronize()
    const observer = new MutationObserver(schedule)
    observer.observe(document.body, { childList: true, subtree: true })
    document.addEventListener('change', schedule, true)
    document.addEventListener('click', schedule, true)
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
      observer.disconnect()
      document.removeEventListener('change', schedule, true)
      document.removeEventListener('click', schedule, true)
      if (ownedBreakHost?.isConnected) ownedBreakHost.remove()
      document.querySelector('[data-portrait-viewer="true"]')?.remove()
    }
  }, [isAdmin])

  if (!isAdmin) return null
  return <>{breakTarget && createPortal(<ShiftBreakSettingsPanel />, breakTarget)}</>
}
