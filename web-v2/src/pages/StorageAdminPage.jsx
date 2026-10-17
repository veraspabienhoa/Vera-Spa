import { confirmDialog } from '../lib/systemDialogs'
import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiCustomText from '../components/UiCustomText'
import { CalendarRange, DatabaseBackup, Download, RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import VeraDateInput from '../components/VeraDateInput'

const dateInput = (value) => {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const rangeFor = (preset) => {
  const now = new Date()
  if (preset === 'previous_month') {
    return [dateInput(new Date(now.getFullYear(), now.getMonth() - 1, 1)), dateInput(new Date(now.getFullYear(), now.getMonth(), 0))]
  }
  if (preset === 'previous_year') {
    return [`${now.getFullYear() - 1}-01-01`, `${now.getFullYear() - 1}-12-31`]
  }
  return [dateInput(new Date(now.getFullYear(), now.getMonth(), 1)), dateInput(new Date(now.getFullYear(), now.getMonth() + 1, 0))]
}

const EXPORT_LABELS = { leave: 'Lịch nghỉ', payroll: 'Bảng lương', attendance: 'Chấm công' }
const LABELS = { ...EXPORT_LABELS, attendance: 'Chấm công / Face ID', purchases: 'Nhập mua', revenue: 'Thu Chi nhập thủ công' }

export default function StorageAdminPage() {
  usePageRefresh(() => load(), () => Boolean(busy))
  const initial = rangeFor('current_month')
  const [preset, setPreset] = useState('current_month')
  const [start, setStart] = useState(initial[0])
  const [end, setEnd] = useState(initial[1])
  const [preview, setPreview] = useState(null)
  const [scope, setScope] = useState('range')
  const requestId = useRef(0)
  const deleting = useRef(false)
  const [exportDataset, setExportDataset] = useState('all')
  const [deleteDataset, setDeleteDataset] = useState('leave')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const query = { dataset: deleteDataset, scope, start: scope === 'range' ? start : null, end: scope === 'range' ? end : null }
  const queryKey = JSON.stringify(query)
  const currentQuery = useRef(queryKey)
  currentQuery.current = queryKey
  const validRange = scope === 'all_time' || Boolean(start && end && start <= end)

  const load = async () => {
    if (deleting.current) return
    const id = ++requestId.current
    setPreview(null); setConfirmation('')
    if (!validRange) { setBusy(''); return }
    setBusy('preview')
    try {
      const result = await veraApi.storageCleanupPreview(query)
      if (id === requestId.current && currentQuery.current === queryKey) setPreview({ ...result, queryKey })
    } catch (error) {
      if (id === requestId.current) setNotice({ type: 'error', message: error.message })
    } finally { if (id === requestId.current) setBusy('') }
  }

  useEffect(() => { void load(); return () => { requestId.current += 1 } }, [queryKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const choosePreset = (value) => {
    setPreset(value)
    if (value === 'custom') return
    const range = rangeFor(value)
    setStart(range[0]); setEnd(range[1])
  }

  const fresh = preview?.queryKey === queryKey
  const selectedCount = fresh ? Number(preview.total || 0) : 0
  const canDelete = fresh && selectedCount > 0 && confirmation === 'XÓA DỮ LIỆU' && !busy
  const cards = useMemo(() => Object.entries(preview?.counts || {}).map(([key, count]) => ({ key, label: LABELS[key], count })), [preview])

  const remove = async () => {
    if (!canDelete || deleting.current) return
    deleting.current = true
    setBusy('confirm')
    const capturedKey = queryKey
    try {
      const label = deleteDataset === 'all' ? 'tất cả 5 nhóm đang hỗ trợ' : LABELS[deleteDataset]
      if (!(await confirmDialog(`Xóa ${selectedCount} bản ghi ${label}, ${scope === 'all_time' ? 'toàn bộ thời gian' : 'trong khoảng ngày đã chọn'}? Hành động này không thể hoàn tác.`))) return
      if (capturedKey !== currentQuery.current) return
      setBusy('delete'); setNotice(null)
      const result = await veraApi.deleteStorageCleanup({ ...query, expected_count: selectedCount, fingerprint: preview.fingerprint, confirmation })
      setPreview(null); setConfirmation('')
      setNotice({ type: 'success', message: result.message })
    } catch (error) {
      setPreview(null); setConfirmation('')
      setNotice({ type: 'error', message: error.message })
    } finally {
      deleting.current = false
      setBusy('')
      await load()
    }
  }

  return <div className="feature-page storage-page">
    <div data-ui-key="u-6a8b09b301fb" className="page-heading"><div><span className="eyebrow"><DatabaseBackup size={14} /> Chỉ Admin</span><h1>BỘ NHỚ HỆ THỐNG</h1><p>Quản lý dữ liệu lưu trữ theo loại và thời gian.</p></div><button data-ui-key="u-baadccdfc0f5" data-ui-label-default="Làm mới" className="secondary-button" onClick={load} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'preview' ? 'spin' : ''} /><UiCustomText uiKey="u-baadccdfc0f5"> Làm mới</UiCustomText></button></div>
    <StableFeedback>{notice && <div className={notice.type === 'success' ? 'success-box' : 'error-box'}>{notice.message}</div>}</StableFeedback>
    <section data-ui-key="u-4e26ff629c4b" className="panel storage-range-panel"><fieldset disabled={busy === 'delete' || busy === 'confirm'} style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}>
      <label>Phạm vi<select value={scope} disabled={busy === 'delete' || busy === 'confirm'} onChange={event => setScope(event.target.value)}><option value="range">Theo khoảng thời gian</option><option value="all_time">Toàn bộ thời gian</option></select></label>
      {scope === 'range' && <><div className="storage-presets">
        {[['previous_month', 'Tháng trước'], ['current_month', 'Tháng này'], ['previous_year', 'Năm trước'], ['custom', 'Tùy chỉnh']].map(([value, label]) => <button data-ui-key="u-9c02717ee425" key={value} className={preset === value ? 'active' : ''} onClick={() => choosePreset(value)}>{label}</button>)}
      </div>
      <div className="storage-dates"><label><CalendarRange size={15} /> Từ ngày<VeraDateInput aria-label="Từ ngày" value={start} onChange={(event) => { setPreset('custom'); setStart(event.target.value) }} /></label><label><CalendarRange size={15} /> Đến ngày<VeraDateInput aria-label="Đến ngày" min={start} value={end} onChange={(event) => { setPreset('custom'); setEnd(event.target.value) }} /></label></div>
      </>}</fieldset>
    </section>
    <div className="metric-grid small storage-metrics">{cards.map((item) => <div data-ui-key="u-d98dc805116e" className="metric-card" key={item.key}><span>{item.label}</span><strong>{item.count}</strong></div>)}</div>
    <section data-ui-key="u-dc4ab3a48d91" className="panel storage-actions-grid">
      <div data-ui-key="u-1a6998c827f5" className="storage-action-card"><h2>EXPORT EXCEL</h2><p>Excel Lịch nghỉ, Bảng lương, Chấm công theo khoảng ngày; không phải bản sao lưu toàn hệ thống.</p><label>Nhóm dữ liệu<select value={exportDataset} onChange={(event) => setExportDataset(event.target.value)}><option value="all">Tất cả (3 sheet)</option>{Object.entries(EXPORT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button data-ui-key="u-a64be30e296c" data-ui-label-default="Export dữ liệu" className="primary-button" onClick={() => veraApi.exportStorageExcel(start, end, exportDataset)} disabled={Boolean(busy) || scope === 'all_time' || !validRange}><Download size={16} /><UiCustomText uiKey="u-a64be30e296c"> Export dữ liệu</UiCustomText></button></div>
      <div data-ui-key="u-2d80f02fe300" className="storage-action-card danger-zone"><h2>XÓA DỮ LIỆU</h2><p>Chỉ xóa các nhóm liệt kê bên dưới. Giữ tài khoản, hồ sơ nhân viên, cấu hình, hóa đơn Live Tour và lịch sử thao tác. Dữ liệu từ Face ID hoặc nguồn ngoài có thể được đồng bộ lại.</p><label>Nhóm dữ liệu<select disabled={busy === 'delete' || busy === 'confirm'} value={deleteDataset} onChange={(event) => { setDeleteDataset(event.target.value); setConfirmation('') }}><option value="all">Tất cả 5 nhóm bên dưới</option>{Object.entries(LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><p>{fresh ? `${selectedCount} bản ghi lưu trữ sẽ bị xóa (bao gồm các bản sao dữ liệu).` : 'Đang chờ bản xem trước hợp lệ.'}</p><label>Nhập “XÓA DỮ LIỆU” để xác nhận<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></label><button data-ui-key="u-a2f9d3c6319b" className="danger-button" onClick={remove} disabled={!canDelete}><Trash2 size={16} /> {busy === 'delete' ? 'Đang xóa…' : `Xóa ${selectedCount} dòng`}</button></div>
    </section>
  </div>
}
