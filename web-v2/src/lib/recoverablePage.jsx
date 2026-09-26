import { lazy } from 'react'
import { pageModuleLoader } from './pageModuleLoader'

// A rejected React.lazy caches its error. Explicit retry needs a new lazy
// instance as well as the loader's rejected-promise eviction. Never reload the
// whole app automatically: that loses the selected route and unsaved work.
export function recoverablePage(importer) {
  const preload = pageModuleLoader(importer)
  let Page = lazy(preload)
  const RecoverablePage = (props) => <Page {...props} />
  RecoverablePage.preload = preload
  RecoverablePage.reset = () => { Page = lazy(preload) }
  return RecoverablePage
}
