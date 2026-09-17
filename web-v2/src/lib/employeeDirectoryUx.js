let scheduled = false

function ensureStyles() {
  if (document.getElementById('vera-employee-directory-ux-style')) return
  const style = document.createElement('style')
  style.id = 'vera-employee-directory-ux-style'
  style.textContent = `
    .vera-list-name-search{display:flex;align-items:center;gap:9px;margin:10px 0 4px;padding:9px 12px;border:1px solid #d7e1dc;border-radius:11px;background:#fff}
    .vera-list-name-search>span{font-size:15px;line-height:1}.vera-list-name-search input{width:100%;min-width:0;border:0!important;outline:0!important;box-shadow:none!important;background:transparent!important;padding:3px 0!important;font-weight:700}
    .vera-profile-header-actions{margin-left:auto;display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
    .vera-profile-header-actions .vera-profile-top-close{min-height:44px!important;padding:10px 18px!important;font-size:13px!important;font-weight:900!important;border-width:2px!important}
    .vera-profile-header-actions .vera-profile-save-top,.vera-profile-header-actions .vera-profile-refresh-top{min-height:42px!important;padding:9px 14px!important;font-size:12px!important;font-weight:900!important}
    @media(max-width:700px){.vera-profile-header-actions{width:100%;display:grid;grid-template-columns:1fr 1fr}.vera-profile-header-actions .vera-profile-top-close{grid-column:1/-1;width:100%}.vera-list-name-search{margin-top:8px}}
  `
  document.head.appendChild(style)
}

function ensureListSearch() {
  const panel = document.querySelector('.staff-list-panel')
  // EmployeePage owns one React-controlled search field in the toolbar.
  // Never inject a second input into React's list subtree: when filtering
  // removes rows, that unmanaged sibling can break DOM reconciliation and
  // leave the application on a blank screen.
  panel?.querySelector('.vera-list-name-search')?.remove()
}

function ensureProfileHeaderActions() {
  // Legacy versions imperatively appended buttons inside React-owned profile headers.
  // Closing/filtering the profile could then make React reconcile nodes that had been
  // moved or removed outside React, producing a fatal blank-screen DOM exception.
  // EmployeePage now renders these controls itself; only remove stale legacy nodes.
  document.querySelectorAll('.vera-profile-header-actions').forEach((node) => node.remove())
}

function reconcile() {
  ensureListSearch()
  ensureProfileHeaderActions()
}

export function startEmployeeDirectoryUx() {
  if (window.__veraEmployeeDirectoryUxStarted) return
  window.__veraEmployeeDirectoryUxStarted = true
  ensureStyles()

  const schedule = () => {
    if (scheduled) return
    scheduled = true
    window.requestAnimationFrame(() => {
      scheduled = false
      reconcile()
    })
  }

  const observer = new MutationObserver(schedule)
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'class', 'value'] })
  document.addEventListener('click', schedule, true)
  document.addEventListener('input', schedule, true)
  document.addEventListener('change', schedule, true)
  window.setInterval(reconcile, 1200)
  schedule()
}
