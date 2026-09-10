function removeToolbarProxy(select) {
  if (!(select instanceof HTMLSelectElement)) return
  const wrapper = select.__veraTypingWrapper
    || (select.nextElementSibling?.classList?.contains('vera-typing-select') ? select.nextElementSibling : null)
  if (wrapper) {
    wrapper.__veraTypingMenu?.remove?.()
    wrapper.remove()
  }
  select.__veraTypingWrapper = null
  select.classList.remove('vera-typing-select-source')

  // Keep this marker so employeeDirectoryUx does not wrap the toolbar again.
  // The real React-owned select is the single source of truth for filter state.
  select.dataset.veraTypingSearch = '1'
}

function restoreToolbar() {
  const toolbar = document.querySelector('.staff-control-panel .staff-toolbar')
  if (!toolbar) return

  // Keep other toolbar filters on native React-owned selects. The employee
  // field is owned by the shared EmployeeSelector.
  toolbar.querySelectorAll('select').forEach(removeToolbarProxy)

  const employeeSelect = toolbar.querySelector('[data-employee-selector] input[type="search"]')
  if (employeeSelect instanceof HTMLInputElement) employeeSelect.dataset.veraToolbarStateSynced = '1'
}

function removeDuplicateListSearch() {
  // EmployeePage owns the shared EmployeeSelector in the top toolbar.
  // employeeDirectoryUx historically injected a second proxy below the list;
  // keeping two imperative inputs caused stale closures and could break React
  // DOM reconciliation while filtering rows.
  const wrapper = document.querySelector('.staff-list-panel .vera-list-name-search')
  wrapper?.remove()
}

export function startEmployeeToolbarRecovery() {
  if (window.__veraEmployeeToolbarRecoveryStarted) return
  window.__veraEmployeeToolbarRecoveryStarted = true

  const reconcile = () => {
    restoreToolbar()
    removeDuplicateListSearch()
  }

  const observer = new MutationObserver(() => window.requestAnimationFrame(reconcile))
  observer.observe(document.body, { childList: true, subtree: true })

  // Keep protection active because employeeDirectoryUx still reconciles profile
  // controls periodically and can recreate legacy toolbar wrappers after a page
  // refresh if the DOM is replaced by React.
  window.setInterval(reconcile, 500)
  window.requestAnimationFrame(reconcile)
}
