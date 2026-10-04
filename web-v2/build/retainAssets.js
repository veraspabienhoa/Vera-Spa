import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { env } from 'node:process'

const assetName = /^[a-zA-Z0-9_.-]+\.(?:js|css|woff2?|ttf|png|jpe?g|svg|webp|gif)$/
const retention = 7 * 24 * 60 * 60 * 1000

// Keep hashed dependencies for tabs opened before a release. Never copy old
// HTML, build-info, service workers, source maps, or application data.
export default function retainAssets({ previousDir = env.VERA_PREVIOUS_WEB_DIST || '/opt/vera-spa/current/web-v2/dist', now = Date.now() } = {}) {
  return {
    name: 'vera-retain-assets', apply: 'build',
    generateBundle(options, bundle) {
      const dates = {}
      const currentAssets = Object.keys(bundle)
      let history = {}
      const previous = resolve(previousDir)
      if (options.dir && previous === resolve(options.dir)) throw new Error('Previous release must be separate from build output')
      if (existsSync(join(previous, 'assets'))) {
        try { history = JSON.parse(readFileSync(join(previous, 'asset-history.json'), 'utf8')) } catch { /* first deployment with retention */ }
        for (const name of readdirSync(join(previous, 'assets'))) {
          if (!assetName.test(name)) continue
          const fileName = `assets/${name}`
          const firstSeen = Object.hasOwn(history, fileName) ? history[fileName] : now
          if (!Number.isFinite(firstSeen) || firstSeen > now || now - firstSeen > retention || bundle[fileName]) continue
          this.emitFile({ type: 'asset', fileName, source: readFileSync(join(previous, fileName)) })
          dates[fileName] = firstSeen
        }
      }
      for (const name of currentAssets) if (name.startsWith('assets/') && assetName.test(name.slice(7))) dates[name] = now
      this.emitFile({ type: 'asset', fileName: 'asset-history.json', source: JSON.stringify(dates) })
    },
  }
}
