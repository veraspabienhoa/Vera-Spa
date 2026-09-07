function forceReactControlValue(control, value) {
  if (!(control instanceof HTMLInputElement) && !(control instanceof HTMLSelectElement)) return
  const proto = control instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
  if (setter) setter.call(control, value)
  else control.value = value

  // React tracks controlled form values internally. Make the tracker differ
  // from the DOM value so the synthetic event is always observed, including
  // after an imperative enhancer previously changed the element outside React.
  const tracker = control._valueTracker
  if (tracker?.setValue) tracker.setValue(`__vera_stale_${Date.now()}__`)
  control.dispatchEvent(new Event('input', { bubbles: true }))
  control.dispatchEvent(new Event('change', { bubbles: true }))
}

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

  toolbar.querySelectorAll('select').forEach((select) => {
    removeToolbarProxy(select)
    if (select.dataset.veraToolbarStateSynced === '1') return
    select.dataset.veraToolbarStateSynced = '1'
    forceReactControlValue(select, select.value)
  })

  const search = toolbar.querySelector('.staff-search input')
  if (search instanceof HTMLInputElement && search.dataset.veraToolbarStateSynced !== '1') {
    search.dataset.veraToolbarStateSynced = '1'
    forceReactControlValue(search, search.value)
  }
}

function hideDuplicateListSearch() {
  // EmployeePage already owns the canonical search box in the top toolbar.
  // employeeDirectoryUx historically injected a second proxy below the list;
  // keeping two imperative inputs caused stale closures after refresh. Leave
  // the node present so the old enhancer does not recreate it, but never expose
  // or use it as a second source of filter state.
  const wrapper = document.querySelector('.staff-list-panel .vera-list-name-search')
  if (!(wrapper instanceof HTMLElement)) return
  wrapper.hidden = true
  wrapper.setAttribute('aria-hidden', 'true')
  wrapper.style.setProperty('display', 'none', 'important')
}

function resyncToolbarAfterNativeChange(event) {
  const target = event.target
  if (!(target instanceof HTMLSelectElement) && !(target instanceof HTMLInputElement)) return
  if (!target.closest('.staff-control-panel .staff-toolbar')) return

  // Native user interaction normally reaches React directly. Queue one guarded
  // replay only when the DOM control survives the React turn; this repairs the
  // rare Safari/imperative-enhancer case where the visible value changed but
  // React state did not.
  const value = target.value
  window.setTimeout(() => {
    if (!target.isConnected || target.value !== value) return
    if (target.dataset.veraToolbarReplay === value) return
    target.dataset.veraToolbarReplay = value
    forceReactControlValue(target, value)
    window.setTimeout(() => {
      if (target.dataset.veraToolbarReplay === value) delete target.dataset.veraToolbarReplay
    }, 0)
  }, 0)
}

export function startEmployeeToolbarRecovery() {
  if (window.__veraEmployeeToolbarRecoveryStarted) return
  window.__veraEmployeeToolbarRecoveryStarted = true

  const reconcile = () => {
    restoreToolbar()
    hideDuplicateListSearch()
  }

  const observer = new MutationObserver(() => window.requestAnimationFrame(reconcile))
  observer.observe(document.body, { childList: true, subtree: true })

  document.addEventListener('change', resyncToolbarAfterNativeChange, true)
  document.addEventListener('search', resyncToolbarAfterNativeChange, true)

  // Keep protection active because employeeDirectoryUx still reconciles profile
  // controls periodically and can recreate legacy toolbar wrappers after a page
  // refresh if the DOM is replaced by React.
  window.setInterval(reconcile, 500)
  window.requestAnimationFrame(reconcile)
}
