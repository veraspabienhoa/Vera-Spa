import { useCallback, useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'
import { searchTextMatches } from '../lib/searchText'
import { showSystemDialog, confirmDialog } from '../lib/systemDialogs'
import usePageRefresh from '../lib/usePageRefresh'
import './ResidencePage.css'

export default function ResidencePage({ user }) {
  const [data, setData] = useState(null)
  const [search, setSearch] = useState('')
  const [department, setDepartment] = useState('')
  const [query, setQuery] = useState('')
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
    && searchTextMatches([row.username, row.full_name], query)), [data, department, query])
  const save = async (row, included) => {
    if (busy) return
    if (!included && !await confirmDialog(`Bỏ ${row.username} khỏi bảng tạm trú?`)) return
    setBusy(true)
    try {
      const result = await veraApi.saveResidence({ username: row.username, included })
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
    <div className="residence-toolbar">
      <label>Bộ phận<select value={department} onChange={e => setDepartment(e.target.value)}>
        <option value="">Tất cả bộ phận</option>{data?.departments.map(item => <option key={item.code} value={item.code}>{item.name}</option>)}
      </select></label>
      <label>Tìm trong bảng<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Tên nhân viên" /></label>
      <button type="button" disabled={busy} onClick={load}>Làm mới</button>
      {canExport && <button type="button" disabled={busy || !data || !!error} onClick={exportExcel}>Xuất Excel</button>}
    </div>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p role="status">Đang tải…</p>}
    {canManage && data && <details className="residence-picker">
      <summary>Tìm và thêm nhân viên</summary>
      <label>Tên nhân viên<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Nhập tên để tìm" /></label>
      <div className="residence-candidates">{candidates.map(row => <div key={row.username}>
        <span><strong>{row.username}</strong> · {row.full_name} · {row.department}</span>
        <button type="button" disabled={busy || !!error} onClick={() => save(row, true)}>Thêm</button>
      </div>)}</div>
      {!candidates.length && <p>Không có nhân viên phù hợp để thêm.</p>}
    </details>}
    {data && <><p>{records.length} nhân viên tạm trú</p>
      <div className="residence-table" tabIndex="0" role="region" aria-label="Bảng nhân viên tạm trú">
        <table><thead><tr><th>STT</th>{data.columns.map(col => <th key={col.key}>{col.label}</th>)}{canManage && <th>Thao tác</th>}</tr></thead>
          <tbody>{records.map((row, index) => <tr key={row.username}><td>{index + 1}</td>
            {data.columns.map(col => <td key={col.key}>{row[col.key] === '' ? '—' : row[col.key]}</td>)}
            {canManage && <td><button type="button" disabled={busy || !!error} onClick={() => save(row, false)}>Bỏ khỏi bảng</button></td>}
          </tr>)}</tbody></table>
      </div>
      {!records.length && <p>Chưa có nhân viên tạm trú phù hợp.</p>}
    </>}
  </section>
}
