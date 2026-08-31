import {
  Download, FileCheck2, FileText, LoaderCircle, Plus, RefreshCw,
  Save, Search, ShieldCheck, Trash2, Upload,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { numberInputDisplayValue } from '../lib/numberInput'

let nextRowId = 1
const makeRows = (rows = []) => rows.map((values) => ({ id: `rule-${nextRowId++}`, values: { ...values } }))

function displayDateTime(value) {
  if (!value) return 'Chưa có'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return String(value)
  return new Intl.DateTimeFormat('vi-VN', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(parsed)
}

function documentSignature(columns, rows) {
  return JSON.stringify({ columns, rows: rows.map((row) => row.values) })
}

function uniqueOptions(rows, key) {
  return Array.from(new Set(rows.map((row) => String(row.values?.[key] ?? '').trim()).filter(Boolean)))
    .sort((left, right) => left.localeCompare(right, 'vi'))
}

function Notice({ notice, onClose }) {
  if (!notice) return null
  return (
    <div className={`rules-notice ${notice.type}`} role="status">
      <strong>{notice.type === 'success' ? 'THÀNH CÔNG' : 'KHÔNG THÀNH CÔNG'}</strong>
      <span>{notice.message}</span>
      <button type="button" onClick={onClose} aria-label="Đóng thông báo">×</button>
    </div>
  )
}

export default function RulesPage() {
  const [data, setData] = useState(null)
  const [columns, setColumns] = useState([])
  const [rows, setRows] = useState([])
  const [originalSignature, setOriginalSignature] = useState('')
  const [quotaRows, setQuotaRows] = useState([])
  const [quotaOriginalSignature, setQuotaOriginalSignature] = useState('')
  const [lateThreshold, setLateThreshold] = useState(5)
  const [lateThresholdOriginal, setLateThresholdOriginal] = useState(5)
  const [selected, setSelected] = useState([])
  const [expanded, setExpanded] = useState([])
  const [search, setSearch] = useState('')
  const [reasonFilter, setReasonFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [newColumn, setNewColumn] = useState('')
  const [deleteColumn, setDeleteColumn] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const importRef = useRef(null)

  const installDocument = (result) => {
    const nextColumns = result.columns || []
    const nextRows = makeRows(result.rows || [])
    setData(result)
    setColumns(nextColumns)
    setRows(nextRows)
    setOriginalSignature(documentSignature(nextColumns, nextRows))
    const nextQuotaRows = (result.daily_quota?.days || []).map((item) => ({ ...item }))
    setQuotaRows(nextQuotaRows)
    setQuotaOriginalSignature(JSON.stringify(nextQuotaRows))
    const nextLateThreshold = Number(result.late_threshold?.threshold_minutes || 5)
    setLateThreshold(nextLateThreshold)
    setLateThresholdOriginal(nextLateThreshold)
    setSelected([])
    setExpanded([])
    setDeleteColumn('')
  }

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const result = await veraApi.rules()
      installDocument(result)
      setNotice(null)
    } catch (error) {
      setNotice({ type: 'error', message: error.message || 'Không tải được Bảng nội quy.' })
    } finally {
      setLoading(false)
    }
  }

  // Initial load only; later reloads are explicit so unsaved edits are not lost.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [])

  const permissions = data?.permissions || {}
  const canEdit = permissions.official_rules_edit === true
  const canEditDailyQuota = data?.can_edit_daily_quota === true
  const canEditLateThreshold = data?.can_edit_late_threshold === true
  const dirty = documentSignature(columns, rows) !== originalSignature
  const quotaDirty = JSON.stringify(quotaRows) !== quotaOriginalSignature
  const lateThresholdDirty = Number(lateThreshold) !== Number(lateThresholdOriginal)
  const requiredColumns = new Set(data?.required_columns || [])
  const deletableColumns = columns.filter((column) => !requiredColumns.has(column))
  const reasonOptions = useMemo(() => uniqueOptions(rows, 'Lý do nghỉ'), [rows])
  const typeOptions = useMemo(() => uniqueOptions(rows, 'Loại nghỉ'), [rows])

  const visibleRows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('vi')
    return rows.filter((row) => {
      if (reasonFilter && String(row.values['Lý do nghỉ'] ?? '').trim() !== reasonFilter) return false
      if (typeFilter && String(row.values['Loại nghỉ'] ?? '').trim() !== typeFilter) return false
      if (!needle) return true
      return columns.some((column) => String(row.values[column] ?? '').toLocaleLowerCase('vi').includes(needle))
    })
  }, [columns, rows, search, reasonFilter, typeFilter])

  const updateCell = (id, column, value) => {
    setRows((current) => current.map((row) => (
      row.id === id ? { ...row, values: { ...row.values, [column]: value } } : row
    )))
  }

  const updateQuota = (weekday, field, value) => {
    const number = Math.max(0, Math.min(100, Number.parseInt(value || '0', 10) || 0))
    setQuotaRows((current) => current.map((item) => (
      item.weekday === weekday ? { ...item, [field]: number } : item
    )))
  }

  const toggleSelected = (id) => {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  const toggleExpanded = (id) => {
    setExpanded((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  const addRow = () => {
    const values = Object.fromEntries(columns.map((column) => [column, '']))
    if (columns.includes('STT')) {
      const maxStt = rows.reduce((maximum, row) => Math.max(maximum, Number(row.values.STT) || 0), 0)
      values.STT = maxStt + 1
    }
    const [next] = makeRows([values])
    setRows((current) => [...current, next])
    setExpanded((current) => [...current, next.id])
  }

  const addColumn = () => {
    const name = newColumn.trim()
    if (!name) {
      setNotice({ type: 'error', message: 'Nhập tên cột trước khi thêm.' })
      return
    }
    if (columns.includes(name)) {
      setNotice({ type: 'error', message: 'Tên cột này đã tồn tại.' })
      return
    }
    setColumns((current) => [...current, name])
    setRows((current) => current.map((row) => ({ ...row, values: { ...row.values, [name]: '' } })))
    setNewColumn('')
    setNotice(null)
  }

  const removeColumn = () => {
    if (!deleteColumn) {
      setNotice({ type: 'error', message: 'Chọn cột cần xóa.' })
      return
    }
    if (!window.confirm(`Xóa cột “${deleteColumn}” khỏi vùng chỉnh sửa?`)) return
    setColumns((current) => current.filter((column) => column !== deleteColumn))
    setRows((current) => current.map((row) => {
      const values = { ...row.values }
      delete values[deleteColumn]
      return { ...row, values }
    }))
    setDeleteColumn('')
  }

  const removeSelected = () => {
    if (!selected.length) {
      setNotice({ type: 'error', message: 'Chưa chọn dòng Nội quy cần xóa.' })
      return
    }
    if (!window.confirm(`Xóa ${selected.length} dòng khỏi vùng chỉnh sửa? Thay đổi chỉ áp dụng sau khi bấm Ghi thay đổi & áp dụng.`)) return
    setRows((current) => current.filter((row) => !selected.includes(row.id)))
    setSelected([])
  }

  const run = async (key, callback) => {
    setBusy(key)
    setNotice(null)
    try {
      await callback()
    } catch (error) {
      setNotice({ type: 'error', message: error.message || 'Thao tác không thành công.' })
    } finally {
      setBusy('')
    }
  }

  const save = () => run('save', async () => {
    if (!dirty) throw new Error('Chưa có thay đổi cần ghi.')
    const result = await veraApi.saveRules({
      columns,
      rows: rows.map((row) => row.values),
      expected_revision: Number(data?.revision || 0),
    })
    await load(true)
    setNotice({ type: 'success', message: result.message })
  })

  const saveLateThreshold = () => run('late-threshold', async () => {
    const threshold = Number.parseInt(lateThreshold, 10)
    if (!Number.isInteger(threshold) || threshold < 1 || threshold > 180) {
      throw new Error('Ngưỡng đi trễ phải từ 1 đến 180 phút.')
    }
    if (!lateThresholdDirty) throw new Error('Ngưỡng đi trễ chưa có thay đổi cần áp dụng.')
    const result = await veraApi.saveLateThreshold({
      threshold_minutes: threshold,
      expected_revision: Number(data?.late_threshold?.revision || 0),
    })
    await load(true)
    setNotice({ type: 'success', message: result.message })
  })

  const saveDailyQuota = () => run('quota', async () => {
    if (!quotaDirty) throw new Error('Hạn mức nghỉ chưa có thay đổi cần áp dụng.')
    const result = await veraApi.saveDailyQuota({
      days: quotaRows.map(({ weekday, paid_limit, generated_limit }) => ({ weekday, paid_limit, generated_limit })),
      expected_revision: Number(data?.daily_quota?.revision || 0),
    })
    await load(true)
    setNotice({ type: 'success', message: result.message })
  })

  const importExcel = (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    run('import', async () => {
      const result = await veraApi.importRulesExcel(file)
      const importedRows = makeRows(result.rows || [])
      setColumns(result.columns || [])
      setRows(importedRows)
      setSelected([])
      setExpanded([])
      setNotice({ type: 'success', message: result.message })
    })
  }

  const discard = () => {
    if ((dirty || quotaDirty || lateThresholdDirty) && !window.confirm('Bỏ toàn bộ thay đổi chưa ghi?')) return
    load()
  }

  return (
    <div className="rules-page">
      <style>{`
        .rules-page{max-width:100%;overflow-x:hidden}
        .rules-filter-row{display:grid;grid-template-columns:minmax(260px,2fr) minmax(180px,1fr) minmax(180px,1fr);gap:9px;width:100%}
        .rules-filter-row>div,.rules-filter-row label{min-width:0}
        .rules-filter-row label{display:flex;flex-direction:column;gap:5px;font-weight:800;font-size:12px}
        .rules-filter-row select{width:100%;min-width:0}
        .rules-page .rules-grid-panel,.rules-page .rules-desktop-table,.rules-page .table-wrap{max-width:100%;max-height:none!important;overflow:visible!important}
        .rules-page .rules-table{width:100%;max-width:100%;table-layout:fixed}
        .rules-page .rules-table th,.rules-page .rules-table td{min-width:0!important;width:auto!important;white-space:normal!important;overflow-wrap:anywhere;word-break:break-word;padding:6px 5px}
        .rules-page .rules-table input{width:100%;min-width:0;box-sizing:border-box;padding:7px 5px}
        .rules-page .rules-table th{font-size:11px;line-height:1.15}
        .rules-page .rules-table td{font-size:12px;line-height:1.2}
        @media(max-width:900px){.rules-page .rules-desktop-table{display:none!important}.rules-page .rules-mobile-list{display:grid!important}}
        @media(max-width:720px){.rules-filter-row{grid-template-columns:1fr}.rules-page .rules-control-panel{padding:12px}}
      `}</style>
      <div className="page-heading-row rules-heading">
        <div>
          <span className="eyebrow"><FileText size={14} /> Quy định vận hành</span>
          <h1 className="page-title">Bảng nội quy</h1>
          <p className="page-subtitle">Quản lý đầy đủ lý do nghỉ, ngày phép, mức phạt và quyền đăng ký/hủy đang áp dụng.</p>
        </div>
        <button className="secondary-button" onClick={discard} disabled={loading || busy === 'save'}>
          <RefreshCw size={17} className={loading ? 'spin' : ''} /> Làm mới
        </button>
      </div>

      <Notice notice={notice} onClose={() => setNotice(null)} />

      <div className="metric-grid rules-metrics">
        {[
          ['Phiên bản', data?.revision ? `#${data.revision}` : 'Khởi tạo', FileCheck2],
          ['Số dòng', rows.length, FileText],
          ['Số cột', columns.length, ShieldCheck],
          ['Cập nhật gần nhất', displayDateTime(data?.updated_at), RefreshCw],
        ].map(([label, value, Icon]) => (
          <div className="metric-card" key={label}><div className="metric-icon"><Icon size={21} /></div><div><span>{label}</span><strong className={label === 'Cập nhật gần nhất' ? 'metric-small-value' : ''}>{value}</strong></div></div>
        ))}
      </div>

      <section className="panel late-threshold-panel">
        <div className="panel-title-row">
          <div>
            <h2>NGƯỠNG TỰ ĐỘNG PHẠT ĐI TRỄ</h2>
            <p>Hệ thống chỉ tạo phạt khi số phút trễ sau khi trừ Hỗ trợ đạt ngưỡng này.</p>
          </div>
          {lateThresholdDirty && <span className="rules-unsaved-chip">Chưa áp dụng</span>}
        </div>
        <div className="rules-filter-row" style={{ gridTemplateColumns: 'minmax(220px, 360px) auto' }}>
          <label>Ngưỡng đi trễ (phút)
            {canEditLateThreshold
              ? <input type="number" min="1" max="180" inputMode="numeric" value={numberInputDisplayValue(lateThreshold)} onChange={(event) => setLateThreshold(event.target.value)} />
              : <strong>{lateThreshold} phút</strong>}
          </label>
          {canEditLateThreshold && <button className="primary-button" disabled={!lateThresholdDirty || busy === 'late-threshold'} onClick={saveLateThreshold}>
            {busy === 'late-threshold' ? <LoaderCircle size={17} className="spin" /> : <Save size={17} />} Áp dụng ngưỡng mới
          </button>}
        </div>
        <p className="page-subtitle" style={{ marginTop: 10 }}>Ví dụ: ngưỡng 5 phút thì trễ 4 phút không phạt; trễ từ 5 phút trở lên mới phạt.</p>
      </section>

      <section className="panel daily-quota-panel">
        <div className="panel-title-row">
          <div>
            <h2>HẠN MỨC NGHỈ THEO NGÀY</h2>
            <p>Số nhân viên tối đa được nghỉ CÓ phép và nghỉ phát sinh trong từng ngày.</p>
          </div>
          {quotaDirty && <span className="rules-unsaved-chip">Chưa áp dụng</span>}
        </div>
        <div className="daily-quota-table-wrap">
          <table className="daily-quota-table">
            <thead><tr><th>Thứ</th><th>Nghỉ CÓ phép</th><th>Nghỉ phát sinh</th></tr></thead>
            <tbody>{quotaRows.map((item) => (
              <tr key={item.weekday}>
                <td><strong>{item.weekday_label}</strong></td>
                <td>{canEditDailyQuota
                  ? <input type="number" min="0" max="100" inputMode="numeric" value={numberInputDisplayValue(item.paid_limit)} onChange={(event) => updateQuota(item.weekday, 'paid_limit', event.target.value)} aria-label={`Nghỉ CÓ phép ${item.weekday_label}`} />
                  : <strong>{item.paid_limit}</strong>}
                </td>
                <td>{canEditDailyQuota
                  ? <input type="number" min="0" max="100" inputMode="numeric" value={numberInputDisplayValue(item.generated_limit)} onChange={(event) => updateQuota(item.weekday, 'generated_limit', event.target.value)} aria-label={`Nghỉ phát sinh ${item.weekday_label}`} />
                  : <strong>{item.generated_limit}</strong>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="daily-quota-footer">
          <span><ShieldCheck size={15} /> Chỉ Admin được thay đổi và áp dụng hạn mức này.</span>
          {canEditDailyQuota && <button className="primary-button" disabled={!quotaDirty || busy === 'quota'} onClick={saveDailyQuota}>
            {busy === 'quota' ? <LoaderCircle size={17} className="spin" /> : <Save size={17} />} Áp dụng nội quy mới
          </button>}
        </div>
      </section>

      <section className="panel rules-control-panel">
        <div className="rules-filter-row">
          <div className="rules-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm trong toàn bộ Bảng nội quy" /></div>
          <label>Lý do nghỉ<select value={reasonFilter} onChange={(event) => setReasonFilter(event.target.value)}><option value="">Tất cả lý do nghỉ</option>{reasonOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
          <label>Loại nghỉ<select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="">Tất cả loại nghỉ</option>{typeOptions.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        </div>
        {canEdit && <div className="rules-toolbar" style={{ marginTop: 9 }}>
          <div className="rules-add-column"><input value={newColumn} onChange={(event) => setNewColumn(event.target.value)} placeholder="Tên cột mới" /><button className="secondary-button" onClick={addColumn}><Plus size={16} /> Thêm cột</button></div>
          <div className="rules-delete-column"><select value={deleteColumn} onChange={(event) => setDeleteColumn(event.target.value)}><option value="">Chọn cột cần xóa</option>{deletableColumns.map((column) => <option key={column}>{column}</option>)}</select><button className="danger-button" disabled={!deleteColumn} onClick={removeColumn}><Trash2 size={16} /> Xóa cột</button></div>
        </div>}
        <div className="rules-actionbar">
          {canEdit && <button className="primary-button" onClick={addRow}><Plus size={17} /> Thêm dòng</button>}
          {permissions.official_rules_export && <button className="secondary-button" disabled={busy === 'export'} onClick={() => run('export', () => veraApi.exportRulesExcel())}><Download size={17} /> Export Excel</button>}
          {permissions.official_rules_import && <>
            <input ref={importRef} className="rules-file-input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={importExcel} />
            <button className="secondary-button" disabled={busy === 'import'} onClick={() => importRef.current?.click()}><Upload size={17} /> Import Excel</button>
          </>}
          {canEdit && <button className="secondary-button" disabled={!dirty || busy === 'save'} onClick={save}>{busy === 'save' ? <LoaderCircle size={17} className="spin" /> : <Save size={17} />} Ghi thay đổi & áp dụng</button>}
          {canEdit && <button className="danger-button rules-delete-rows" disabled={!selected.length} onClick={removeSelected}><Trash2 size={17} /> Xóa dòng đã chọn ({selected.length})</button>}
        </div>
        {!canEdit && <div className="rules-view-note"><ShieldCheck size={16} /> Bạn đang ở chế độ chỉ xem. Chỉ Admin/Quản lý được phép thay đổi Bảng nội quy.</div>}
      </section>

      <section className="panel rules-grid-panel">
        <div className="panel-title-row"><div><h2>BẢNG NỘI QUY</h2><p>{visibleRows.length} / {rows.length} dòng · {data?.updated_by ? `Cập nhật bởi ${data.updated_by}` : 'Chưa có người cập nhật'}.</p></div>{dirty && <span className="rules-unsaved-chip">Chưa ghi</span>}</div>
        {loading ? <div className="empty-cell"><LoaderCircle className="spin" /> Đang tải Bảng nội quy…</div> : <>
          <div className="rules-desktop-table table-wrap">
            <table className="rules-table">
              <thead><tr>{canEdit && <th className="rules-select-column">Chọn</th>}{columns.map((column) => <th key={column} className={requiredColumns.has(column) ? 'required' : ''}>{column}</th>)}</tr></thead>
              <tbody>{visibleRows.map((row) => <tr key={row.id}>
                {canEdit && <td className="center rules-select-column"><input type="checkbox" checked={selected.includes(row.id)} onChange={() => toggleSelected(row.id)} aria-label={`Chọn ${row.values['Lý do nghỉ'] || row.id}`} /></td>}
                {columns.map((column) => <td key={column}>{canEdit
                  ? <input value={row.values[column] ?? ''} onChange={(event) => updateCell(row.id, column, event.target.value)} aria-label={`${column} · ${row.values['Lý do nghỉ'] || 'dòng Nội quy'}`} />
                  : <span>{String(row.values[column] ?? '') || '—'}</span>
                }</td>)}
              </tr>)}</tbody>
            </table>
          </div>

          <div className="rules-mobile-list">{visibleRows.map((row, index) => {
            const open = expanded.includes(row.id)
            return <article className="rules-mobile-card" key={row.id}>
              <div className="rules-mobile-head">
                {canEdit && <input type="checkbox" checked={selected.includes(row.id)} onChange={() => toggleSelected(row.id)} aria-label={`Chọn ${row.values['Lý do nghỉ'] || row.id}`} />}
                <div><span>Dòng {index + 1}</span><strong>{row.values['Lý do nghỉ'] || 'Chưa nhập lý do nghỉ'}</strong><small>{row.values['Loại nghỉ'] || 'Chưa chọn loại nghỉ'}</small></div>
                <button className="text-button" onClick={() => toggleExpanded(row.id)}>{open ? 'Thu gọn' : canEdit ? 'Sửa' : 'Chi tiết'}</button>
              </div>
              {!open && <div className="rules-mobile-summary"><span>Ngày tính: <strong>{String(row.values['Số ngày tính phép'] ?? '') || '—'}</strong></span><span>Phạt: <strong>{String(row.values['Phạt vi phạm'] ?? '') || '0'} đ</strong></span></div>}
              {open && <div className="rules-mobile-fields">{columns.map((column) => <label key={column}>{column}{canEdit
                ? <textarea rows={String(row.values[column] ?? '').length > 80 ? 3 : 1} value={row.values[column] ?? ''} onChange={(event) => updateCell(row.id, column, event.target.value)} />
                : <span>{String(row.values[column] ?? '') || '—'}</span>
              }</label>)}</div>}
            </article>
          })}</div>
          {!visibleRows.length && <div className="empty-cell">Không có dòng Nội quy phù hợp bộ lọc.</div>}
        </>}
      </section>
    </div>
  )
}
