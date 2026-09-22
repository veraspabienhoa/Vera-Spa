import { useState } from 'react'

export default function LiveTourAppointmentInput({ value = '', employeeName, revision, busy, disabled = false, onSave, quick = false }) {
  const [draft, setDraft] = useState(null)
  const currentValue = draft?.value ?? value
  const dirty = draft !== null && currentValue.trim() !== value
  const mobileScale = quick ? 0.75 : Math.max(0.4, Math.min(0.75, 9 / Math.max(9, Array.from(currentValue).length || 1)))
  const mobileFitStyle = quick ? undefined : {
    '--appointment-mobile-scale': mobileScale,
    '--appointment-mobile-width': `${100 / mobileScale}%`,
    '--appointment-mobile-height': `${26 / mobileScale}px`,
  }

  const save = async (event) => {
    event.preventDefault()
    if (!dirty || busy || disabled) return
    const result = await onSave(currentValue.trim(), draft.revision ?? revision)
    // Keep unsaved text after errors. Retrying explicitly uses the refreshed
    // revision, so background polling cannot silently overwrite another edit.
    setDraft(result ? null : { value: currentValue, revision: null })
  }

  return <form className={`live-tour-appointment-editor${quick ? ' quick' : ''}`} onSubmit={save}>
    <span className="live-tour-appointment-text"><input type="text" maxLength={200} value={currentValue} disabled={disabled || busy} style={mobileFitStyle}
      aria-label={employeeName ? `Lịch hẹn của ${employeeName}` : 'Lịch hẹn nhân viên'}
      title={employeeName ? `Lịch hẹn của ${employeeName} · Enter để lưu, Esc để hủy` : 'Tìm hoặc chọn đúng một nhân viên để lưu lịch hẹn'}
      onChange={(event) => setDraft({ value: event.target.value, revision: draft?.revision ?? revision })}
      onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); setDraft(null) } }}/></span>
    {(quick || dirty) && <button data-ui-key="u-4c09b839d5bc" type="submit" className="secondary-button" disabled={!dirty || disabled || busy}>{quick ? 'Lưu lịch hẹn' : 'Lưu'}</button>}
    {quick && employeeName && <span className="live-tour-appointment-target">{employeeName}</span>}
  </form>
}
