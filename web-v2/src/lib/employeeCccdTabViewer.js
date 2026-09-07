const normalizeText = (value) => String(value || '').replace(/\s+/g, ' ').trim()

const actionText = (button) => normalizeText(button?.textContent)

function waitForImage(card, timeoutMs = 4500) {
  const current = card?.querySelector('.employee-id-preview img')
  if (current?.src) return Promise.resolve(current)
  return new Promise((resolve) => {
    const started = Date.now()
    const timer = window.setInterval(() => {
      const image = card?.querySelector('.employee-id-preview img')
      if (image?.src || Date.now() - started >= timeoutMs) {
        window.clearInterval(timer)
        resolve(image?.src ? image : null)
      }
    }, 80)
  })
}

async function ensureCardImage(card) {
  let image = card?.querySelector('.employee-id-preview img')
  if (image?.src) return image
  const viewButton = Array.from(card?.querySelectorAll('.employee-id-actions button') || [])
    .find((button) => /^Xem$/i.test(actionText(button)))
  if (!viewButton || viewButton.disabled) return null
  viewButton.click()
  image = await waitForImage(card)
  return image?.src ? image : null
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Không chuyển được ảnh CCCD để mở tab mới.'))
    reader.readAsDataURL(blob)
  })
}

async function imageToPortableUrl(image) {
  if (!image?.src) return ''
  try {
    const response = await fetch(image.src)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return await blobToDataUrl(await response.blob())
  } catch {
    return image.src
  }
}

function employeeLabel(panel) {
  const staffPanel = panel.closest('.staff-form-panel')
  const heading = normalizeText(staffPanel?.querySelector('h2')?.textContent)
  if (heading.includes('·')) return heading.split('·').slice(1).join('·').trim()
  return ''
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function renderTab(tab, employee, frontUrl, backUrl) {
  if (!tab || tab.closed) return
  const employeeText = employee ? ` · ${escapeHtml(employee)}` : ''
  const imageBlock = (label, url) => `
    <section class="side">
      <h2>${label}</h2>
      <div class="image-wrap">${url
        ? `<img src="${url}" alt="CCCD ${label.toLowerCase()}"/>`
        : '<div class="missing">Chưa có ảnh CCCD</div>'}</div>
    </section>`

  tab.document.open()
  tab.document.write(`<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>VERA SPA - CCCD${employeeText}</title>
<style>
  *{box-sizing:border-box}body{margin:0;background:#eef3f1;color:#16241e;font-family:Arial,Helvetica,sans-serif}
  header{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px;background:#fff;border-bottom:1px solid #d9e3df}
  h1{margin:0;font-size:18px}header .actions{display:flex;gap:8px;flex-wrap:wrap}button{border:1px solid #cbd7d2;background:#fff;border-radius:9px;padding:8px 12px;font-weight:700;cursor:pointer}
  main{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px;max-width:1500px;margin:0 auto}.side{background:#fff;border:1px solid #dbe4e0;border-radius:14px;padding:12px;min-width:0}.side h2{margin:0 0 10px;font-size:15px}
  .image-wrap{min-height:260px;background:#111;border-radius:10px;display:flex;align-items:center;justify-content:center;overflow:hidden}.image-wrap img{display:block;width:100%;height:auto;max-height:78vh;object-fit:contain}.missing{color:#fff;padding:30px;text-align:center}
  @media(max-width:800px){main{grid-template-columns:1fr;padding:8px;gap:8px}header{padding:10px 12px}.image-wrap{min-height:180px}}
  @media print{header .actions{display:none}body{background:#fff}main{max-width:none;padding:0}.side{break-inside:avoid;border:none}}
</style>
</head>
<body>
<header><h1>CĂN CƯỚC CÔNG DÂN${employeeText}</h1><div class="actions"><button onclick="window.print()">In</button><button onclick="window.close()">Đóng</button></div></header>
<main>${imageBlock('Mặt trước', frontUrl)}${imageBlock('Mặt sau', backUrl)}</main>
</body>
</html>`)
  tab.document.close()
  try { tab.opener = null } catch { /* browser may block this assignment */ }
}

async function openBothSides(panel) {
  const tab = window.open('', '_blank')
  if (!tab) {
    window.alert('Trình duyệt đang chặn tab mới. Hãy cho phép pop-up cho app.veraspa.vn rồi thử lại.')
    return
  }
  tab.document.write('<!doctype html><meta charset="utf-8"><title>VERA SPA - CCCD</title><p style="font-family:Arial;padding:20px">Đang tải CCCD...</p>')

  const cards = Array.from(panel.querySelectorAll('.employee-identity-grid .employee-id-side')).slice(0, 2)
  const [frontCard, backCard] = cards
  try {
    const [frontImage, backImage] = await Promise.all([
      ensureCardImage(frontCard),
      ensureCardImage(backCard),
    ])
    const [frontUrl, backUrl] = await Promise.all([
      imageToPortableUrl(frontImage),
      imageToPortableUrl(backImage),
    ])
    renderTab(tab, employeeLabel(panel), frontUrl, backUrl)
  } catch (error) {
    if (!tab.closed) {
      tab.document.body.innerHTML = `<p style="font-family:Arial;padding:20px;color:#a62a20">Không mở được CCCD: ${escapeHtml(error?.message || 'Lỗi không xác định')}</p>`
    }
  }
}

function enhancePanel(panel) {
  const cards = panel.querySelectorAll('.employee-identity-grid .employee-id-side')
  if (cards.length < 2) return
  const host = panel.querySelector('.employee-profile-export')
  if (!host || host.querySelector('[data-open-cccd-tab="true"]')) return

  host.style.gap = '8px'
  host.style.flexWrap = 'wrap'
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'secondary-button'
  button.dataset.openCccdTab = 'true'
  button.textContent = 'Mở CCCD trong tab mới'
  button.title = 'Mở cùng lúc mặt trước và mặt sau CCCD trong một tab mới'
  button.addEventListener('click', () => void openBothSides(panel))
  host.insertBefore(button, host.firstChild)
}

let scheduled = false
function refresh() {
  if (scheduled) return
  scheduled = true
  window.requestAnimationFrame(() => {
    scheduled = false
    document.querySelectorAll('.employee-identity-panel').forEach(enhancePanel)
  })
}

export function startEmployeeCccdTabViewer() {
  if (window.__veraEmployeeCccdTabViewerStarted) return
  window.__veraEmployeeCccdTabViewerStarted = true
  refresh()
  const observer = new MutationObserver(refresh)
  observer.observe(document.body, { childList: true, subtree: true })
}
