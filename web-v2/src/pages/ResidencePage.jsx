import { useCallback, useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'
import { searchTextMatches } from '../lib/searchText'
import { showSystemDialog, confirmDialog } from '../lib/systemDialogs'
import usePageRefresh from '../lib/usePageRefresh'
import { RefreshCw, Download, Share2, Plus } from 'lucide-react'
import LiveTourSearchSelect from '../components/LiveTourSearchSelect'
import EmployeeProfileModal from '../components/EmployeeProfileModal'
import TrainingReportFiles from '../components/TrainingReportFiles'
import './ResidencePage.css'

export default function ResidencePage({ user }) {
  const [data, setData] = useState(null)
  const [search, setSearch] = useState('')
  const [department, setDepartment] = useState('')
  const [selected, setSelected] = useState('')
  const [exportScope, setExportScope] = useState(null)
  const [sharing, setSharing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const canManage = user?.role === 'admin' || user?.permissions?.residence_manage
  const canExport = user?.role === 'admin' || user?.permissions?.residence_export
  const load = useCallback(async () => {
    setError('')
    try { setData(await veraApi.residence()) }
    catch (err) { setError(err.message) }
  }, [])
  useEffect(() => { void load() }, [load])
  usePageRefresh(load, () => busy)
  const matches = row => (!department || row.department_code === department)
  const records = (data?.records || []).filter(row => matches(row) && searchTextMatches([row.username, row.full_name], search))
  const candidates = useMemo(() => (data?.employees || []).filter(row => !row.included
    && (!department || row.department_code === department)
    ), [data, department])
  const save = async (row, included) => {
    if (busy) return
    if (!included && !await confirmDialog(`Bỏ ${row.username} khỏi bảng tạm trú?`)) return
    setBusy(true)
    try {
      const result = await veraApi.saveResidence({ username: row.username, included })
      setSelected('')
      await load()
      void showSystemDialog({ kind: 'success', message: result.message })
    } catch (err) { void showSystemDialog({ kind: 'error', message: err.message }) }
    finally { setBusy(false) }
  }
  const exportExcel = async () => {
    setBusy(true)
    try { await veraApi.exportResidence({ department, search }) }
    catch (err) { void showSystemDialog({ kind: 'error', message: err.message }) }
    finally { setBusy(false) }
  }
  return <section className="panel residence-page">
    <h1>Tạm trú</h1>
    <div className="residence-toolbar residence-toolbar-top">
    {canManage && data && <div className="residence-picker">
      <LiveTourSearchSelect label="Tìm và thêm nhân viên" value={selected} onChange={setSelected}
        options={candidates.map(row => ({ value: row.username, label: row.username, detail: `${row.full_name} · ${row.department}`, searchText: `${row.username} ${row.full_name}` }))}
        placeholder="Nhập tên nhân viên" disabled={busy || !!error} />
      <button className="primary-button" type="button" disabled={busy || !!error || !selected}
        onClick={() => save({ username: selected }, true)}><Plus size={16} />Thêm</button>
    </div>}

      <label>Bộ phận<select value={department} onChange={e => { setDepartment(e.target.value); setSelected('') }}>
        <option value="">Tất cả bộ phận</option>{data?.departments.map(item => <option key={item.code} value={item.code}>{item.name}</option>)}
      </select></label>
      <button className="secondary-button" type="button" disabled={busy} onClick={load}><RefreshCw size={16} />Làm mới</button>
    </div>
    <div className="residence-toolbar residence-toolbar-bottom">
      <label>Tìm trong bảng<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Tên nhân viên" /></label>
      <div className="residence-export-actions">
      {canExport && <button className="secondary-button" type="button" disabled={busy || !data || !!error} onClick={exportExcel}><Download size={16} />Xuất Excel</button>}
    {canExport && <button className="secondary-button residence-export" type="button" disabled={busy || !data || !!error}
      onClick={() => setExportScope({ kind: 'residence', filters: { department, search } })}><Share2 size={16} />Xem / tải / chia sẻ PNG và PDF</button>}
      </div>
    </div>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p role="status">Đang tải…</p>}
    {canExport && exportScope && <EmployeeProfileModal labelledBy="residence-export-title" busy={sharing} onClose={() => setExportScope(null)}>
      <h2 id="residence-export-title">Bảng tạm trú · PNG / PDF</h2>
      <TrainingReportFiles scope={exportScope} onSharingChange={setSharing} onDenied={err => {
        setExportScope(null); void showSystemDialog({ kind: 'error', message: err.message })
      }} />
      <button data-dialog-close="true" className="secondary-button residence-close-button" type="button" disabled={sharing} onClick={() => setExportScope(null)}>Đóng</button>
    </EmployeeProfileModal>}
    {data && <><p>{records.length} nhân viên tạm trú</p>
      <div className="residence-table" tabIndex="0" role="region" aria-label="Bảng nhân viên tạm trú">
        <table><thead><tr><th>STT</th>{data.columns.map(col => <th key={col.key}>{col.label}</th>)}{canManage && <th>Thao tác</th>}</tr></thead>
          <tbody>{records.map((row, index) => <tr key={row.username}><td>{index + 1}</td>
            {data.columns.map(col => <td key={col.key}>{row[col.key] === '' ? '—' : row[col.key]}</td>)}
            {canManage && <td><button className="secondary-button" type="button" disabled={busy || !!error} onClick={() => save(row, false)}>Bỏ khỏi bảng</button></td>}
          </tr>)}</tbody></table>
      </div>
      {!records.length && <p>Chưa có nhân viên tạm trú phù hợp.</p>}
    </>}
  </section>
}
