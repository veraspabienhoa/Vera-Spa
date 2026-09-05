import { CalendarRange, DatabaseBackup, Download, RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
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

const LABELS = { leave: 'Lịch nghỉ', payroll: 'Bảng lương', attendance: 'Chấm công' }

export default function StorageAdminPage() {
  const initial = rangeFor('current_month')
  const [preset, setPreset] = useState('current_month')
  const [start, setStart] = useState(initial[0])
  const [end, setEnd] = useState(initial[1])
  const [preview, setPreview] = useState({ counts: { leave: 0, payroll: 0, attendance: 0 }, total: 0 })
  const [exportDataset, setExportDataset] = useState('all')
  const [deleteDataset, setDeleteDataset] = useState('leave')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const load = async () => {
    setBusy('preview'); setNotice(null)
    try { setPreview(await veraApi.storagePreview(start, end)) }
    catch (error) { setNotice({ type: 'error', message: error.message }) }
    finally { setBusy('') }
  }

  useEffect(() => { void load() }, [start, end]) // eslint-disable-line react-hooks/exhaustive-deps

  const choosePreset = (value) => {
    setPreset(value)
    if (value === 'custom') return
    const range = rangeFor(value)
    setStart(range[0]); setEnd(range[1])
  }

  const selectedCount = Number(preview.counts?.[deleteDataset] || 0)
  const canDelete = selectedCount > 0 && confirmation === 'XÓA DỮ LIỆU' && !busy
  const cards = useMemo(() => Object.entries(LABELS).map(([key, label]) => ({ key, label, count: Number(preview.counts?.[key] || 0) })), [preview])

  const remove = async () => {
    if (!canDelete) return
    if (!window.confirm(`Xóa ${selectedCount} bản ghi ${LABELS[deleteDataset]}? Hành động này không thể hoàn tác.`)) return
    setBusy('delete'); setNotice(null)
    try {
      const result = await veraApi.deleteStorageData({ dataset: deleteDataset, start, end, expected_count: selectedCount, confirmation })
      setConfirmation('')
      setNotice({ type: 'success', message: result.message })
      await load()
    } catch (error) { setNotice({ type: 'error', message: error.message }) }
    finally { setBusy('') }
  }

  return <div className="feature-page storage-page">
    <div className="page-heading"><div><span className="eyebrow"><DatabaseBackup size={14} /> Chỉ Admin</span><h1>BỘ NHỚ HỆ THỐNG</h1><p>Xuất bản lưu Excel và quản lý thời hạn lưu Lịch nghỉ, Bảng lương, Chấm công.</p></div><button className="secondary-button" onClick={load} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'preview' ? 'spin' : ''} /> Làm mới</button></div>
    {notice && <div className={notice.type === 'success' ? 'success-box' : 'error-box'}>{notice.message}</div>}
    <section className="panel storage-range-panel">
      <div className="storage-presets">
        {[['previous_month', 'Tháng trước'], ['current_month', 'Tháng này'], ['previous_year', 'Năm trước'], ['custom', 'Tùy chỉnh']].map(([value, label]) => <button key={value} className={preset === value ? 'active' : ''} onClick={() => choosePreset(value)}>{label}</button>)}
      </div>
      <div className="storage-dates"><label><CalendarRange size={15} /> Từ ngày<VeraDateInput aria-label="Từ ngày" value={start} onChange={(event) => { setPreset('custom'); setStart(event.target.value) }} /></label><label><CalendarRange size={15} /> Đến ngày<VeraDateInput aria-label="Đến ngày" min={start} value={end} onChange={(event) => { setPreset('custom'); setEnd(event.target.value) }} /></label></div>
    </section>
    <div className="metric-grid small storage-metrics">{cards.map((item) => <div className="metric-card" key={item.key}><span>{item.label}</span><strong>{item.count}</strong></div>)}</div>
    <section className="panel storage-actions-grid">
      <div className="storage-action-card"><h2>EXPORT EXCEL</h2><p>Nên tải bản lưu trước mọi thao tác xóa.</p><label>Nhóm dữ liệu<select value={exportDataset} onChange={(event) => setExportDataset(event.target.value)}><option value="all">Tất cả (3 sheet)</option>{Object.entries(LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button className="primary-button" onClick={() => veraApi.exportStorageExcel(start, end, exportDataset)} disabled={Boolean(busy)}><Download size={16} /> Export dữ liệu</button></div>
      <div className="storage-action-card danger-zone"><h2>XÓA DỮ LIỆU</h2><p>Chỉ xóa nhóm đã chọn trong khoảng thời gian đang xem. Dữ liệu đồng bộ ngoài hệ thống có thể được nạp lại ở lần đồng bộ sau.</p><label>Nhóm dữ liệu<select value={deleteDataset} onChange={(event) => { setDeleteDataset(event.target.value); setConfirmation('') }}>{Object.entries(LABELS).map(([value, label]) => <option key={value} value={value}>{label} · {preview.counts?.[value] || 0} dòng</option>)}</select></label><label>Nhập “XÓA DỮ LIỆU” để xác nhận<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></label><button className="danger-button" onClick={remove} disabled={!canDelete}><Trash2 size={16} /> {busy === 'delete' ? 'Đang xóa…' : `Xóa ${selectedCount} dòng`}</button></div>
    </section>
  </div>
}
