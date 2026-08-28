import { Eye, KeyRound, LoaderCircle, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { staffSecurityApi } from '../lib/staffSecurityApi'

const TARGET_BYTES = 500 * 1024
const MAX_SOURCE_BYTES = 15 * 1024 * 1024

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (!bytes) return '0 KB'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function imageElement(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => resolve({ image, url })
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Không đọc được file ảnh.'))
    }
    image.src = url
  })
}

function canvasBlob(canvas, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) reject(new Error('Trình duyệt không nén được ảnh này.'))
      else resolve(blob)
    }, 'image/webp', quality)
  })
}

async function compressIdentityImage(file) {
  if (!String(file.type || '').startsWith('image/')) throw new Error('Chỉ chấp nhận file ảnh.')
  if (file.size > MAX_SOURCE_BYTES) throw new Error('Ảnh gốc vượt quá 15 MB.')

  const { image, url } = await imageElement(file)
  try {
    let maxEdge = 1600
    let quality = 0.8
    let lastBlob = null
    for (let attempt = 0; attempt < 7; attempt += 1) {
      const scale = Math.min(1, maxEdge / Math.max(image.naturalWidth, image.naturalHeight))
      const width = Math.max(1, Math.round(image.naturalWidth * scale))
      const height = Math.max(1, Math.round(image.naturalHeight * scale))
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const context = canvas.getContext('2d', { alpha: false })
      context.fillStyle = '#fff'
      context.fillRect(0, 0, width, height)
      context.drawImage(image, 0, 0, width, height)
      lastBlob = await canvasBlob(canvas, quality)
      if (lastBlob.size <= TARGET_BYTES) return lastBlob
      maxEdge = Math.max(900, Math.round(maxEdge * 0.84))
      quality = Math.max(0.54, quality - 0.05)
    }
    return lastBlob
  } finally {
    URL.revokeObjectURL(url)
  }
}

function IdentitySide({ username, side, title, metadata, busy, onChanged, setNotice }) {
  const inputRef = useRef(null)
  const [previewUrl, setPreviewUrl] = useState('')

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
  }, [previewUrl])

  const upload = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    onChanged(`upload-${side}`, async () => {
      const compressed = await compressIdentityImage(file)
      const result = await staffSecurityApi.uploadIdentity(username, side, compressed)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setPreviewUrl(URL.createObjectURL(compressed))
      setNotice({
        type: 'success',
        message: `${result.message} Ảnh gốc ${formatBytes(file.size)} → sau nén ${formatBytes(compressed.size)}.`,
      })
      return true
    })
  }

  const view = () => onChanged(`view-${side}`, async () => {
    const blob = await staffSecurityApi.identityBlob(username, side)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(URL.createObjectURL(blob))
    return false
  })

  const remove = () => onChanged(`delete-${side}`, async () => {
    if (!window.confirm(`Xóa ảnh ${title.toLowerCase()} CCCD của ${username}?`)) return false
    const result = await staffSecurityApi.deleteIdentity(username, side)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl('')
    setNotice({ type: 'success', message: result.message })
    return true
  })

  return <div className="employee-id-side">
    <div className="employee-id-side-head">
      <div><strong>{title}</strong><span>{metadata ? `Đã lưu · ${formatBytes(metadata.size_bytes)}` : 'Chưa có ảnh'}</span></div>
      {busy && <LoaderCircle className="spin" size={16} />}
    </div>
    <div className="employee-id-preview">
      {previewUrl ? <img src={previewUrl} alt={`${title} CCCD`} /> : <div className="employee-id-placeholder">CCCD</div>}
    </div>
    <div className="employee-id-actions">
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp,image/*" onChange={upload} hidden />
      <button type="button" className="secondary-button compact" onClick={() => inputRef.current?.click()} disabled={Boolean(busy)}><Upload size={14} /> {metadata ? 'Thay ảnh' : 'Tải ảnh'}</button>
      {metadata && <button type="button" className="secondary-button compact" onClick={view} disabled={Boolean(busy)}><Eye size={14} /> Xem</button>}
      {metadata && <button type="button" className="danger-button compact" onClick={remove} disabled={Boolean(busy)}><Trash2 size={14} /> Xóa</button>}
    </div>
  </div>
}

export default function EmployeeIdentityPanel({ username, allowPasswordReset = false, className = '' }) {
  const [meta, setMeta] = useState({ front: null, back: null })
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const load = async () => {
    if (!username) return
    try {
      const result = await staffSecurityApi.identityMetadata(username)
      setMeta({ front: result.front || null, back: result.back || null })
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    }
  }

  useEffect(() => { void load() }, [username]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (key, callback) => {
    setBusy(key)
    setNotice(null)
    try {
      const changed = await callback()
      if (changed) await load()
    } catch (error) {
      setNotice({ type: 'error', message: error.message || 'Thao tác không thành công.' })
    } finally {
      setBusy('')
    }
  }

  const resetPassword = () => run('password', async () => {
    if (password.length < 8) throw new Error('Mật khẩu mới phải có tối thiểu 8 ký tự.')
    if (password !== confirmPassword) throw new Error('Xác nhận mật khẩu chưa khớp.')
    if (!window.confirm(`Reset mật khẩu cho ${username}? Nhân viên sẽ phải đổi mật khẩu sau lần đăng nhập kế tiếp.`)) return false
    const result = await staffSecurityApi.resetPassword(username, password)
    setPassword('')
    setConfirmPassword('')
    setNotice({ type: 'success', message: result.message })
    return false
  })

  if (!username) return null

  return <div className={`employee-identity-panel ${className}`}>
    <style>{`
      .employee-identity-panel{display:grid;gap:14px;padding:16px;border:1px solid #dfe7e3;border-radius:16px;background:#f9fbfa}
      .employee-identity-title{display:flex;gap:10px;align-items:flex-start}.employee-identity-title h3{margin:0;font-size:15px}.employee-identity-title p{margin:3px 0 0;color:#6c7873;font-size:12px;line-height:1.45}
      .employee-identity-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.employee-id-side{border:1px solid #e2e8e5;border-radius:14px;background:#fff;padding:12px;min-width:0}
      .employee-id-side-head{display:flex;justify-content:space-between;gap:8px;align-items:center}.employee-id-side-head div{display:grid;gap:2px}.employee-id-side-head strong{font-size:13px}.employee-id-side-head span{font-size:11px;color:#74807b}
      .employee-id-preview{height:132px;margin:10px 0;border-radius:10px;overflow:hidden;background:#eef3f1;display:flex;align-items:center;justify-content:center}.employee-id-preview img{width:100%;height:100%;object-fit:contain;background:#111}.employee-id-placeholder{font-weight:900;color:#9aa6a1;letter-spacing:.12em}
      .employee-id-actions{display:flex;flex-wrap:wrap;gap:7px}.employee-id-actions button{min-height:34px}
      .employee-password-reset{display:grid;gap:10px;padding:13px;border:1px solid #eadfcf;border-radius:14px;background:#fffaf2}.employee-password-reset-head{display:flex;gap:8px;align-items:flex-start}.employee-password-reset-head h4{margin:0;font-size:13px}.employee-password-reset-head p{margin:3px 0 0;font-size:11px;color:#776d60;line-height:1.45}.employee-password-reset-grid{display:grid;grid-template-columns:1fr 1fr auto;gap:9px;align-items:end}.employee-password-reset-grid label{display:grid;gap:5px;font-size:12px;font-weight:700}.employee-password-reset-grid input{min-width:0}
      .employee-identity-notice{padding:9px 11px;border-radius:10px;font-size:12px}.employee-identity-notice.success{background:#edf8f2;color:#17603b}.employee-identity-notice.error{background:#fff1f0;color:#a62a20}
      @media(max-width:700px){.employee-identity-panel{padding:12px;gap:11px}.employee-identity-grid{grid-template-columns:1fr}.employee-id-preview{height:118px}.employee-password-reset-grid{grid-template-columns:1fr}.employee-password-reset-grid button{width:100%}}
    `}</style>
    <div className="employee-identity-title"><ShieldCheck size={19} /><div><h3>CĂN CƯỚC CÔNG DÂN</h3><p>Ảnh được tự động chuyển sang WebP và nén trước khi tải lên để giảm dung lượng lưu trữ. Chỉ chính nhân viên và Admin được xem.</p></div></div>
    <div className="employee-identity-grid">
      <IdentitySide username={username} side="front" title="Mặt trước" metadata={meta.front} busy={busy.startsWith('upload-front') || busy.startsWith('view-front') || busy.startsWith('delete-front')} onChanged={run} setNotice={setNotice} />
      <IdentitySide username={username} side="back" title="Mặt sau" metadata={meta.back} busy={busy.startsWith('upload-back') || busy.startsWith('view-back') || busy.startsWith('delete-back')} onChanged={run} setNotice={setNotice} />
    </div>
    {allowPasswordReset && <div className="employee-password-reset">
      <div className="employee-password-reset-head"><KeyRound size={17} /><div><h4>RESET MẬT KHẨU NHÂN VIÊN</h4><p>Mật khẩu hiện tại không hiển thị trên trình duyệt để bảo vệ tài khoản. Admin có thể đặt mật khẩu mới; nhân viên bắt buộc đổi lại sau lần đăng nhập tiếp theo.</p></div></div>
      <div className="employee-password-reset-grid">
        <label>Mật khẩu mới<input type="password" minLength={8} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Tối thiểu 8 ký tự" /></label>
        <label>Xác nhận mật khẩu<input type="password" minLength={8} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
        <button type="button" className="primary-button" onClick={resetPassword} disabled={busy === 'password'}>{busy === 'password' ? <LoaderCircle className="spin" size={16} /> : <KeyRound size={16} />} Reset mật khẩu</button>
      </div>
    </div>}
    {notice && <div className={`employee-identity-notice ${notice.type}`}>{notice.message}</div>}
  </div>
}
