export function isPageLoadFailure(error) {
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Loading (?:chunk|CSS chunk)|Unable to preload CSS|Failed to load module script/i.test(String(error?.message || error || ''))
}

export async function hasNewPageBuild(windowObject = window, fetcher = fetch) {
  const entry = [...windowObject.document.querySelectorAll('script[type="module"][src]')]
    .map(script => new URL(script.src, windowObject.location.href).pathname).find(path => path.startsWith('/assets/'))
  if (!entry) return false
  try {
    const response = await fetcher(`/build-info.json?check=${Date.now()}`, { cache: 'no-store', signal: AbortSignal.timeout(5000) })
    if (!response.ok) return false
    const info = await response.json()
    return typeof info.entry_script === 'string' && /^\/assets\/[\w.-]+\.js$/.test(info.entry_script) && info.entry_script !== entry
  } catch { return false }
}
