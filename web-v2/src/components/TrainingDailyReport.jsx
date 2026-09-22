import UiCustomText from './UiCustomText'
import { trainingDailySummary } from '../lib/trainingSummary'
import { formatVeraDate } from '../lib/veraDate'
const hours = minutes => (minutes / 60).toLocaleString('vi-VN', { maximumFractionDigits:2 })
export default function TrainingDailyReport({ report }) {
  const days = trainingDailySummary(report.progress)
  return <section data-ui-key="u-d4a02febab9a" className="training-card training-daily-report"><h2>Nhật ký đào tạo · {report.employee_username}</h2>
    <p>{days.length} ngày · {days.reduce((n,d) => n+d.sessions.length,0)} buổi · <strong>{hours(days.reduce((n,d) => n+d.minutes,0))} giờ</strong></p>
    <table data-ui-key="u-73702c25b78b"><thead><tr><th data-ui-key="u-bec4fc20da69"><UiCustomText uiKey="u-bec4fc20da69">Ngày</UiCustomText></th><th data-ui-key="u-3a57bc2740de"><UiCustomText uiKey="u-3a57bc2740de">Giờ đào tạo</UiCustomText></th><th data-ui-key="u-4666c749bee9"><UiCustomText uiKey="u-4666c749bee9">Nội dung và đánh giá từng buổi</UiCustomText></th></tr></thead><tbody>{days.map(day => <tr key={day.date}><td>{formatVeraDate(day.date)}</td><td><strong>{hours(day.minutes)} giờ</strong></td><td>{day.sessions.map(s => <article key={s.id}><strong>{String(s.start_time).slice(0,5)}–{String(s.end_time).slice(0,5)} · {hours(s.minutes)} giờ</strong><p>{s.topic || 'Đào tạo hằng ngày'} · Người đào tạo: {s.evaluator_name || s.trainer_username}</p><p>Tay nghề: {s.skill_grade} · Tinh thần: {s.learning_attitude}</p><p>Điểm mạnh: {s.strengths || '—'}</p><p>Cần cải thiện: {s.improvements || '—'}</p><p>Nhận xét: {s.notes || '—'}</p></article>)}</td></tr>)}</tbody></table>
    {!days.length && <p>Chưa có nhật ký đào tạo trong khoảng đã chọn.</p>}
  </section>
}
