import { useState } from 'react'
import { veraApi } from '../lib/api'

export default function MissingCheckinAbsenceRules({ policy, canEdit }) {
  const [current, setCurrent] = useState(policy)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  async function save(key, enabled) {
    if (!canEdit || busy) return
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await veraApi.saveMissingCheckinAbsencePolicy({
        enabled: current.enabled, ca1_enabled: current.ca1_enabled, ca2_enabled: current.ca2_enabled,
        [key]: enabled, expected_revision: current.revision,
      })
      setCurrent(result); setMessage(result.message)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <section className="panel leave-queue-policy-panel" aria-labelledby="absence-policy-title">
    <h2 id="absence-policy-title">TỰ ĐỘNG NGHỈ KHÔNG PHÉP · THIẾU CHECK IN</h2>
    <p>Chỉ áp dụng cho bộ phận Leader và Nhân viên (KTV). Locker, Lễ tân, Tạp vụ và các bộ phận khác không bị tự động phạt theo quy tắc này.</p>
    <p>Chờ thêm 2 tiếng sau mốc phải check in: sau 17:00 với Ca 1 (mốc 15:00), sau 19:00 với Ca 2 (mốc 17:00), giờ Việt Nam, nhân viên có lịch làm nhưng chưa có lượt quét hợp lệ được ghi nghỉ không phép tại lượt đồng bộ FaceGate đầy đủ, còn mới tiếp theo.</p>
    <p>Thứ Hai–Thứ Sáu: Nghỉ KHÔNG phép. Thứ Bảy–Chủ nhật: Nghỉ CUỐI TUẦN KHÔNG phép. Mức phạt và cộng dồn lấy theo Nội quy KTV tại lúc ghi nhận.</p>
    <p>Khi Admin tạm dừng phạt tự động, quy tắc cũng tạm dừng. Không xử lý ngày cũ, tài khoản tạm miễn, chưa ánh xạ Face ID, dữ liệu thiếu hoặc mất kết nối. Trước khi ghi phạt, hệ thống kiểm tra lại dữ liệu và thay dòng không phép cũ trong cùng ngày bằng khoản mới, giữ bản lưu đối soát. Dòng có phép được giữ nguyên; đã đăng ký đi trễ có phép chỉ ghi nửa ngày không phép bằng lý do “Về sớm KHÔNG phép” (ngày thường) hoặc “Về sớm CUỐI TUẦN KHÔNG phép” (Thứ Bảy, Chủ nhật), theo mức Nội quy. Nếu chưa có mức nửa ngày phù hợp, dừng để quản lý kiểm tra. Trường hợp có lượt quét đến sau khi đã ghi nghỉ cần quản lý kiểm tra và điều chỉnh.</p>
    <fieldset disabled={!canEdit || busy}>
      <legend>Áp dụng tự động</legend>
      {[['enabled', 'Bật quy tắc tự động nghỉ không phép'], ['ca1_enabled', 'Ca 1 · sau 17:00'], ['ca2_enabled', 'Ca 2 · sau 19:00']].map(([key, label]) => <label key={key}>
        <input type="checkbox" checked={current[key]} onChange={event => save(key, event.target.checked)} /><span>{label}</span>
      </label>)}
    </fieldset>
    <p>Thông báo cho đúng nhân viên, lễ tân, quản lý và Admin qua hệ thống, popup và thông báo đẩy. Điều chỉnh kênh/người nhận trong Cài đặt thông báo → Tự động nghỉ không phép · Ca 1 / Ca 2. Tắt thông báo không tắt quy tắc ghi nghỉ.</p>
    {!canEdit && <p>Chỉ Admin được thay đổi nội quy này.</p>}
    {busy && <p role="status">Đang lưu…</p>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
  </section>
}
