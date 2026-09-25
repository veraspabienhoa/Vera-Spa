import { Camera, ScanLine, Smartphone, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { formatVeraDateTime } from '../lib/veraDate'

function StationImage({ id, onViewed }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  const load = async () => {
    try {
      const blob = await veraApi.mobileStationImage(id)
      if (!blob.type.startsWith('image/jpeg')) throw new Error('Ảnh không hợp lệ.')
      setUrl(URL.createObjectURL(blob)); onViewed?.()
    } catch (cause) { setError(cause.message) }
  }
  return <span>{!url && <button type="button" className="secondary-button compact" onClick={load}>Xem ảnh</button>}{url && <img src={url} alt="Ảnh ghi từ điện thoại" width="90" loading="lazy"/>}{error && <small role="alert">{error}</small>}</span>
}

export default function MobileStationPanel({ registry, onRegistryChange, canRegister, canConfirm }) {
  const devices = registry.devices
  const stations = devices.filter(device => device.enabled && ['camera', 'scanner', 'faceid'].includes(device.kind))
  const [stationId, setStationId] = useState(() => localStorage.getItem('vera-mobile-station-id') || '')
  const [employee, setEmployee] = useState('')
  const [barcode, setBarcode] = useState('')
  const [camera, setCamera] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [records, setRecords] = useState(null)
  const [viewed, setViewed] = useState({})
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const pendingRef = useRef(null)

  useEffect(() => {
    if (typeof veraApi.mobileStationEvents !== 'function') return undefined
    let active = true
    const refresh = () => veraApi.mobileStationEvents().then(value => { if (active) setRecords(value.records) }).catch(() => {})
    void refresh()
    const timer = window.setInterval(refresh, 15000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  useEffect(() => {
    if (!camera) return undefined
    let active = true
    const start = async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('Trình duyệt cần hỗ trợ Camera và HTTPS.')
        const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } } })
        if (!active) { stream.getTracks().forEach(track => track.stop()); return }
        streamRef.current = stream
        if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play() }
      } catch (cause) { if (active) setMessage(cause.message || 'Không mở được Camera.') }
    }
    void start()
    return () => { active = false; streamRef.current?.getTracks().forEach(track => track.stop()); streamRef.current = null }
  }, [camera])

  const photo = () => new Promise((resolve, reject) => {
    const video = videoRef.current
    if (!video?.videoWidth) { reject(new Error('Camera chưa sẵn sàng.')); return }
    const canvas = document.createElement('canvas')
    const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight))
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Không chụp được ảnh.')), 'image/jpeg', 0.72)
  })

  const submit = async type => {
    if (!stationId) { setMessage('Chọn thiết bị điện thoại đã đăng ký.'); return }
    if (type === 'checkin' && !employee.trim()) { setMessage('Nhập tên đăng nhập của nhân viên trước khi chấm công.'); return }
    setBusy(true); setMessage('')
    try {
      const image = pendingRef.current?.type === type ? pendingRef.current.image : type === 'scan' ? null : await photo()
      if (image?.size > 2 * 1024 * 1024) throw new Error('Ảnh vượt 2 MB. Hãy giảm độ phân giải camera.')
      if (type === 'scan' && !barcode.trim()) {
        if (!('BarcodeDetector' in window)) throw new Error('Trình duyệt không hỗ trợ quét mã trực tiếp. Hãy nhập mã vào ô bên trên.')
        if (!videoRef.current) throw new Error('Bật camera để quét mã.')
        const results = await new window.BarcodeDetector().detect(videoRef.current)
        if (!results.length) throw new Error('Không thấy mã. Hướng camera vào mã và thử lại.')
        setBarcode(results[0].rawValue)
        setMessage(`Đã quét: ${results[0].rawValue}. Bấm Lưu mã để gửi.`)
        return
      }
      const pending = pendingRef.current?.type === type ? pendingRef.current : {
        id: crypto.randomUUID(), type, deviceId: stationId, employee: employee.trim(), barcode: barcode.trim(), image,
      }
      pendingRef.current = pending
      await veraApi.saveMobileStationEvent(pending)
      pendingRef.current = null
      setMessage(type === 'checkin' ? 'Đã gửi sự kiện chấm công. Admin cần xem ảnh và xác nhận để ghi nhận chấm công.' : 'Đã gửi dữ liệu từ điện thoại.')
      setRecords((await veraApi.mobileStationEvents()).records)
    } catch (cause) { setMessage(cause.message || 'Không gửi được dữ liệu; bấm lại để thử cùng mã thao tác.') }
    finally { setBusy(false) }
  }

  const confirm = async id => {
    if (!window.confirm('Đã đối chiếu ảnh và tên nhân viên? Xác nhận sẽ ghi chấm công và có thể cập nhật thời gian kết thúc kỳ nghỉ.')) return
    setBusy(true)
    try { await veraApi.confirmMobileCheckin(id); setRecords((await veraApi.mobileStationEvents()).records); setMessage('Đã xác nhận chấm công.') }
    catch (cause) { setMessage(cause.message || 'Không xác nhận được.') }
    finally { setBusy(false) }
  }

  const registerPhone = async () => {
    if (devices.length >= 100) { setMessage('Danh sách đã đủ 100 thiết bị.'); return }
    setBusy(true); setMessage('')
    try {
      const id = crypto.randomUUID()
      const phone = {
        id, name: `Điện thoại ${new Date().toLocaleDateString('vi-VN')}`, kind: 'camera',
        connection: 'network', manufacturer: '', model: '', serial: id, location: '', address: '', port: null,
        notes: 'Camera / quét mã / chấm công qua VERA HTTPS', enabled: true, adapter: 'pending',
      }
      const updated = await veraApi.saveDeviceRegistry({ expected_revision: registry.revision, devices: [...devices, phone] })
      onRegistryChange(updated)
      setStationId(id)
      localStorage.setItem('vera-mobile-station-id', id)
      setMessage('Đã đăng ký điện thoại này. Bật camera để bắt đầu.')
    } catch (cause) { setMessage(cause.message || 'Không đăng ký được điện thoại; tải lại danh sách và thử lại.') }
    finally { setBusy(false) }
  }

  return <section className="device-mobile-station panel">
    <h2><Smartphone size={20}/> Điện thoại chụp ảnh · quét mã · chấm công</h2>
    <p>Mở ứng dụng VERA bằng HTTPS và đăng nhập Admin trên điện thoại. Chọn hồ sơ điện thoại đang bật; ảnh và mã sẽ gửi tới máy chủ để xem trên máy tính. Hai thiết bị chỉ cần có Internet, không cần Bluetooth hay Wi-Fi Direct.</p>
    <div className="device-mobile-actions">
      <label>Điện thoại đã đăng ký<select value={stationId} onChange={event => { setStationId(event.target.value); pendingRef.current = null; localStorage.setItem('vera-mobile-station-id', event.target.value) }}><option value="">Chọn thiết bị</option>{stations.map(device => <option key={device.id} value={device.id}>{device.name}</option>)}</select></label>
      <label>Tên đăng nhập nhân viên<input value={employee} onChange={event => setEmployee(event.target.value)} maxLength={200} placeholder="Nhập chính xác tên đăng nhập"/></label>
      <label>Mã cần quét<input value={barcode} onChange={event => setBarcode(event.target.value)} maxLength={256} placeholder="Mã QR hoặc barcode"/></label>
    </div>
    <div className="device-actions">{canRegister && <button type="button" className="secondary-button" disabled={busy} onClick={registerPhone}><Smartphone size={16}/>Đăng ký điện thoại này</button>}<button type="button" className="secondary-button" onClick={() => setCamera(value => !value)}><Camera size={16}/>{camera ? 'Tắt camera' : 'Bật camera'}</button></div>
    {camera && <video ref={videoRef} playsInline muted className="device-mobile-preview"/>}
    <div className="device-actions">
      <button type="button" className="secondary-button" disabled={busy || !camera} onClick={() => submit('photo')}>Chụp & gửi ảnh</button>
      <button type="button" className="secondary-button" disabled={busy} onClick={() => submit('scan')}><ScanLine size={16}/>{barcode.trim() ? 'Lưu mã' : 'Quét mã'}</button>
      <button type="button" className="primary-button" disabled={busy || !camera || !employee.trim()} onClick={() => submit('checkin')}>Gửi chấm công có ảnh</button>
    </div>
    {message && <p role="status">{message}</p>}
    <div className="device-actions"><h3>Sự kiện từ điện thoại</h3><button type="button" className="secondary-button" disabled={busy} onClick={async () => { try { setRecords((await veraApi.mobileStationEvents()).records) } catch (cause) { setMessage(cause.message) } }}><RefreshCw size={16}/>Làm mới</button></div>
    {records && <div className="device-mobile-records">{records.map(record => <article key={record.id}><strong>{record.event_type === 'checkin' ? 'Chấm công' : record.event_type === 'scan' ? 'Quét mã' : 'Ảnh'}</strong><span>{record.employee_username || record.barcode || '—'}</span><small>{formatVeraDateTime(record.occurred_at)} · {record.operator}</small>{record.has_image && <StationImage id={record.id} onViewed={() => setViewed(current => ({ ...current, [record.id]: true }))}/ >}{record.event_type === 'checkin' && canConfirm && <button type="button" className="secondary-button compact" disabled={busy || Boolean(record.confirmed_at) || !viewed[record.id]} onClick={() => confirm(record.id)}>{record.confirmed_at ? 'Đã xác nhận' : 'Xem ảnh rồi xác nhận'}</button>}</article>)}</div>}
  </section>
}
