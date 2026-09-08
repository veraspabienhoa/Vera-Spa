// Development only: real React component + synthetic backend DTO; no production API calls.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const root = fileURLToPath(new URL('../', import.meta.url))
const fixtures = execFileSync(process.env.LIVE_TOUR_TEST_PYTHON || 'python',
  [fileURLToPath(new URL('../../tests/live_tour_preview_fixture.py', import.meta.url))], { encoding: 'utf8' })
const html = `<!doctype html><html lang="vi"><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live Tour — dữ liệu mẫu</title><div id="root"></div><script type="module" src="/dev/live-tour-preview.jsx"></script></html>`
const server = await createServer({ root, server: { host: '127.0.0.1', port: 5174, strictPort: true }, plugins: [{
  name: 'live-tour-read-only-preview',
  configureServer(server) {
    server.middlewares.use(async (req, res, next) => {
      const path = req.url.split('?')[0]
      if (path === '/preview-fixtures.json') {
        res.setHeader('Content-Type', 'application/json; charset=utf-8')
        return res.end(fixtures)
      }
      if (path === '/preview-mobile') {
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        return res.end('<!doctype html><html lang="vi"><title>Live Tour 390px</title><iframe title="Live Tour mobile" src="/preview" style="width:390px;height:844px;border:1px solid #ccc"></iframe></html>')
      }
      if (path === '/preview') {
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        return res.end(await server.transformIndexHtml(req.url, html))
      }
      // Fail closed if the component gains an unmocked API dependency.
      if (path.startsWith('/api/') || path.startsWith('/v2/')) {
        res.statusCode = 503
        return res.end('Synthetic preview: API access disabled')
      }
      next()
    })
  },
}] })
await server.listen()
if (process.argv.includes('--check')) {
  try {
    for (const path of ['/preview', '/preview-mobile', '/dev/live-tour-preview.jsx', '/src/pages/LiveTourPage.jsx', '/preview-fixtures.json']) {
      const response = await fetch(`http://127.0.0.1:5174${path}`)
      if (!response.ok) throw new Error(`${path}: ${response.status}`)
      await response.text()
    }
    const response = await fetch('http://127.0.0.1:5174/v2/live-tour')
    if (response.status !== 503) throw new Error('Preview must block live API access')
    console.log('Synthetic preview routes and API guard passed.')
  } finally { await server.close() }
} else server.printUrls()
