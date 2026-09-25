import { Camera, Monitor, Plus, Printer, RefreshCw, ScanLine, Server, Settings2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { formatVeraDateTime } from '../lib/veraDate'
import { searchTextMatches } from '../lib/searchText'
import MobileStationPanel from './MobileStationPanel'
import './DevicesAndCheckin.css'

const kindIcons = { faceid: ScanLine, printer: Printer, scanner: ScanLine, camera: Camera, screen: Monitor, other: Server }
const newDevice = () => ({ id: crypto.randomUUID(), name: '', kind: 'faceid', connection: 'network', manufacturer: '', model: '', serial: '', location: '', address: '', port: '', notes: '', enabled: true, adapter: 'pending' })

export default function DevicePage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(null)
  const [search, setSearch] = useState('')
  const [kind, setKind] = useState('')
  const [state, setState] = useState('')
  const [source, setSource] = useState(null)
  const [sourceError, setSourceError] = useState('')
  const [sourceBusy, setSourceBusy] = useState(false)
  const [detected, setDetected] = useState(null)
  const sequence = useRef(0)
  const registerUsbRef = useRef(null)
  const formRef = useRef(null)
  const reload = async () => {
    const id = ++sequence.current
    setBusy(true); setError('')
    try {
      const response = await veraApi.deviceRegistry()
      if (sequence.current === id) setData(response)
    } catch (cause) { if (sequence.current === id) setError(cause.message || 'Không tải được danh sách thiết bị.') }
    finally { if (sequence.current === id) setBusy(false) }
  }
  useEffect(() => { reload(); return () => { sequence.current += 1 } }, [])
  const registerUsb = async device => {
    if (!device || !data || data.devices.length >= 100) return
    const serial = String(device.serialNumber || '').slice(0, 100)
    const vendor = device.vendorId.toString(16).padStart(4, '0')
    const product = device.productId.toString(16).padStart(4, '0')
    const identity = serial || `USB ${vendor}:${product}`
    setDetected({ manufacturer: device.manufacturerName || '', model: device.productName || '', vendor, product })
    if (data.devices.some(item => item.connection === 'usb' && item.serial === identity)) return
    const record = { ...newDevice(), name: (device.productName || `Thiết bị USB ${vendor}:${product}`).slice(0, 160),
      kind: 'other', connection: 'usb', manufacturer: (device.manufacturerName || '').slice(0, 100),
      model: (device.productName || '').slice(0, 100), serial: identity, notes: `USB VID ${vendor} · PID ${product}` }
    try {
      setData(await veraApi.saveDeviceRegistry({ expected_revision: data.revision, devices: [...data.devices, record] }))
      setMessage('Đã thêm hồ sơ thiết bị USB. Kết nối nghiệp vụ cần bộ điều khiển tương thích.')
    } catch (cause) { setError(cause.message || 'Không lưu được hồ sơ thiết bị.'); await reload() }
  }
  registerUsbRef.current = registerUsb
  const discoverUsb = async () => {
    if (!navigator.usb?.requestDevice) { setError('Trình duyệt này không hỗ trợ nhận diện USB. Hãy dùng Chrome hoặc Edge trên máy tính.'); return }
    try { await registerUsb(await navigator.usb.requestDevice({ filters: [] })) }
    catch (cause) { if (cause?.name !== 'NotFoundError') setError(cause.message || 'Không nhận diện được USB.') }
  }
  const discoverBluetooth = async () => {
    if (!navigator.bluetooth?.requestDevice) { setError('Trình duyệt hoặc thiết bị này chưa hỗ trợ Web Bluetooth. iPhone không thể ghép nối qua tính năng này.'); return }
    try {
      const found = await navigator.bluetooth.requestDevice({ acceptAllDevices: true })
      if (!found) return
      setDetected({ manufacturer: 'Bluetooth', model: found.name || 'Thiết bị chưa đặt tên' })
      edit({ ...newDevice(), name: found.name || 'Thiết bị Bluetooth', kind: 'other', connection: 'bluetooth', serial: found.id, notes: 'Đã chọn qua Web Bluetooth; cần tích hợp giao thức của thiết bị để dùng dữ liệu.' })
    } catch (cause) { if (cause?.name !== 'NotFoundError') setError(cause.message || 'Không nhận diện được Bluetooth.') }
  }
  const hasRegistry = Boolean(data)
  useEffect(() => {
    if (!hasRegistry || !navigator.usb) return undefined
    const onConnect = event => { void registerUsbRef.current?.(event.device) }
    navigator.usb.addEventListener('connect', onConnect)
    navigator.usb.getDevices().then(devices => devices.forEach(onDevice => { void registerUsbRef.current?.(onDevice) })).catch(() => {})
    return () => navigator.usb.removeEventListener('connect', onConnect)
  }, [hasRegistry])
  const save = async event => {
    event.preventDefault()
    if (!event.currentTarget.reportValidity() || !data) return
    setBusy(true); setError(''); setMessage('')
    const device = { ...editing, name: editing.name.trim(), port: editing.port === '' || editing.port == null ? null : Number(editing.port) }
    const devices = data.devices.some(item => item.id === device.id)
      ? data.devices.map(item => item.id === device.id ? device : item) : [...data.devices, device]
    try {
      setData(await veraApi.saveDeviceRegistry({ expected_revision: data.revision, devices }))
      setEditing(null); setMessage('Đã lưu hồ sơ thiết bị.')
    } catch (cause) { setError(cause.message || 'Không lưu được thiết bị.') }
    finally { setBusy(false) }
  }
  const inspectSource = async () => {
    setSourceBusy(true); setSourceError('')
    try { setSource(await veraApi.attendanceSource()) }
    catch (cause) { setSource(null); setSourceError(cause.message || 'Không tải được trạng thái nguồn.') }
    finally { setSourceBusy(false) }
  }
  const edit = device => {
    setEditing({ ...device, port: device.port ?? '' }); setError(''); setMessage('')
    window.setTimeout(() => { formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); formRef.current?.querySelector('input')?.focus() }, 0)
  }
  const change = patch => setEditing(value => ({ ...value, ...patch }))
  const visible = (data?.devices || []).filter(item => (!kind || item.kind === kind)
    && (!state || String(item.enabled) === state)
    && searchTextMatches([item.name, item.serial, item.location, item.manufacturer, item.model].join(' '), search))
  return <section className="device-page">
    <div className="page-heading"><div><span className="eyebrow"><Server size={16} /> TRUNG TÂM THIẾT BỊ</span><h1>QUẢN LÝ THIẾT BỊ</h1><p>Quản lý FaceID, máy in, máy quét, màn hình và các thiết bị ngoại vi của spa.</p></div></div>
    <div className="device-actions">
      <button type="button" className="secondary-button" disabled={busy || !data || Boolean(editing) || data.devices.length >= 100} onClick={() => edit(newDevice())}><Plus size={16} />Thêm thiết bị</button>
      <button type="button" className="secondary-button" disabled={busy || Boolean(editing)} onClick={reload}><RefreshCw size={16} className={busy ? 'spin' : ''} />{busy ? 'Đang xử lý…' : 'Tải lại danh sách'}</button>
      <button type="button" className="secondary-button" disabled={busy || !data || data.devices.length >= 100} onClick={() => void discoverUsb()}><ScanLine size={16}/>Nhận diện USB</button>
      <button type="button" className="secondary-button" disabled={busy || !data || data.devices.length >= 100} onClick={() => void discoverBluetooth()}><ScanLine size={16}/>Nhận diện Bluetooth</button>
    </div>
    <p>Điện thoại Android/iPhone có thể chụp ảnh, quét mã và gửi sự kiện chấm công qua tài khoản Admin trên HTTPS. Wi-Fi Direct trực tiếp cần ứng dụng hệ điều hành hỗ trợ.</p>
    {detected && <p className="device-detected">Đã nhận diện: {detected.manufacturer || 'USB'} {detected.model || `${detected.vendor}:${detected.product}`}. <a href={`https://www.google.com/search?q=${encodeURIComponent(`${detected.manufacturer} ${detected.model} ${detected.vendor}:${detected.product} driver official`)}`} target="_blank" rel="noopener noreferrer">Tìm driver từ hãng</a></p>}
    {error && <p className="device-error" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {editing && <form ref={formRef} className="device-editor" onSubmit={save}>
      <h2>{data.devices.some(item => item.id === editing.id) ? 'Chỉnh sửa thiết bị' : 'Thêm thiết bị'}</h2>
      <fieldset disabled={busy}>
        <div className="device-form-grid">
          <label>Tên thiết bị<input required maxLength={160} value={editing.name} onChange={event => change({ name: event.target.value })} placeholder="Ví dụ: Máy in lễ tân" /></label>
          <label>Loại thiết bị<select disabled={editing.adapter === 'facegate_server'} value={editing.kind} onChange={event => change({ kind: event.target.value })}>{Object.entries(data.kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Vị trí<input maxLength={160} value={editing.location} onChange={event => change({ location: event.target.value })} placeholder="Lễ tân, phòng, tầng…" /></label>
          <label>Hãng sản xuất<input maxLength={100} value={editing.manufacturer} onChange={event => change({ manufacturer: event.target.value })} /></label>
          <label>Model<input maxLength={100} value={editing.model} onChange={event => change({ model: event.target.value })} /></label>
          <label>Serial / ID máy<input maxLength={100} value={editing.serial} onChange={event => change({ serial: event.target.value })} /></label>
          <label>Kiểu kết nối<select value={editing.connection} onChange={event => change({ connection: event.target.value })}>{Object.entries(data.connections).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Địa chỉ IP / tên máy<input maxLength={253} value={editing.address} onChange={event => change({ address: event.target.value })} placeholder="Chỉ địa chỉ, không nhập mật khẩu" /></label>
          <label>Cổng<input type="number" min="1" max="65535" value={editing.port} onChange={event => change({ port: event.target.value })} placeholder="Nếu thiết bị dùng cổng mạng" /></label>
        </div>
        <label>Ghi chú<textarea rows={3} maxLength={1000} value={editing.notes} onChange={event => change({ notes: event.target.value })} placeholder="Mục đích sử dụng, máy trạm phụ trách…" /></label>
        <label className="device-checkbox"><input type="checkbox" checked={editing.enabled} onChange={event => change({ enabled: event.target.checked })} />Đang sử dụng trong danh sách quản lý</label>
        <p>{editing.adapter === 'facegate_server' ? 'Hồ sơ này dùng kết nối FaceGate đã cấu hình trên máy chủ. Thay đổi địa chỉ trong hồ sơ không tự đổi đường kết nối đang chạy.' : 'Lưu hồ sơ để chuẩn bị kết nối. Thiết bị mới cần tích hợp bộ kết nối phù hợp với hãng/model và máy trạm sử dụng.'} Trạng thái sử dụng quản lý hồ sơ, không bật/tắt phần cứng.</p>
        <div className="device-actions"><button type="submit" className="secondary-button">Lưu thiết bị</button><button type="button" className="secondary-button" onClick={() => setEditing(null)}>Hủy</button></div>
      </fieldset>
    </form>}
    {data && <>
      <MobileStationPanel registry={data} onRegistryChange={setData}/>
      <div className="device-list-filters">
        <label>Tìm thiết bị<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Tên, serial, hãng, vị trí" /></label>
        <label>Loại thiết bị<select value={kind} onChange={event => setKind(event.target.value)}><option value="">Tất cả</option>{Object.entries(data.kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Trạng thái sử dụng<select value={state} onChange={event => setState(event.target.value)}><option value="">Tất cả</option><option value="true">Đang sử dụng</option><option value="false">Ngừng sử dụng</option></select></label>
      </div>
      <p>{visible.length} / {data.devices.length} thiết bị</p>
      <div className="device-grid">{visible.map(item => {
        const Icon = kindIcons[item.kind] || Server
        const adapter = data.adapters[item.adapter]
        return <article className="device-card" key={item.id}>
          <div className="device-card-title"><Icon size={24} /><div><h2>{item.name}</h2><span>{data.kinds[item.kind]}</span></div></div>
          <span className={`device-badge ${item.enabled ? '' : 'device-badge-muted'}`}>{item.enabled ? 'Đang sử dụng' : 'Ngừng sử dụng'}</span>
          <dl><dt>Vị trí</dt><dd>{item.location || 'Chưa đặt'}</dd><dt>Hãng / model</dt><dd>{[item.manufacturer, item.model].filter(Boolean).join(' · ') || 'Chưa nhập'}</dd><dt>Serial / ID</dt><dd>{item.serial || 'Chưa nhập'}</dd><dt>Kết nối</dt><dd>{data.connections[item.connection]}</dd><dt>Bộ kết nối</dt><dd>{adapter?.label || 'Chờ tích hợp'}</dd></dl>
          <p>{item.adapter === 'pending' ? 'Chưa có kết nối vận hành.' : adapter?.configured ? 'Đã có cấu hình máy chủ. Trạng thái online chưa được kiểm tra.' : 'Chưa đủ cấu hình máy chủ.'}</p>
          <button type="button" className="secondary-button" disabled={busy || Boolean(editing)} onClick={() => edit(item)}><Settings2 size={16} />Chỉnh sửa</button>
        </article>
      })}</div>
      {!visible.length && <p role="status">Không có thiết bị phù hợp bộ lọc.</p>}
    </>}
    <details className="device-source"><summary>Nguồn chấm công TimeSoft</summary>
      <p>Dữ liệu đồng bộ là nguồn riêng; không xác nhận trạng thái online của từng thiết bị.</p>
      <button type="button" className="secondary-button" disabled={sourceBusy} onClick={inspectSource}>{sourceBusy ? 'Đang kiểm tra…' : 'Kiểm tra nguồn'}</button>
      {sourceError && <p role="alert">{sourceError}</p>}
      {source && <p>{source.row_count} bản ghi; đồng bộ lúc {formatVeraDateTime(source.last_sync_at)}; {source.cache_fresh ? 'cache còn hạn' : 'cache hết hạn'}.</p>}
    </details>
  </section>
}
