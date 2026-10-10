import './LiveTourBookingNotes.css'

export default function LiveTourBookingNotes({ entries = [], className = '' }) {
  const notes = entries.map((entry, index) => ({ entry, index })).filter(({ entry }) => String(entry?.note ?? '').trim())
  if (!notes.length) return null
  return <div className={`tour-booking-notes ${className}`.trim()} aria-label="Ghi chú booking">
    <strong>Ghi chú booking</strong>
    {notes.map(({ entry, index }) => <p key={index}><strong>{[entry.employee_name || entry.name || `Dòng ${index + 1}`, entry.room].filter(Boolean).join(' · ')}: </strong><span>{entry.note}</span></p>)}
  </div>
}
