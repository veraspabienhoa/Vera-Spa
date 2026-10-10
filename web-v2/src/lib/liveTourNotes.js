// Booking notes remain attached to their source entries. The invoice has its
// own editable note; an explicitly saved empty string must not be rehydrated.
export function bookingNotesDefault(entries = []) {
  return [...new Set(entries.map(entry => String(entry?.note ?? '')).filter(note => note.trim()))].join('\n')
}

export function checkoutNote(source, entries = source?.entries || []) {
  return source && Object.prototype.hasOwnProperty.call(source, 'note')
    ? String(source.note ?? '') : bookingNotesDefault(entries)
}
