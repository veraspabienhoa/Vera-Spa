import UiToolbar from '../components/UiToolbar'
import './FaceIdCard.css'
import './EmployeeIdentityMedia.css'
import UiCustomText from '../components/UiCustomText'
import { Camera, Crop, Download, Eye, FileDown, Image as ImageIcon, KeyRound, LoaderCircle, RotateCcw, RotateCw, ShieldCheck, SlidersHorizontal, Trash2, Upload, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { staffSecurityApi, faceIdApi } from '../lib/staffSecurityApi'

import VeraDateInput from '../components/VeraDateInput'
import { formatVeraDateTime } from '../lib/veraDate'

const TARGET_BYTES = 450 * 1024
const MAX_SOURCE_BYTES = 20 * 1024 * 1024
const MIN_CROP = 20
const CCCD_ASPECT_RATIO = 85.6 / 53.98
const PORTRAIT_ASPECT_RATIO = 3 / 4
const DEFAULT_RESET_PASSWORD = 'Vera123456'

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

function drawProcessedImage(canvas, image, crop, rotation, maxEdge, aspectRatio = null) {
  if (!canvas || !image) return
  const sourceWidth = image.naturalWidth || image.width
  const sourceHeight = image.naturalHeight || image.height
  const sx = Math.round(sourceWidth * crop.x / 100)
  const sy = Math.round(sourceHeight * crop.y / 100)
  let sw = Math.max(1, Math.round(sourceWidth * crop.w / 100))
  let sh = Math.max(1, Math.round(sourceHeight * crop.h / 100))
  let adjustedSx = sx
  let adjustedSy = sy
  const quarterTurn = Math.abs(rotation % 180) === 90
  if (aspectRatio) {
    const cropRatio = quarterTurn ? 1 / aspectRatio : aspectRatio
    if (sw / sh > cropRatio) {
      const nextWidth = Math.max(1, Math.round(sh * cropRatio))
      adjustedSx += Math.round((sw - nextWidth) / 2)
      sw = nextWidth
    } else {
      const nextHeight = Math.max(1, Math.round(sw / cropRatio))
      adjustedSy += Math.round((sh - nextHeight) / 2)
      sh = nextHeight
    }
  }
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
  context.drawImage(image, adjustedSx, adjustedSy, sw, sh, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight)
  context.restore()
}

function drawCropEditorImage(canvas, image, crop) {
  if (!canvas || !image) return
  const sourceWidth = image.naturalWidth || image.width
  const sourceHeight = image.naturalHeight || image.height
  const scale = Math.min(1, 1200 / Math.max(sourceWidth, sourceHeight))
  const width = Math.max(1, Math.round(sourceWidth * scale))
  const height = Math.max(1, Math.round(sourceHeight * scale))
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d', { alpha: false })
  context.drawImage(image, 0, 0, width, height)
  const x = width * crop.x / 100
  const y = height * crop.y / 100
  const w = width * crop.w / 100
  const h = height * crop.h / 100
  context.fillStyle = 'rgba(5, 18, 14, .62)'
  context.fillRect(0, 0, width, height)
  context.drawImage(image, sourceWidth * crop.x / 100, sourceHeight * crop.y / 100, sourceWidth * crop.w / 100, sourceHeight * crop.h / 100, x, y, w, h)
  context.strokeStyle = '#f5c451'
  context.lineWidth = Math.max(3, Math.round(Math.min(width, height) * 0.008))
  context.strokeRect(x, y, w, h)
  context.fillStyle = '#fff'
  const handle = Math.max(7, Math.round(Math.min(width, height) * 0.018))
  for (const [hx, hy] of [[x, y], [x + w, y], [x, y + h], [x + w, y + h]]) {
    context.beginPath()
    context.arc(hx, hy, handle, 0, Math.PI * 2)
    context.fill()
    context.stroke()
  }
}

async function createCompressedBlob(image, crop, rotation, preferredEdge, preferredQuality, aspectRatio = null) {
  let maxEdge = preferredEdge
  let quality = preferredQuality
  let lastBlob = null
  for (let attempt = 0; attempt < 14; attempt += 1) {
    const canvas = document.createElement('canvas')
    drawProcessedImage(canvas, image, crop, rotation, maxEdge, aspectRatio)
    lastBlob = await canvasBlob(canvas, quality)
    if (lastBlob.size <= TARGET_BYTES) return lastBlob
    if (quality > 0.44) quality = Math.max(0.42, quality - 0.07)
    else maxEdge = Math.max(650, Math.round(maxEdge * 0.82))
  }
  if (lastBlob?.size <= 650 * 1024) return lastBlob
  throw new Error(`Ảnh sau xử lý vẫn còn ${formatBytes(lastBlob?.size)}. Hãy Crop bớt vùng thừa hoặc giảm Độ phân giải.`)
}

function IdentityCamera({ title, onCancel, onCapture, aspectRatio = CCCD_ASPECT_RATIO, mediaLabel = 'CCCD' }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [facingMode, setFacingMode] = useState(() => aspectRatio < 1 ? 'user' : 'environment')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)

  useEffect(() => {
    let active = true
    const open = async () => {
      setBusy(true)
      setError('')
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Trình duyệt này không hỗ trợ camera trực tiếp. Hãy dùng nút Tải ảnh.')
        setBusy(false)
        return
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: facingMode },
            width: { ideal: 1920 },
            height: { ideal: 1210 },
            aspectRatio: { ideal: aspectRatio },
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
  }, [aspectRatio, facingMode])

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
    if (sourceRatio > aspectRatio) {
      sw = Math.round(video.videoHeight * aspectRatio)
      sx = Math.max(0, Math.round((video.videoWidth - sw) / 2))
    } else if (sourceRatio < aspectRatio) {
      sh = Math.round(video.videoWidth / aspectRatio)
      sy = Math.max(0, Math.round((video.videoHeight - sh) / 2))
    }

    const outputWidth = Math.min(1800, sw)
    const outputHeight = Math.max(1, Math.round(outputWidth / aspectRatio))
    const canvas = document.createElement('canvas')
    canvas.width = outputWidth
    canvas.height = outputHeight
    const context = canvas.getContext('2d', { alpha: false })
    context.drawImage(video, sx, sy, sw, sh, 0, 0, outputWidth, outputHeight)
    canvas.toBlob((blob) => {
      if (!blob) { setError('Không tạo được ảnh từ Camera.'); return }
      const file = new File([blob], `${mediaLabel.replace(/\s+/g, '_')}_${title.replace(/\s+/g, '_')}_${Date.now()}.jpg`, { type: 'image/jpeg' })
      onCapture(file)
    }, 'image/jpeg', 0.94)
  }

  const isPortrait = aspectRatio < 1
  return <div className="identity-editor-backdrop" role="dialog" aria-modal="true" aria-label={`Camera ${title} ${mediaLabel}`}>
    <div data-ui-key="u-4768cf250b00" className="identity-camera-card">
      <div className="identity-editor-head"><div><span className="eyebrow"><Camera size={14}/> Camera {mediaLabel}</span><h3>CHỤP {title.toUpperCase()}</h3><p>{isPortrait ? 'Canh khuôn mặt và phần thân trên trong khung dọc 3:4.' : 'Canh đủ bốn góc CCCD trong khung ngang rồi chụp.'}</p></div><button data-ui-key="u-73d792115c93" data-ui-label-default="Đóng" type="button" className="secondary-button compact" onClick={onCancel}><X size={16}/><UiCustomText uiKey="u-73d792115c93"> Đóng</UiCustomText></button></div>
      <div className="identity-camera-facing" aria-label="Lựa chọn camera trước hoặc camera sau">
        <span>Chọn camera</span>
        <button data-ui-key="u-8390b4bab86b" data-ui-label-default="Camera trước" type="button" aria-pressed={facingMode === 'user'} className={facingMode === 'user' ? 'primary-button compact' : 'secondary-button compact'} onClick={() => setFacingMode('user')} disabled={busy}><Camera size={14}/><UiCustomText uiKey="u-8390b4bab86b"> Camera trước</UiCustomText></button>
        <button data-ui-key="u-e84f14c43c4f" data-ui-label-default="Camera sau" type="button" aria-pressed={facingMode === 'environment'} className={facingMode === 'environment' ? 'primary-button compact' : 'secondary-button compact'} onClick={() => setFacingMode('environment')} disabled={busy}><Camera size={14}/><UiCustomText uiKey="u-e84f14c43c4f"> Camera sau</UiCustomText></button>
      </div>
      <div className={`identity-camera-landscape ${isPortrait ? 'portrait' : ''}`} style={{ aspectRatio }}>
        <video ref={videoRef} playsInline muted autoPlay style={{ transform: facingMode === 'user' ? 'scaleX(-1)' : 'none' }} />
        <div data-ui-key="u-41b5b7dc03c3" className="identity-camera-card-guide"><span>{isPortrait ? 'CANH ẢNH NHÂN VIÊN TỶ LỆ 3:4' : 'CANH 4 GÓC CCCD TRONG KHUNG NÀY'}</span></div>
        {busy && <div className="identity-camera-loading"><LoaderCircle className="spin" size={24}/> Đang mở Camera…</div>}
      </div>
      <div className="identity-camera-help">{isPortrait ? 'Ảnh được cắt theo tỷ lệ dọc 3:4 trước khi chuyển sang bước Crop/Rotate/Nén.' : 'Khung chụp nằm ngang theo tỷ lệ CCCD 85,6 × 53,98 mm; ảnh được cắt đúng tỷ lệ trước khi xử lý.'}</div>
      {error && <div className="employee-identity-notice error">{error}</div>}
      <div className="identity-editor-footer"><button data-ui-key="u-7d5ea8462f67" data-ui-label-default="Hủy" type="button" className="secondary-button" onClick={onCancel}><UiCustomText uiKey="u-7d5ea8462f67">Hủy</UiCustomText></button><button data-ui-key="u-7afe1cb8a636" data-ui-label-default="Chụp ảnh" type="button" className="primary-button" onClick={capture} disabled={busy || Boolean(error)}><Camera size={16}/><UiCustomText uiKey="u-7afe1cb8a636"> Chụp ảnh</UiCustomText></button></div>
    </div>
  </div>
}

export function IdentityImageEditor({ file, title, onCancel, onConfirm, aspectRatio = CCCD_ASPECT_RATIO, mediaLabel = 'CCCD', confirmLabel = 'Xử lý & tải lên' }) {
  const [source, setSource] = useState(null)
  const [sourceUrl, setSourceUrl] = useState('')
  const [crop, setCrop] = useState({ x: 0, y: 0, w: 100, h: 100 })
  const [rotation, setRotation] = useState(0)
  const [quality, setQuality] = useState(0.78)
  const [maxEdge, setMaxEdge] = useState(1600)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [cropTool, setCropTool] = useState('draw')
  const canvasRef = useRef(null)
  const dragRef = useRef(null)

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
    if (source && canvasRef.current) drawCropEditorImage(canvasRef.current, source, crop)
  }, [crop, source])

  const pointerPoint = (event) => {
    const bounds = canvasRef.current?.getBoundingClientRect()
    if (!bounds?.width || !bounds?.height) return null
    return {
      x: Math.max(0, Math.min(100, (event.clientX - bounds.left) * 100 / bounds.width)),
      y: Math.max(0, Math.min(100, (event.clientY - bounds.top) * 100 / bounds.height)),
    }
  }

  const beginCropGesture = (event) => {
    const point = pointerPoint(event)
    if (!point || busy) return
    event.preventDefault()
    canvasRef.current?.setPointerCapture?.(event.pointerId)
    dragRef.current = { point, crop: { ...crop }, mode: cropTool }
    if (cropTool === 'draw') setCrop({ x: point.x, y: point.y, w: 0.1, h: 0.1 })
  }

  const updateCropGesture = (event) => {
    const gesture = dragRef.current
    const point = pointerPoint(event)
    if (!gesture || !point) return
    event.preventDefault()
    if (gesture.mode === 'move') {
      const x = Math.max(0, Math.min(100 - gesture.crop.w, gesture.crop.x + point.x - gesture.point.x))
      const y = Math.max(0, Math.min(100 - gesture.crop.h, gesture.crop.y + point.y - gesture.point.y))
      setCrop({ ...gesture.crop, x, y })
      return
    }
    const x = Math.min(gesture.point.x, point.x)
    const y = Math.min(gesture.point.y, point.y)
    setCrop({ x, y, w: Math.max(0.1, Math.abs(point.x - gesture.point.x)), h: Math.max(0.1, Math.abs(point.y - gesture.point.y)) })
  }

  const endCropGesture = (event) => {
    const gesture = dragRef.current
    if (!gesture) return
    canvasRef.current?.releasePointerCapture?.(event.pointerId)
    dragRef.current = null
    setCrop((current) => current.w < MIN_CROP || current.h < MIN_CROP ? gesture.crop : current)
  }

  const setCropInset = (edge, raw) => {
    const value = Number(raw)
    setCrop((current) => {
      const right = Math.max(0, 100 - current.x - current.w)
      const bottom = Math.max(0, 100 - current.y - current.h)
      const next = { ...current }
      if (edge === 'left') {
        next.x = Math.min(value, 100 - right - MIN_CROP)
        next.w = 100 - right - next.x
      } else if (edge === 'right') {
        const nextRight = Math.min(value, 100 - current.x - MIN_CROP)
        next.w = 100 - current.x - nextRight
      } else if (edge === 'top') {
        next.y = Math.min(value, 100 - bottom - MIN_CROP)
        next.h = 100 - bottom - next.y
      } else if (edge === 'bottom') {
        const nextBottom = Math.min(value, 100 - current.y - MIN_CROP)
        next.h = 100 - current.y - nextBottom
      }
      return next
    })
  }

  const process = async () => {
    if (!source || busy) return
    setBusy(true); setError('')
    try {
      const blob = await createCompressedBlob(source, crop, rotation, maxEdge, quality, aspectRatio)
      await onConfirm(blob)
    } catch (processError) {
      setError(processError.message || 'Không xử lý được ảnh.')
    } finally {
      setBusy(false)
    }
  }

  return <div className="identity-editor-backdrop" role="dialog" aria-modal="true" aria-label={`Chỉnh ảnh ${title} ${mediaLabel}`}>
    <div data-ui-key="u-2b13b01e0a2c" className="identity-editor-card">
      <div className="identity-editor-head"><div><span className="eyebrow"><Crop size={14}/> {mediaLabel}</span><h3>CHỈNH ẢNH {title.toUpperCase()}</h3><p>Crop vùng cần giữ, xoay đúng chiều và nén ảnh trước khi tải lên theo tỷ lệ {aspectRatio < 1 ? '3:4' : 'CCCD'}.</p></div><button data-ui-key="u-a0252d06097b" data-ui-label-default="Đóng" type="button" className="secondary-button compact" onClick={onCancel} disabled={busy}><X size={16}/><UiCustomText uiKey="u-a0252d06097b"> Đóng</UiCustomText></button></div>
      <div className="identity-editor-layout">
        <div className="identity-editor-preview"><canvas ref={canvasRef} onPointerDown={beginCropGesture} onPointerMove={updateCropGesture} onPointerUp={endCropGesture} onPointerCancel={endCropGesture}/><small>Chạm/kéo trực tiếp trên ảnh để chọn hoặc di chuyển vùng giữ lại.</small></div>
        <div className="identity-editor-controls">
          <div className="identity-editor-section"><strong><RotateCw size={15}/> Xoay ảnh</strong><div className="identity-editor-buttons"><button data-ui-key="u-aad4a9dad05b" data-ui-label-default="-90°" type="button" className="secondary-button compact" onClick={() => setRotation((value) => (value + 270) % 360)}><RotateCcw size={14}/><UiCustomText uiKey="u-aad4a9dad05b"> -90°</UiCustomText></button><button data-ui-key="u-b71a25c16bb7" data-ui-label-default="+90°" type="button" className="secondary-button compact" onClick={() => setRotation((value) => (value + 90) % 360)}><RotateCw size={14}/><UiCustomText uiKey="u-b71a25c16bb7"> +90°</UiCustomText></button><span>{rotation}°</span></div></div>
          <div className="identity-editor-section"><strong><Crop size={15}/> Crop</strong>
            <small>Chọn “Vẽ vùng crop tự do” rồi kéo trên ảnh; hoặc chọn “Di chuyển ảnh/vùng chọn” để đặt đúng vị trí hiển thị.</small>
            <div className="identity-editor-buttons"><button data-ui-key="u-f2676edafc29" data-ui-label-default="Vẽ vùng crop tự do" type="button" className={cropTool === 'draw' ? 'primary-button compact' : 'secondary-button compact'} onClick={() => setCropTool('draw')}><Crop size={14}/><UiCustomText uiKey="u-f2676edafc29"> Vẽ vùng crop tự do</UiCustomText></button><button data-ui-key="u-8e6186c4554f" data-ui-label-default="Di chuyển ảnh/vùng chọn" type="button" className={cropTool === 'move' ? 'primary-button compact' : 'secondary-button compact'} onClick={() => setCropTool('move')}><SlidersHorizontal size={14}/><UiCustomText uiKey="u-8e6186c4554f"> Di chuyển ảnh/vùng chọn</UiCustomText></button></div>
            <label>Trái: {Math.round(crop.x)}%<input type="range" min="0" max={Math.max(0, 100 - (100 - crop.x - crop.w) - MIN_CROP)} value={crop.x} onChange={(e) => setCropInset('left', e.target.value)}/></label>
            <label>Phải: {Math.round(100 - crop.x - crop.w)}%<input type="range" min="0" max={Math.max(0, 100 - crop.x - MIN_CROP)} value={100 - crop.x - crop.w} onChange={(e) => setCropInset('right', e.target.value)}/></label>
            <label>Trên: {Math.round(crop.y)}%<input type="range" min="0" max={Math.max(0, 100 - (100 - crop.y - crop.h) - MIN_CROP)} value={crop.y} onChange={(e) => setCropInset('top', e.target.value)}/></label>
            <label>Dưới: {Math.round(100 - crop.y - crop.h)}%<input type="range" min="0" max={Math.max(0, 100 - crop.y - MIN_CROP)} value={100 - crop.y - crop.h} onChange={(e) => setCropInset('bottom', e.target.value)}/></label>
            <button data-ui-key="u-3d9e38d87ba3" data-ui-label-default="Khôi phục toàn ảnh" type="button" className="secondary-button compact" onClick={() => setCrop({ x: 0, y: 0, w: 100, h: 100 })}><UiCustomText uiKey="u-3d9e38d87ba3">Khôi phục toàn ảnh</UiCustomText></button>
          </div>
          <div className="identity-editor-section"><strong><SlidersHorizontal size={15}/> Nén trước khi upload</strong>
            <label>Độ phân giải tối đa<select value={maxEdge} onChange={(e) => setMaxEdge(Number(e.target.value))}><option value="1800">1800 px</option><option value="1600">1600 px</option><option value="1400">1400 px</option><option value="1200">1200 px</option><option value="1000">1000 px</option><option value="800">800 px</option></select></label>
            <label>Chất lượng: {Math.round(quality * 100)}%<input type="range" min="45" max="90" value={Math.round(quality * 100)} onChange={(e) => setQuality(Number(e.target.value) / 100)}/></label>
            <div className="identity-editor-size">Ảnh gốc: <b>{formatBytes(file.size)}</b> · Mục tiêu upload: <b>≤ {formatBytes(TARGET_BYTES)}</b></div>
          </div>
        </div>
      </div>
      {error && <div className="employee-identity-notice error">{error}</div>}
      <div className="identity-editor-footer"><button data-ui-key="u-0c9e77892f3e" data-ui-label-default="Hủy" type="button" className="secondary-button" onClick={onCancel} disabled={busy}><UiCustomText uiKey="u-0c9e77892f3e">Hủy</UiCustomText></button><button data-ui-key="u-2606b646551f" type="button" className="primary-button" onClick={process} disabled={busy || !source}>{busy ? <LoaderCircle className="spin" size={16}/> : <Upload size={16}/>} {busy ? 'Đang Crop · Rotate · Nén…' : confirmLabel}</button></div>
    </div>
  </div>
}

function IdentitySide({ username, side, title, metadata, busy, onChanged, setNotice, allowDownload, allowAdminEdit, onExtracted }) {
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
          const appliedCount = Object.keys(result.applied_fields || {}).length
          const detectedCount = Object.keys(result.extracted_fields || {}).length
          const ocrMessage = appliedCount
            ? ` Đã tự điền ${appliedCount} trường CCCD còn trống.`
            : detectedCount ? ' Đã nhận dạng CCCD; dữ liệu đang có được giữ nguyên.' : ' Không đọc được thông tin chữ; vui lòng nhập tay hoặc thử ảnh rõ hơn.'
          setNotice({ type: 'success', message: `${result.message} Ảnh gốc ${formatBytes(original?.size)} → sau Crop/Rotate/Nén ${formatBytes(blob.size)}.${ocrMessage}` })
          if (appliedCount) {
            onExtracted?.(result.applied_fields)
            window.dispatchEvent(new CustomEvent('vera-identity-extracted', { detail: { username, fields: result.applied_fields } }))
          }
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

  const editSaved = () => onChanged(`edit-${side}`, async () => {
    const blob = await staffSecurityApi.identityBlob(username, side)
    setPendingFile(new File([blob], `${username}_CCCD_${side}.${blob.type === 'image/png' ? 'png' : blob.type === 'image/jpeg' ? 'jpg' : 'webp'}`, { type: blob.type || 'image/webp' }))
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
    <UiToolbar data-ui-key="u-fd645c66d4ca" className="employee-id-actions">
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp,image/*" onChange={chooseFile} hidden/>
      <button data-ui-key="u-396ed536f64f" data-ui-label-default="Chụp ảnh" type="button" className="secondary-button compact" onClick={() => setCameraOpen(true)} disabled={Boolean(busy)}><Camera size={14}/><UiCustomText uiKey="u-396ed536f64f"> Chụp ảnh</UiCustomText></button>
      <button data-ui-key="u-4958ba7c82cc" type="button" className="secondary-button compact" onClick={() => inputRef.current?.click()} disabled={Boolean(busy)}><Upload size={14}/> {metadata ? 'Thay ảnh' : 'Tải ảnh'}</button>
      {metadata && <button data-ui-key="u-c9b41969e028" data-ui-label-default="Xem" type="button" className="secondary-button compact" onClick={view} disabled={Boolean(busy)}><Eye size={14}/><UiCustomText uiKey="u-c9b41969e028"> Xem</UiCustomText></button>}
      {metadata && allowDownload && <button data-ui-key="u-b379632a11cb" data-ui-label-default="Tải xuống" type="button" className="secondary-button compact" onClick={download} disabled={Boolean(busy)}><Download size={14}/><UiCustomText uiKey="u-b379632a11cb"> Tải xuống</UiCustomText></button>}
      {metadata && allowAdminEdit && <button data-ui-key="u-a51e321ceeea" data-ui-label-default="Crop / Xoay ảnh đã lưu" type="button" className="secondary-button compact" onClick={editSaved} disabled={Boolean(busy)}><Crop size={14}/><UiCustomText uiKey="u-a51e321ceeea"> Crop / Xoay ảnh đã lưu</UiCustomText></button>}
      {metadata && allowAdminEdit && <button data-ui-key="u-a212a818629e" data-ui-label-default="Xóa" type="button" className="danger-button compact" onClick={remove} disabled={Boolean(busy)}><Trash2 size={14}/><UiCustomText uiKey="u-a212a818629e"> Xóa</UiCustomText></button>}
    </UiToolbar>
    {cameraOpen && <IdentityCamera title={title} onCancel={() => setCameraOpen(false)} onCapture={(file) => { setCameraOpen(false); acceptFile(file) }}/>}
    {pendingFile && <IdentityImageEditor file={pendingFile} title={title} onCancel={() => setPendingFile(null)} onConfirm={uploadProcessed} aspectRatio={CCCD_ASPECT_RATIO} mediaLabel="CCCD"/>}
  </div>
}

function PortraitSide({ username, metadata, busy, onChanged, setNotice, allowAdminEdit, mediaApi = staffSecurityApi, side = 'portrait', title = 'Ảnh nhân viên', canEdit = true, sources }) {
  const inputRef = useRef(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [pendingFile, setPendingFile] = useState(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])
  useEffect(() => {
    let cancelled = false
    let loadedUrl = ''
    if (!metadata) {
      setPreviewUrl('')
      return undefined
    }
    mediaApi.identityBlob(username, side).then((blob) => {
      if (cancelled) return
      loadedUrl = URL.createObjectURL(blob)
      setPreviewUrl(loadedUrl)
    }).catch(() => {})
    return () => {
      cancelled = true
      if (loadedUrl) URL.revokeObjectURL(loadedUrl)
    }
  }, [metadata, username, mediaApi, side])

  const acceptFile = (file) => {
    if (!file) return
    if (!String(file.type || '').startsWith('image/')) { setNotice({ type: 'error', message: 'Chỉ chấp nhận file ảnh.' }); return }
    if (file.size > MAX_SOURCE_BYTES) { setNotice({ type: 'error', message: 'Ảnh gốc vượt quá 20 MB.' }); return }
    setPendingFile(file)
  }
  const uploadProcessed = async (blob) => new Promise((resolve, reject) => {
    onChanged('upload-portrait', async () => {
      try {
        const result = await mediaApi.uploadIdentity(username, side, blob)
        if (previewUrl) URL.revokeObjectURL(previewUrl)
        setPreviewUrl(URL.createObjectURL(blob))
        setPendingFile(null)
        setNotice({ type: 'success', message: `${result.message} Ảnh được lưu đúng tỷ lệ 3:4.` })
        window.dispatchEvent(new CustomEvent('vera-profile-updated'))
        resolve(true)
        return true
      } catch (error) { reject(error); throw error }
    })
  })
  const view = () => onChanged('view-portrait', async () => {
    const blob = await mediaApi.identityBlob(username, side)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(URL.createObjectURL(blob))
    return false
  })
  const editSaved = () => onChanged('edit-portrait', async () => {
    const blob = await mediaApi.identityBlob(username, side)
    setPendingFile(new File([blob], `${username}_Anh_Nhan_Vien.webp`, { type: blob.type || 'image/webp' }))
    return false
  })
  const remove = () => onChanged('delete-portrait', async () => {
    if (!window.confirm(`Xóa ${title} của ${username}?`)) return false
    const result = await mediaApi.deleteIdentity(username, side)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl('')
    setNotice({ type: 'success', message: result.message })
    return true
  })

  return <div className="employee-portrait-side">
    <div className="employee-id-side-head"><div><strong>{title}</strong><span>{metadata ? `Đã lưu · ${formatBytes(metadata.size_bytes)}` : 'Chưa có ảnh · tỷ lệ 3:4'}</span></div>{busy && <LoaderCircle className="spin" size={16}/>}</div>
    <div className="employee-portrait-preview">{previewUrl ? <img src={previewUrl} alt={title}/> : <div className="employee-id-placeholder"><ImageIcon size={28}/><span>ẢNH 3:4</span></div>}</div>
    {canEdit && sources?.(acceptFile)}
    <UiToolbar data-ui-key="u-e846d87f96c5" className="employee-id-actions">
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp,image/*" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; acceptFile(file) }} hidden/>
      <button data-ui-key="u-a4ae33de7ed9" data-ui-label-default="Chụp ảnh" type="button" className="secondary-button compact" onClick={() => setCameraOpen(true)} disabled={Boolean(busy) || !canEdit}><Camera size={14}/><UiCustomText uiKey="u-a4ae33de7ed9"> Chụp ảnh</UiCustomText></button>
      <button data-ui-key="u-5825e51c59e7" type="button" className="secondary-button compact" onClick={() => inputRef.current?.click()} disabled={Boolean(busy) || !canEdit}><Upload size={14}/> {metadata ? 'Thay ảnh' : 'Tải ảnh'}</button>
      {metadata && <button data-ui-key="u-1e33c261ec19" data-ui-label-default="Xem" type="button" className="secondary-button compact" onClick={view} disabled={Boolean(busy)}><Eye size={14}/><UiCustomText uiKey="u-1e33c261ec19"> Xem</UiCustomText></button>}
      {metadata && allowAdminEdit && <button data-ui-key="u-636be8616e35" data-ui-label-default="Crop / Xoay" type="button" className="secondary-button compact" onClick={editSaved} disabled={Boolean(busy) || !canEdit}><Crop size={14}/><UiCustomText uiKey="u-636be8616e35"> Crop / Xoay</UiCustomText></button>}
      {metadata && <button data-ui-key="u-5e617d4cab9b" data-ui-label-default="Xóa" type="button" className="danger-button compact" onClick={remove} disabled={Boolean(busy) || !canEdit}><Trash2 size={14}/><UiCustomText uiKey="u-5e617d4cab9b"> Xóa</UiCustomText></button>}
    </UiToolbar>
    {cameraOpen && <IdentityCamera title={title} mediaLabel="Hồ sơ" aspectRatio={PORTRAIT_ASPECT_RATIO} onCancel={() => setCameraOpen(false)} onCapture={(file) => { setCameraOpen(false); acceptFile(file) }}/>}
    {pendingFile && <IdentityImageEditor file={pendingFile} title={title} mediaLabel="Hồ sơ" aspectRatio={PORTRAIT_ASPECT_RATIO} onCancel={() => setPendingFile(null)} onConfirm={uploadProcessed}/>}
  </div>
}


export function FaceIdCard({ username }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [day, setDay] = useState(() => new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Ho_Chi_Minh'}).format(new Date()))
  const [captures, setCaptures] = useState(null)
  const load = async () => setData(await faceIdApi.metadata(username))
  useEffect(() => {
    let active = true
    setData(null); setNotice(null); setCaptures(null)
    faceIdApi.metadata(username).then((value) => { if (active) setData(value) }).catch((error) => {
      if (active && error.status !== 403) setNotice({type: 'error', message: error.message})
    })
    return () => { active = false }
  }, [username])
  const run = async (key, callback) => {
    setBusy(key); setNotice(null)
    try { if (await callback()) await load() }
    catch (error) { setNotice({type: 'error', message: error.message}) }
    finally { setBusy('') }
  }
  if (!data) return notice ? <p role="alert">{notice.message}</p> : null
  const asFile = (blob) => new File([blob], 'FaceID.jpg', {type: blob.type})
  return <div className="face-id-card" style={{border: '1px solid #315d4b', padding: 12, minWidth: 0}}>
    <PortraitSide key={username} username={username} metadata={data.photo} busy={busy}
      onChanged={run} setNotice={setNotice} allowAdminEdit canEdit={data.can_manage}
      mediaApi={faceIdApi} side="face_id" title="ẢNH FACE ID"
      sources={(acceptFile) => <div className="employee-id-actions">
        <button type="button" className="secondary-button compact" disabled={Boolean(busy)} onClick={() => run('portrait', async () => { acceptFile(asFile(await faceIdApi.portrait(username))); return false })}>Từ ảnh đại diện</button>
        <VeraDateInput aria-label="Ngày chụp FaceID" value={day} onChange={(event) => {setDay(event.target.value); setCaptures(null)}}/>
        <button type="button" className="secondary-button compact" disabled={Boolean(busy) || !day} onClick={() => run('captures', async () => {setCaptures(await faceIdApi.captures(username, day)); return false})}>Từ ảnh chụp trên FaceID</button>
        {captures && <div><p>Danh sách ảnh của thiết bị trong ngày. Hãy kiểm tra đúng nhân viên trước khi lưu; hệ thống chưa xác minh danh tính trong ảnh.</p>
          {captures.truncated && <p>Danh sách chưa đầy đủ do giới hạn đọc từ thiết bị.</p>}
          {!captures.records.length && <p>Không có ảnh chụp trong ngày đã chọn.</p>}
          {captures.records.map((record) => <button type="button" className="secondary-button compact" disabled={Boolean(busy)} key={record.event_id}
            onClick={() => run('capture', async () => { acceptFile(asFile(await faceIdApi.capture(username, day, record.event_id))); return false })}>{formatVeraDateTime(record.occurred_at)} · #{record.event_id}</button>)}
        </div>}
      </div>}/>
    <p>Ảnh lưu riêng trong VERA SPA, không xuất trong PDF hồ sơ. Chưa xác minh đăng ký ảnh trên thiết bị chấm công.</p>
    {notice && <p role="status" className={`employee-identity-notice ${notice.type}`}>{notice.message}</p>}
  </div>
}

function DraftMediaSide({ title, value, onChange, aspectRatio, mediaLabel, onExtracted }) {
  const inputRef = useRef(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [pendingFile, setPendingFile] = useState(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [ocrNote, setOcrNote] = useState('')
  useEffect(() => {
    if (!value) { setPreviewUrl(''); return undefined }
    const url = URL.createObjectURL(value)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [value])
  const acceptFile = (file) => {
    if (!file) return
    if (!String(file.type || '').startsWith('image/') || file.size > MAX_SOURCE_BYTES) return
    setOcrNote('')
    setPendingFile(file)
  }
  return <div className={`employee-id-side draft ${aspectRatio < 1 ? 'portrait-draft' : ''}`}>
    <div className="employee-id-side-head"><div><strong>{title}</strong><span>{value ? `Sẵn sàng tải · ${formatBytes(value.size)}` : `Chưa chọn · ${aspectRatio < 1 ? '3:4' : 'tỷ lệ CCCD'}`}</span></div></div>
    <div className={aspectRatio < 1 ? 'employee-portrait-preview' : 'employee-id-preview'}>{previewUrl ? <img src={previewUrl} alt={title}/> : <div className="employee-id-placeholder">{aspectRatio < 1 ? 'ẢNH 3:4' : 'CCCD'}</div>}</div>
    <UiToolbar data-ui-key="u-109f9dc9b127" className="employee-id-actions">
      <input ref={inputRef} type="file" accept="image/*" hidden onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; acceptFile(file) }}/>
      <button data-ui-key="u-d2583df8c0ab" data-ui-label-default="Chụp" type="button" className="secondary-button compact" onClick={() => setCameraOpen(true)}><Camera size={14}/><UiCustomText uiKey="u-d2583df8c0ab"> Chụp</UiCustomText></button>
      <button data-ui-key="u-66a9855d42ee" data-ui-label-default="Chọn ảnh" type="button" className="secondary-button compact" onClick={() => inputRef.current?.click()}><Upload size={14}/><UiCustomText uiKey="u-66a9855d42ee"> Chọn ảnh</UiCustomText></button>
      {value && <button data-ui-key="u-04746a6e70ae" data-ui-label-default="Bỏ chọn" type="button" className="secondary-button compact" onClick={() => onChange(null)}><X size={14}/><UiCustomText uiKey="u-04746a6e70ae"> Bỏ chọn</UiCustomText></button>}
    </UiToolbar>
    {ocrNote && <small className="employee-media-ocr-note">{ocrNote}</small>}
    {cameraOpen && <IdentityCamera title={title} mediaLabel={mediaLabel} aspectRatio={aspectRatio} onCancel={() => setCameraOpen(false)} onCapture={(file) => { setCameraOpen(false); acceptFile(file) }}/>}
    {pendingFile && <IdentityImageEditor file={pendingFile} title={title} mediaLabel={mediaLabel} aspectRatio={aspectRatio} onCancel={() => setPendingFile(null)} onConfirm={async (blob) => {
      onChange(blob)
      if (mediaLabel === 'CCCD') {
        try {
          const result = await staffSecurityApi.extractIdentity(blob)
          const fields = result.extracted_fields || {}
          if (Object.keys(fields).length) {
            onExtracted?.(fields)
            setOcrNote(`Đã nhận dạng ${Object.keys(fields).length} trường. Khi lưu, hệ thống sẽ đối chiếu Họ tên và Số Căn cước.`)
          } else setOcrNote('Không đọc được chữ; có thể nhập tay hoặc thử ảnh rõ hơn.')
        } catch (error) {
          setOcrNote(`Không thể tự đọc CCCD (${error.message}). Ảnh vẫn được giữ để lưu.`)
        }
      }
      setPendingFile(null)
    }}/>}
  </div>
}

export function EmployeeMediaDraftPanel({ value, onChange, onIdentityExtracted }) {
  const media = value || { portrait: null, front: null, back: null }
  const update = (side, blob) => onChange({ ...media, [side]: blob })
  return <div className="employee-media-draft span-2">
    <div className="employee-identity-title"><ImageIcon size={19}/><div><h3>ẢNH HỒ SƠ KHI TẠO NHÂN VIÊN</h3><p>Bắt buộc có ảnh nhân viên 3:4 và đủ hai mặt CCCD. Hệ thống tự điền ô còn trống, sau đó đối chiếu Họ tên và Số Căn cước trước khi cho lưu.</p></div></div>
    <div className="employee-media-draft-grid">
      <DraftMediaSide title="Ảnh nhân viên" value={media.portrait} onChange={(blob) => update('portrait', blob)} aspectRatio={PORTRAIT_ASPECT_RATIO} mediaLabel="Hồ sơ"/>
      <DraftMediaSide title="Mặt trước CCCD" value={media.front} onChange={(blob) => update('front', blob)} aspectRatio={CCCD_ASPECT_RATIO} mediaLabel="CCCD" onExtracted={onIdentityExtracted}/>
      <DraftMediaSide title="Mặt sau CCCD" value={media.back} onChange={(blob) => update('back', blob)} aspectRatio={CCCD_ASPECT_RATIO} mediaLabel="CCCD" onExtracted={onIdentityExtracted}/>
    </div>
  </div>
}

export default function EmployeeIdentityPanel({ username, allowPasswordReset = false, allowAdminEdit = false, className = '', onIdentityExtracted }) {
  const [meta, setMeta] = useState({ front: null, back: null, portrait: null })
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const load = async () => {
    if (!username) return
    try { const result = await staffSecurityApi.identityMetadata(username); setMeta({ front: result.front || null, back: result.back || null, portrait: result.portrait || null }) }
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
    if (!window.confirm(`Reset mật khẩu cho ${username} về ${DEFAULT_RESET_PASSWORD}?`)) return false
    const result = await staffSecurityApi.resetPassword(username, DEFAULT_RESET_PASSWORD)
    setNotice({ type: 'success', message: `${result.message} Mật khẩu mặc định: ${DEFAULT_RESET_PASSWORD}.` }); return false
  })

  const exportPdf = () => run('profile-pdf', async () => {
    await staffSecurityApi.exportProfilePdf(username)
    setNotice({ type: 'success', message: 'Đã xuất hồ sơ PDF đầy đủ để in.' })
    return false
  })

  if (!username) return null

  return <div className={`employee-identity-panel ${className}`}>

    <div className="employee-identity-title"><ImageIcon size={19}/><div><h3>ẢNH NHÂN VIÊN</h3><p>Ảnh hiển thị theo tỷ lệ dọc 3:4. Nhân viên có thể upload hoặc chụp trực tiếp với khung căn hình.</p></div></div>
    <div className="employee-portrait-section"><PortraitSide username={username} metadata={meta.portrait} busy={busy.includes('portrait')} onChanged={run} setNotice={setNotice} allowAdminEdit={allowAdminEdit || allowPasswordReset}/><FaceIdCard key={username} username={username}/></div>
    <div className="employee-identity-title"><ShieldCheck size={19}/><div><h3>CĂN CƯỚC CÔNG DÂN</h3></div></div>
    <div className="employee-identity-grid"><IdentitySide username={username} side="front" title="Mặt trước" metadata={meta.front} busy={busy.includes('front')} onChanged={run} setNotice={setNotice} allowDownload={allowAdminEdit || allowPasswordReset} allowAdminEdit={allowAdminEdit || allowPasswordReset} onExtracted={onIdentityExtracted}/><IdentitySide username={username} side="back" title="Mặt sau" metadata={meta.back} busy={busy.includes('back')} onChanged={run} setNotice={setNotice} allowDownload={allowAdminEdit || allowPasswordReset} allowAdminEdit={allowAdminEdit || allowPasswordReset} onExtracted={onIdentityExtracted}/></div>
    <div className="employee-profile-export"><button data-ui-key="u-3d346c6c0daf" type="button" className="secondary-button" onClick={exportPdf} disabled={busy === 'profile-pdf'}>{busy === 'profile-pdf' ? <LoaderCircle className="spin" size={16}/> : <FileDown size={16}/>} Xuất PDF hồ sơ nhân viên</button></div>
    {allowPasswordReset && <div className="employee-password-reset"><div className="employee-password-reset-head"><KeyRound size={17}/><div><h4>RESET MẬT KHẨU NHÂN VIÊN</h4><p>Bấm Reset để tự động đặt mật khẩu mặc định và xóa phiên đăng nhập cũ.</p></div></div><div className="employee-password-reset-grid"><div className="employee-password-default"><span>Mật khẩu mặc định</span><strong>{DEFAULT_RESET_PASSWORD}</strong></div><button data-ui-key="u-ef6e811b8699" type="button" className="primary-button employee-password-submit" onClick={resetPassword} disabled={busy === 'password'}>{busy === 'password' ? <LoaderCircle className="spin" size={16}/> : <KeyRound size={16}/>} Reset mật khẩu</button></div></div>}
    {notice && <div className={`employee-identity-notice ${notice.type}`}>{notice.message}</div>}
  </div>
}
