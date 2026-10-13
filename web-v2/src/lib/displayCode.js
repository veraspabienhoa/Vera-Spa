// Presentation only: never use abbreviated codes as record keys or API values.
export function displayCode(value) {
  const code = String(value ?? '').trim()
  if (!code) return '—'
  return code.length > 16 ? `${code.slice(0, 8)}…${code.slice(-4)}` : code
}
