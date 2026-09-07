import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import ShiftBreakSettingsPanel from './ShiftBreakSettingsPanel'

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
