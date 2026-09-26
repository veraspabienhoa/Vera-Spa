// Prefetch JavaScript only. Import failures remain retryable; speculative loads
// never reload the browser, make business API calls or mount a hidden page.
export function pageModuleLoader(importer) {
  let pending
  return () => {
    if (!pending) pending = Promise.resolve().then(importer).catch(error => { pending = undefined; throw error })
    return pending
  }
}
