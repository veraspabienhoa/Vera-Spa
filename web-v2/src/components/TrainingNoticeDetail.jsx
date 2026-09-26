import StableFeedback from './StableFeedback'
import { useState } from 'react'
import { ImageDown, Share2, X } from 'lucide-react'
import { formatVeraDate } from '../lib/veraDate'

const clock = value => String(value || '').slice(0, 5)
const trainingSchedule = detail => {
  if (!detail?.training_date || !detail?.start_time || !detail?.end_time) return null
  const start = clock(detail.start_time), end = clock(detail.end_time)
  const [sh, sm] = start.split(':').map(Number), [eh, em] = end.split(':').map(Number)
  const minutes = (eh * 60 + em) - (sh * 60 + sm)
  if (!Number.isFinite(minutes) || minutes <= 0) return null
  return { date: formatVeraDate(detail.training_date), start, end,
    duration: `${(minutes / 60).toLocaleString('vi-VN', { maximumFractionDigits: 2 })} giờ` }
}

function linesFor(notice) {
  const d = notice.detail || {}, schedule = trainingSchedule(d)
  return [
    ['Nhân viên', d.employee_name], ['Người thực hiện', d.evaluator_name],
    ...(schedule ? [['Ngày đào tạo', schedule.date], ['Thời gian', `${schedule.start} – ${schedule.end}`], ['Số giờ đào tạo', schedule.duration]] : []),
    ['Nội dung đào tạo', d.topic],
    ['Kỹ năng / Tinh thần', d.skill_grade && `${d.skill_grade}${d.learning_attitude ? ` · ${d.learning_attitude}` : ''}`],
    ['Đợt đánh giá', d.cycle_name],
    ['Tay nghề / Giao tiếp / Thái độ', d.craft_score && `${d.craft_score}/5 · ${d.communication_score}/5 · ${d.attitude_score}/5`],
    ['Nhận xét', d.comments || d.notes],
  ].filter(([, value]) => value != null && value !== '')
}

async function imageFile(notice) {
  const canvas = document.createElement('canvas')
  canvas.width = 960
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Trình duyệt không hỗ trợ tạo ảnh.')
  const rows = [notice.notification?.title || 'Thông báo đào tạo', notice.notification?.body || '',
    ...linesFor(notice).map(([label, value]) => `${label}: ${value}`)]
  ctx.font = '27px sans-serif'
  const wrapped = rows.flatMap((row, index) => {
    const words = String(row).split(/\s+/), output = []
    let line = ''
    for (const word of words) {
      const next = `${line} ${word}`.trim()
      if (line && ctx.measureText(next).width > 850) { output.push({ text: line, heading: index === 0 }); line = word }
      else line = next
    }
    output.push({ text: line, heading: index === 0 })
    return output
  })
  canvas.height = Math.max(440, 175 + wrapped.length * 47)
  ctx.fillStyle = '#f3f7f2'; ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = '#194232'; ctx.fillRect(0, 0, canvas.width, 16)
  ctx.fillStyle = '#9b762b'; ctx.font = 'bold 23px sans-serif'; ctx.fillText('ĐÀO TẠO & ĐÁNH GIÁ', 54, 73)
  wrapped.forEach((row, index) => {
    ctx.fillStyle = '#173d30'; ctx.font = row.heading ? 'bold 31px sans-serif' : '27px sans-serif'
    ctx.fillText(row.text, 54, 132 + index * 47)
  })
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'))
  if (!blob) throw new Error('Không tạo được ảnh thông báo.')
  return new File([blob], 'thong-bao-dao-tao.png', { type: 'image/png' })
}

export default function TrainingNoticeDetail({ notice, onClose }) {
  const [error, setError] = useState('')
  const share = async (downloadOnly = false) => {
    try {
      setError('')
      const file = await imageFile(notice)
      if (!downloadOnly && navigator.canShare?.({ files: [file] }) && navigator.share) {
        try { await navigator.share({ files: [file], title: 'Thông báo đào tạo' }); return }
        catch (cause) { if (cause?.name === 'AbortError') return }
      }
      const url = URL.createObjectURL(file), link = document.createElement('a')
      link.href = url; link.download = file.name; link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (cause) { setError(cause.message || 'Không tạo được ảnh thông báo.') }
  }
  return <div className="training-notification-modal" role="dialog" aria-modal="true" aria-label="Chi tiết đào tạo">
    <div className="training-notification-dialog">
      <header><div><small>ĐÀO TẠO & ĐÁNH GIÁ</small><h2>{notice.notification?.title}</h2></div>
        <button type="button" aria-label="Đóng" onClick={onClose}><X size={20}/></button></header>
      <p>{notice.notification?.body}</p>
      <dl>{linesFor(notice).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <StableFeedback>{error && <p role="alert">{error}</p>}</StableFeedback>
      <div className="training-notification-actions">
        <button type="button" className="primary-button" onClick={() => void share()}><Share2 size={16}/> Chia sẻ ảnh / Zalo</button>
        <button type="button" className="secondary-button" onClick={() => void share(true)}><ImageDown size={16}/> Tải ảnh PNG</button>
        <button type="button" className="primary-button" onClick={onClose}>Đóng</button>
      </div>
    </div>
  </div>
}
