import UiCustomText from './UiCustomText'
import { useState } from 'react'

export default function LiveTourPartialLeaveSettings({ value, busy, onSave }) {
  const [form, setForm] = useState(() => ({ partial_leave_times: { late1:'15:00', late2:'17:00', early1:'15:00', early2:'17:00', ...value?.partial_leave_times } }))
  return <details className="panel tour-partial-leave-settings">
    <summary>Giờ đi trễ / về sớm theo lịch nghỉ trong ngày</summary>
    <form onSubmit={event => { event.preventDefault(); onSave({ ...value, partial_leave_times: form.partial_leave_times }) }}>
    <fieldset disabled={busy}><legend>Giờ đi trễ / về sớm theo lịch nghỉ trong ngày</legend><p>Áp dụng cho Nhân viên và Leader theo ca làm của ngày đó. Định dạng 24 giờ, giờ Việt Nam.</p>{[['late1', 'Đi trễ · Ca 1', '15:00'], ['late2', 'Đi trễ · Ca 2', '17:00'], ['early1', 'Về sớm · Ca 1', '15:00'], ['early2', 'Về sớm · Ca 2', '17:00']].map(([key, label, fallback]) => <label key={key}>{label}<input type="time" required value={form.partial_leave_times?.[key] ?? fallback} onChange={event => setForm(current => ({ ...current, partial_leave_times: { late1: '15:00', late2: '17:00', early1: '15:00', early2: '17:00', ...current.partial_leave_times, [key]: event.target.value } }))}/></label>)}<p>Đi trễ: loại chung, có phép, không phép, cuối tuần có/không phép, phát sinh, Leader đi trễ sớm theo chính sách.</p><p>Về sớm: loại chung, có phép, không phép, cuối tuần có/không phép, phát sinh, bệnh có giấy khám hoặc được quản lý duyệt, Leader về sớm theo chính sách.</p></fieldset>
      <button data-ui-key="u-79cb4bba967f" data-ui-label-default="Lưu giờ đi trễ / về sớm" type="submit" className="primary-button" disabled={busy}><UiCustomText uiKey="u-79cb4bba967f">Lưu giờ đi trễ / về sớm</UiCustomText></button>
    </form>
  </details>
}
