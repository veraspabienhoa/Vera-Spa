import { Camera, Crop, Download, Eye, KeyRound, LoaderCircle, RotateCcw, RotateCw, ShieldCheck, SlidersHorizontal, Trash2, Upload, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { staffSecurityApi } from '../lib/staffSecurityApi'

const TARGET_BYTES = 450 * 1024
const MAX_SOURCE_BYTES = 20 * 1024 * 1024
const MIN_CROP = 20
const CCCD_ASPECT_RATIO = 85.6 / 53.98

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

function drawProcessedImage(canvas, image, crop, rotation, maxEdge) {
  if (!canvas || !image) return
  const sourceWidth = image.naturalWidth || image.width
  const sourceHeight = image.naturalHeight || image.height
  const sx = Math.round(sourceWidth * crop.x / 100)
  const sy = Math.round(sourceHeight * crop.y / 100)
  const sw = Math.max(1, Math.round(sourceWidth * crop.w / 100))
  const sh = Math.max(1, Math.round(sourceHeight * crop.h / 100))
  const quarterTurn = Math.abs(rotation % 180) === 90
  const rotatedWidth = quarterTurn ? sh : sw
  const rotatedHeight = quarterTurn ? sw : sh
  const scale = Math.min(1, maxEdge / Math.max(rotatedWidth, rotatedHeight))
  const outputWidth = Math.max(1, Math.round(rotatedWidth * scale))
  const outputHeight = Math.max(1, Math.round(rotatedHeight * scale))
  const drawWidth = Math.max(1, Math.round(sw * scale))
  const drawHeight = Math.max(1, Math.round(sh * scale))

  canvas.width = outputWidth
  canvas.height = outputHeight
  const context = canvas.getContext('2d', { alpha: false })
  context.save()
  context.fillStyle = '#fff'
  context.fillRect(0, 0, outputWidth, outputHeight)
  context.translate(outputWidth / 2, outputHeight / 2)
  context.rotate(rotation * Math.PI / 180)
  context.drawImage(image, sx, sy, sw, sh, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight)
  context.restore()
}

async function createCompressedBlob(image, crop, rotation, preferredEdge, preferredQuality) {
  let maxEdge = preferredEdge
  let quality = preferredQuality
  let lastBlob = null
  for (let attempt = 0; attempt < 14; attempt += 1) {
    const canvas = document.createElement('canvas')
    drawProcessedImage(canvas, image, crop, rotation, maxEdge)
    lastBlob = await canvasBlob(canvas, quality)
    if (lastBlob.size <= TARGET_BYTES) return lastBlob
    if (quality > 0.44) quality = Math.max(0.42, quality - 0.07)
    else maxEdge = Math.max(650, Math.round(maxEdge * 0.82))
  }
  if (lastBlob?.size <= 650 * 1024) return lastBlob
  throw new Error(`Ảnh sau xử lý vẫn còn ${formatBytes(lastBlob?.size)}. Hãy Crop bớt vùng thừa hoặc giảm Độ phân giải.`)
}

function IdentityCamera({ title, onCancel, onCapture }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)

  useEffect(() => {
    let active = true
    const open = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Trình duyệt này không hỗ trợ camera trực tiếp. Hãy dùng nút Tải ảnh.')
        setBusy(false)
        return
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1920 },
            height: { ideal: 1210 },
            aspectRatio: { ideal: CCCD_ASPECT_RATIO },
          },
        })
        if (!active) { stream.getTracks().forEach((track) => track.stop()); return }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play().catch(() => {})
        }
      } catch (cameraError) {
        setError(cameraError?.name === 'NotAllowedError' ? 'Chưa được cấp quyền Camera. Vui lòng cho phép Camera rồi thử lại.' : `Không mở được Camera (${cameraError?.message || 'lỗi camera'}).`)
      } finally {
        if (active) setBusy(false)
      }
    }
    void open()
    return () => {
      active = false
      streamRef.current?.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
  }, [])

  const capture = () => {
    const video = videoRef.current
    if (!video?.videoWidth || !video?.videoHeight) {
      setError('Camera chưa sẵn sàng để chụp.')
      return
    }

    const sourceRatio = video.videoWidth / video.videoHeight
    let sx = 0
    let sy = 0
    let sw = video.videoWidth
    let sh = video.videoHeight
    if (sourceRatio > CCCD_ASPECT_RATIO) {
      sw = Math.round(video.videoHeight * CCCD_ASPECT_RATIO)
      sx = Math.max(0, Math.round((video.videoWidth - sw) / 2))
    } else if (sourceRatio < CCCD_ASPECT_RATIO) {
      sh = Math.round(video.videoWidth / CCCD_ASPECT_RATIO)
      sy = Math.max(0, Math.round((video.videoHeight - sh) / 2))
    }

    const outputWidth = Math.min(1800, sw)
    const outputHeight = Math.max(1, Math.round(outputWidth / CCCD_ASPECT_RATIO))
    const canvas = document.createElement('canvas')
    canvas.width = outputWidth
    canvas.height = outputHeight
    const context = canvas.getContext('2d', { alpha: false })
    context.drawImage(video, sx, sy, sw, sh, 0, 0, outputWidth, outputHeight)
    canvas.toBlob((blob) => {
      if (!blob) { setError('Không tạo được ảnh từ Camera.'); return }
      const file = new File([blob], `CCCD_${title.replace(/\s+/g, '_')}_${Date.now()}.jpg`, { type: 'image/jpeg' })
      onCapture(file)
    }, 'image/jpeg', 0.94)
  }

  return <div className="identity-editor-backdrop" role="dialog" aria-modal="true" aria-label={`Camera ${title} CCCD`}>
    <div className="identity-camera-card">
      <div className="identity-editor-head"><div><span className="eyebrow"><Camera size={14}/> Camera CCCD</span><h3>CHỤP {title.toUpperCase()}</h3><p>Khung Camera là hình chữ nhật ngang theo tỷ lệ thẻ CCCD. Canh đủ bốn góc CCCD trong khung rồi chụp.</p></div><button type="button" className="secondary-button compact" onClick={onCancel}><X size={16}/> Đóng</button></div>
      <div className="identity-camera-landscape">
        <video ref={videoRef} playsInline muted autoPlay />
        <div className="identity-camera-card-guide"><span>CANH 4 GÓC CCCD TRONG KHUNG NÀY</span></div>
        {busy && <div className="identity-camera-loading"><LoaderCircle className="spin" size={24}/> Đang mở Camera…</div>}
      </div>
      <div className="identity-camera-help">Khung chụp nằm ngang, tỷ lệ gần đúng kích thước CCCD 85,6 × 53,98 mm. Ảnh chụp cũng được cắt theo đúng tỷ lệ ngang này trước khi chuyển sang bước Crop/Rotate/Nén.</div>
      {error && <div className="employee-identity-notice error">{error}</div>}
      <div className="identity-editor-footer"><button type="button" className="secondary-button" onClick={onCancel}>Hủy</button><button type="button" className="primary-button" onClick={capture} disabled={busy || Boolean(error)}><Camera size={16}/> Chụp ảnh</button></div>
    </div>
  </div>
}

function IdentityImageEditor({ file, title, onCancel, onConfirm }) {
  const [source, setSource] = useState(null)
  const [sourceUrl, setSourceUrl] = useState('')
  const [crop, setCrop] = useState({ x: 0, y: 0, w: 100, h: 100 })
  const [rotation, setRotation] = useState(0)
  const [quality, setQuality] = useState(0.78)
  const [maxEdge, setMaxEdge] = useState(1600)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const canvasRef = useRef(null)

  useEffect(() => {
    let active = true
    imageElement(file).then(({ image, url }) => {
      if (!active) { URL.revokeObjectURL(url); return }
      setSource(image); setSourceUrl(url)
    }).catch((loadError) => setError(loadError.message))
    return () => { active = false }
  }, [file])

  useEffect(() => () => { if (sourceUrl) URL.revokeObjectURL(sourceUrl) }, [sourceUrl])

  useEffect(() => {
    if (source && canvasRef.current) drawProcessedImage(canvasRef.current, source, crop, rotation, 720)
  }, [crop, rotation, source])

  const setCropValue = (key, raw) => {
    const value = Number(raw)
    setCrop((current) => {
      const next = { ...current, [key]: value }
      if (key === 'x') next.w = Math.min(next.w, 100 - value)
      if (key === 'y') next.h = Math.min(next.h, 100 - value)
      if (key === 'w') next.w = Math.min(value, 100 - next.x)
      if (key === 'h') next.h = Math.min(value, 100 - next.y)
      next.w = Math.max(MIN_CROP, next.w)
      next.h = Math.max(MIN_CROP, next.h)
      next.x = Math.min(next.x, 100 - next.w)
      next.y = Math.min(next.y, 100 - next.h)
      return next
    })
  }

  const process = async () => {
    if (!source || busy) return
    setBusy(true); setError('')
    try {
      const blob = await createCompressedBlob(source, crop, rotation, maxEdge, quality)
      await onConfirm(blob)
    } catch (processError) {
      setError(processError.message || 'Không xử lý được ảnh.')
    } finally {
      setBusy(false)
    }
  }

  return <div className="identity-editor-backdrop" role="dialog" aria-modal="true" aria-label={`Chỉnh ảnh ${title} CCCD`}>
    <div className="identity-editor-card">
      <div className="identity-editor-head"><div><span className="eyebrow"><Crop size={14}/> CCCD</span><h3>CHỈNH ẢNH {title.toUpperCase()}</h3><p>Crop vùng cần giữ, xoay đúng chiều và nén ảnh trước khi tải lên.</p></div><button type="button" className="secondary-button compact" onClick={onCancel} disabled={busy}><X size={16}/> Đóng</button></div>
      <div className="identity-editor-layout">
        <div className="identity-editor-preview"><canvas ref={canvasRef}/><small>Ảnh xem trước sau Crop + Rotate</small></div>
        <div className="identity-editor-controls">
          <div className="identity-editor-section"><strong><RotateCw size={15}/> Xoay ảnh</strong><div className="identity-editor-buttons"><button type="button" className="secondary-button compact" onClick={() => setRotation((value) => (value + 270) % 360)}><RotateCcw size={14}/> -90°</button><button type="button" className="secondary-button compact" onClick={() => setRotation((value) => (value + 90) % 360)}><RotateCw size={14}/> +90°</button><span>{rotation}°</span></div></div>
          <div className="identity-editor-section"><strong><Crop size={15}/> Crop</strong>
            <label>Trái: {crop.x}%<input type="range" min="0" max={Math.max(0, 100 - crop.w)} value={crop.x} onChange={(e) => setCropValue('x', e.target.value)}/></label>
            <label>Trên: {crop.y}%<input type="range" min="0" max={Math.max(0, 100 - crop.h)} value={crop.y} onChange={(e) => setCropValue('y', e.target.value)}/></label>
            <label>Rộng: {crop.w}%<input type="range" min={MIN_CROP} max={100 - crop.x} value={crop.w} onChange={(e) => setCropValue('w', e.target.value)}/></label>
            <label>Cao: {crop.h}%<input type="range" min={MIN_CROP} max={100 - crop.y} value={crop.h} onChange={(e) => setCropValue('h', e.target.value)}/></label>
            <button type="button" className="secondary-button compact" onClick={() => setCrop({ x: 0, y: 0, w: 100, h: 100 })}>Khôi phục toàn ảnh</button>
          </div>
          <div className="identity-editor-section"><strong><SlidersHorizontal size={15}/> Nén trước khi upload</strong>
            <label>Độ phân giải tối đa<select value={maxEdge} onChange={(e) => setMaxEdge(Number(e.target.value))}><option value="1800">1800 px</option><option value="1600">1600 px</option><option value="1400">1400 px</option><option value="1200">1200 px</option><option value="1000">1000 px</option><option value="800">800 px</option></select></label>
            <label>Chất lượng: {Math.round(quality * 100)}%<input type="range" min="45" max="90" value={Math.round(quality * 100)} onChange={(e) => setQuality(Number(e.target.value) / 100)}/></label>
            <div className="identity-editor-size">Ảnh gốc: <b>{formatBytes(file.size)}</b> · Mục tiêu upload: <b>≤ {formatBytes(TARGET_BYTES)}</b></div>
          </div>
        </div>
      </div>
      {error && <div className="employee-identity-notice error">{error}</div>}
      <div className="identity-editor-footer"><button type="button" className="secondary-button" onClick={onCancel} disabled={busy}>Hủy</button><button type="button" className="primary-button" onClick={process} disabled={busy || !source}>{busy ? <LoaderCircle className="spin" size={16}/> : <Upload size={16}/>} {busy ? 'Đang Crop · Rotate · Nén…' : 'Xử lý & tải lên'}</button></div>
    </div>
  </div>
}

function IdentitySide({ username, side, title, metadata, busy, onChanged, setNotice, allowDownload }) {
  const inputRef = useRef(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [pendingFile, setPendingFile] = useState(null)
  const [cameraOpen, setCameraOpen] = useState(false)

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  const acceptFile = (file) => {
    if (!file) return
    if (!String(file.type || '').startsWith('image/')) { setNotice({ type: 'error', message: 'Chỉ chấp nhận file ảnh.' }); return }
    if (file.size > MAX_SOURCE_BYTES) { setNotice({ type: 'error', message: 'Ảnh gốc vượt quá 20 MB.' }); return }
    setPendingFile(file)
  }

  const chooseFile = (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    acceptFile(file)
  }

  const uploadProcessed = async (blob) => {
    const original = pendingFile
    const uploaded = await new Promise((resolve, reject) => {
      onChanged(`upload-${side}`, async () => {
        try {
          const result = await staffSecurityApi.uploadIdentity(username, side, blob)
          if (previewUrl) URL.revokeObjectURL(previewUrl)
          setPreviewUrl(URL.createObjectURL(blob))
          setNotice({ type: 'success', message: `${result.message} Ảnh gốc ${formatBytes(original?.size)} → sau Crop/Rotate/Nén ${formatBytes(blob.size)}.` })
          setPendingFile(null)
          window.dispatchEvent(new CustomEvent('vera-profile-updated'))
          resolve(true)
          return true
        } catch (error) {
          reject(error)
          throw error
        }
      })
    })
    return uploaded
  }

  const view = () => onChanged(`view-${side}`, async () => {
    const blob = await staffSecurityApi.identityBlob(username, side)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(URL.createObjectURL(blob))
    return false
  })

  const download = () => onChanged(`download-${side}`, async () => {
    const blob = await staffSecurityApi.identityBlob(username, side)
    const extension = blob.type === 'image/png' ? 'png' : blob.type === 'image/jpeg' ? 'jpg' : 'webp'
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${username}_CCCD_${side === 'front' ? 'Mat_Truoc' : 'Mat_Sau'}.${extension}`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    return false
  })

  const remove = () => onChanged(`delete-${side}`, async () => {
    if (!window.confirm(`Xóa ảnh ${title.toLowerCase()} CCCD của ${username}?`)) return false
    const result = await staffSecurityApi.deleteIdentity(username, side)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl('')
    setNotice({ type: 'success', message: result.message })
    window.dispatchEvent(new CustomEvent('vera-profile-updated'))
    return true
  })

  return <div className="employee-id-side">
    <div className="employee-id-side-head"><div><strong>{title}</strong><span>{metadata ? `Đã lưu · ${formatBytes(metadata.size_bytes)}` : 'Chưa có ảnh'}</span></div>{busy && <LoaderCircle className="spin" size={16}/>}</div>
    <div className="employee-id-preview">{previewUrl ? <img src={previewUrl} alt={`${title} CCCD`}/> : <div className="employee-id-placeholder">CCCD</div>}</div>
    <div className="employee-id-actions">
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp,image/*" onChange={chooseFile} hidden/>
      <button type="button" className="secondary-button compact" onClick={() => setCameraOpen(true)} disabled={Boolean(busy)}><Camera size={14}/> Chụp ảnh</button>
      <button type="button" className="secondary-button compact" onClick={() => inputRef.current?.click()} disabled={Boolean(busy)}><Upload size={14}/> {metadata ? 'Thay ảnh' : 'Tải ảnh'}</button>
      {metadata && <button type="button" className="secondary-button compact" onClick={view} disabled={Boolean(busy)}><Eye size={14}/> Xem</button>}
      {metadata && allowDownload && <button type="button" className="secondary-button compact" onClick={download} disabled={Boolean(busy)}><Download size={14}/> Tải xuống</button>}
      {metadata && <button type="button" className="danger-button compact" onClick={remove} disabled={Boolean(busy)}><Trash2 size={14}/> Xóa</button>}
    </div>
    {cameraOpen && <IdentityCamera title={title} onCancel={() => setCameraOpen(false)} onCapture={(file) => { setCameraOpen(false); acceptFile(file) }}/>} 
    {pendingFile && <IdentityImageEditor file={pendingFile} title={title} onCancel={() => setPendingFile(null)} onConfirm={uploadProcessed}/>} 
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
    try { const result = await staffSecurityApi.identityMetadata(username); setMeta({ front: result.front || null, back: result.back || null }) }
    catch (error) { setNotice({ type: 'error', message: error.message }) }
  }
  useEffect(() => { void load() }, [username]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (key, callback) => {
    setBusy(key); setNotice(null)
    try { const changed = await callback(); if (changed) await load() }
    catch (error) { setNotice({ type: 'error', message: error.message || 'Thao tác không thành công.' }) }
    finally { setBusy('') }
  }

  const resetPassword = () => run('password', async () => {
    if (password.length < 8) throw new Error('Mật khẩu mới phải có tối thiểu 8 ký tự.')
    if (password !== confirmPassword) throw new Error('Xác nhận mật khẩu chưa khớp.')
    if (!window.confirm(`Reset mật khẩu cho ${username}? Nhân viên sẽ phải đổi mật khẩu sau lần đăng nhập kế tiếp.`)) return false
    const result = await staffSecurityApi.resetPassword(username, password)
    setPassword(''); setConfirmPassword(''); setNotice({ type: 'success', message: result.message }); return false
  })

  if (!username) return null

  return <div className={`employee-identity-panel ${className}`}>
    <style>{`
      .employee-identity-panel{display:grid;gap:14px;padding:16px;border:1px solid #dfe7e3;border-radius:16px;background:#f9fbfa}.employee-identity-title{display:flex;gap:10px;align-items:flex-start}.employee-identity-title h3{margin:0;font-size:15px}.employee-identity-title p{margin:3px 0 0;color:#6c7873;font-size:12px;line-height:1.45}
      .employee-identity-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.employee-id-side{border:1px solid #e2e8e5;border-radius:14px;background:#fff;padding:12px;min-width:0}.employee-id-side-head{display:flex;justify-content:space-between;gap:8px;align-items:center}.employee-id-side-head div{display:grid;gap:2px}.employee-id-side-head strong{font-size:13px}.employee-id-side-head span{font-size:11px;color:#74807b}.employee-id-preview{height:132px;margin:10px 0;border-radius:10px;overflow:hidden;background:#eef3f1;display:flex;align-items:center;justify-content:center}.employee-id-preview img{width:100%;height:100%;object-fit:contain;background:#111}.employee-id-placeholder{font-weight:900;color:#9aa6a1;letter-spacing:.12em}.employee-id-actions{display:flex;flex-wrap:wrap;gap:7px}.employee-id-actions button{min-height:34px}
      .employee-password-reset{display:grid;gap:10px;padding:13px;border:1px solid #eadfcf;border-radius:14px;background:#fffaf2}.employee-password-reset-head{display:flex;gap:8px;align-items:flex-start}.employee-password-reset-head h4{margin:0;font-size:13px}.employee-password-reset-head p{margin:3px 0 0;font-size:11px;color:#776d60;line-height:1.45}.employee-password-reset-grid{display:grid;grid-template-columns:1fr 1fr auto;gap:9px;align-items:end}.employee-password-reset-grid label{display:grid;gap:5px;font-size:12px;font-weight:700}.employee-password-reset-grid input{min-width:0}.employee-identity-notice{padding:9px 11px;border-radius:10px;font-size:12px}.employee-identity-notice.success{background:#edf8f2;color:#17603b}.employee-identity-notice.error{background:#fff1f0;color:#a62a20}
      .identity-editor-backdrop{position:fixed;inset:0;z-index:10000;background:rgba(9,25,20,.72);display:flex;align-items:center;justify-content:center;padding:18px}.identity-editor-card,.identity-camera-card{width:min(980px,100%);max-height:94vh;overflow:auto;background:#fff;border-radius:20px;padding:18px;box-shadow:0 24px 70px rgba(0,0,0,.3)}.identity-camera-card{width:min(760px,100%)}.identity-editor-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.identity-editor-head h3{margin:3px 0}.identity-editor-head p{margin:0;color:#6c7873;font-size:12px}.identity-editor-layout{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(280px,.75fr);gap:16px;margin-top:14px}.identity-editor-preview{min-height:320px;border-radius:14px;background:#17201d;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:12px;gap:8px}.identity-editor-preview canvas{max-width:100%;max-height:58vh;object-fit:contain;background:#fff}.identity-editor-preview small{color:#d4dfda}.identity-editor-controls{display:grid;gap:10px;align-content:start}.identity-editor-section{display:grid;gap:8px;border:1px solid #e0e7e3;border-radius:12px;padding:11px}.identity-editor-section>strong{display:flex;align-items:center;gap:7px;font-size:12px}.identity-editor-section label{display:grid;gap:4px;font-size:11px;font-weight:800}.identity-editor-section input[type=range]{width:100%}.identity-editor-section select{width:100%}.identity-editor-buttons{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.identity-editor-buttons span{font-size:12px;font-weight:900}.identity-editor-size{font-size:11px;color:#68736f;line-height:1.5}.identity-editor-footer{display:flex;justify-content:flex-end;gap:9px;margin-top:14px}
      .identity-camera-landscape{position:relative;width:min(90vw,680px);max-width:100%;aspect-ratio:85.6/53.98;margin:16px auto 0;overflow:hidden;border-radius:18px;background:#101815}.identity-camera-landscape video{width:100%;height:100%;object-fit:cover}.identity-camera-card-guide{position:absolute;inset:4%;border:3px solid rgba(255,255,255,.98);border-radius:16px;box-shadow:0 0 0 999px rgba(0,0,0,.20),inset 0 0 0 1px rgba(0,0,0,.25);display:flex;align-items:flex-end;justify-content:center;padding:10px;pointer-events:none}.identity-camera-card-guide span{padding:5px 9px;border-radius:999px;background:rgba(0,0,0,.58);color:#fff;font-size:10px;font-weight:900;letter-spacing:.05em}.identity-camera-loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px;background:rgba(0,0,0,.35);color:#fff;font-weight:800}.identity-camera-help{margin:10px auto 0;max-width:680px;color:#68736f;font-size:11px;line-height:1.45;text-align:center}
      @media(max-width:700px){.employee-identity-panel{padding:12px;gap:11px}.employee-identity-grid{grid-template-columns:1fr}.employee-id-preview{height:118px}.employee-password-reset-grid{grid-template-columns:1fr}.employee-password-reset-grid button{width:100%}.identity-editor-backdrop{padding:7px}.identity-editor-card,.identity-camera-card{padding:12px;border-radius:14px}.identity-editor-layout{grid-template-columns:1fr}.identity-editor-preview{min-height:220px}.identity-editor-preview canvas{max-height:34vh}.identity-editor-footer{display:grid;grid-template-columns:1fr 1fr}.identity-editor-footer button{width:100%}.identity-camera-landscape{width:min(95vw,680px)}}
    `}</style>
    <div className="employee-identity-title"><ShieldCheck size={19}/><div><h3>CĂN CƯỚC CÔNG DÂN</h3><p>Camera chụp CCCD dùng khung chữ nhật ngang theo tỷ lệ thẻ CCCD và có viền để canh đúng bốn góc. Trước khi upload, ảnh vẫn được Crop, Rotate và nén WebP. Chỉ chính nhân viên và Admin được xem; Admin có thêm nút tải ảnh xuống.</p></div></div>
    <div className="employee-identity-grid"><IdentitySide username={username} side="front" title="Mặt trước" metadata={meta.front} busy={busy.startsWith('upload-front') || busy.startsWith('view-front') || busy.startsWith('download-front') || busy.startsWith('delete-front')} onChanged={run} setNotice={setNotice} allowDownload={allowPasswordReset}/><IdentitySide username={username} side="back" title="Mặt sau" metadata={meta.back} busy={busy.startsWith('upload-back') || busy.startsWith('view-back') || busy.startsWith('download-back') || busy.startsWith('delete-back')} onChanged={run} setNotice={setNotice} allowDownload={allowPasswordReset}/></div>
    {allowPasswordReset && <div className="employee-password-reset"><div className="employee-password-reset-head"><KeyRound size={17}/><div><h4>RESET MẬT KHẨU NHÂN VIÊN</h4><p>Mật khẩu hiện tại không hiển thị trên trình duyệt để bảo vệ tài khoản. Admin có thể đặt mật khẩu mới; nhân viên bắt buộc đổi lại sau lần đăng nhập tiếp theo.</p></div></div><div className="employee-password-reset-grid"><label>Mật khẩu mới<input type="password" minLength={8} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Tối thiểu 8 ký tự"/></label><label>Xác nhận mật khẩu<input type="password" minLength={8} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)}/></label><button type="button" className="primary-button" onClick={resetPassword} disabled={busy === 'password'}>{busy === 'password' ? <LoaderCircle className="spin" size={16}/> : <KeyRound size={16}/>} Reset mật khẩu</button></div></div>}
    {notice && <div className={`employee-identity-notice ${notice.type}`}>{notice.message}</div>}
  </div>
}
