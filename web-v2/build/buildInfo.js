import { execFileSync } from 'node:child_process'
import { env } from 'node:process'
import { fileURLToPath } from 'node:url'

function sourceRevision() {
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: fileURLToPath(new URL('..', import.meta.url)),
      encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    return env.VERA_BUILD_REVISION || 'development'
  }
}

// Public provenance only: never include build environment or runtime settings.
export default function buildInfo(revision = sourceRevision()) {
  return {
    name: 'vera-build-info',
    apply: 'build',
    generateBundle(_options, bundle) {
      const entries = Object.values(bundle).filter(item => item.type === 'chunk' && item.isEntry)
      if (entries.length !== 1) throw new Error('Expected one VERA browser entry')
      this.emitFile({
        type: 'asset', fileName: 'build-info.json',
        source: JSON.stringify({ revision, entry_script: `/${entries[0].fileName}` }) + '\n',
      })
    },
  }
}
