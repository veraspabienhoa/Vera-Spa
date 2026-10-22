export default function ArrivalDetail({ value }) {
  const text = String(value || '')
  if (/^Đơn Phép năm\s+AL-[A-Z0-9]+\s+đã duyệt(?:\s*\||\s*$)/i.test(text.trim())) return 'Phép năm'
  if (!/Đồng bộ (?:TimeSoft|FaceGate) trực tiếp|\|/.test(text)) return text || '—'
  const lines = text.split(/\s*[·|]\s*|\r?\n/)
    .map(line => line.replace(/Đồng bộ (?:TimeSoft|FaceGate) trực tiếp\.?/g, '').trim())
    .filter(Boolean)
    .map(line => line.replace(/(Check-in\s+)(\d{2})\/(\d{2})\/(\d{4})/g, '$1$2-$3-$4'))
  return lines.length ? lines.map((line, index) => <div key={index}>{line}</div>) : '—'
}
