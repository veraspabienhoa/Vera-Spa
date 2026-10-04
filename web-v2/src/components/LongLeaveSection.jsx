import StableFeedback from './StableFeedback'
import usePageRefresh from '../lib/usePageRefresh'
import UiToolbar from './UiToolbar'
import UiCustomText from './UiCustomText'
import { CalendarDays, CheckCircle2, Clock3, RefreshCw, Send, UserRoundCheck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { isApiConfigured, veraApi } from '../lib/api'
import { APPROVED_LEAVE_FILTERS, approvedLeaveStatus, filterApprovedLeaveItems, vietnamToday } from '../lib/approvedLeaveFilters'
import VeraDateInput from './VeraDateInput'

const ANNUAL = 'Nghỉ Phép năm'
const LONG = 'Nghỉ làm đẹp'
const RESIGNATION = 'Nghỉ việc'
const EMPTY_REQUESTS = []

const formatDateInput = (date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = () => formatDateInput(new Date())

const addDays = (value, days) => {
  const result = new Date(`${value}T00:00:00`)
  result.setDate(result.getDate() + days)
  return formatDateInput(result)
}

const formatDateDisplay = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}-${month}-${year}` : '—'
}

const shortEmployeeName = (value) => String(value || '')
  .split(/\s*[-–—]\s*/, 1)[0]
  .trim()
  .toLocaleLowerCase('vi-VN')
  .replace(/(^|\s)\S/g, (letter) => letter.toLocaleUpperCase('vi-VN'))

const emptyForm = () => ({
  request_type: ANNUAL,
  start_date: today(),
  end_date: today(),
  reason: '',
  detail: '',
})

export default function LongLeaveSection({ user, refreshRevision = 0 }) {
  usePageRefresh(() => load(), () => Boolean(loading || saving || returnBusyId || approvedBusy || approvedEditor))
  const role = String(user?.role || '').toLowerCase()
  const canOpen = role === 'admin'
    || user?.permissions?.long_leave === true
    || user?.permissions?.long_leave_form === true
    || user?.permissions?.long_leave_stats === true
    || user?.permissions?.resignation_form === true
  const canUseForm = role === 'admin' || user?.permissions?.long_leave_form === true
  const canUseResignation = role === 'admin' || user?.permissions?.resignation_form === true
  const canViewApproved = role === 'admin' || user?.permissions?.long_leave_stats === true
  const [overview, setOverview] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)
  const [approvedEditor, setApprovedEditor] = useState(null)
  const [approvedBusy, setApprovedBusy] = useState(false)
  const [pendingSync, setPendingSync] = useState('')
  const [approvedSearch, setApprovedSearch] = useState('')
  const [approvedFilter, setApprovedFilter] = useState('all')

  const load = useCallback(async () => {
    if (!canOpen || !isApiConfigured) return
    setLoading(true)
    try {
      const result = await veraApi.longLeaveOverview()
      setOverview(result)
      if (role === 'admin') {
        const pending = await veraApi.pendingApprovedLongLeave()
        setPendingSync(pending.request_ids[0] || '')
      }
      setNotice((current) => current?.status === 'success' ? current : null)
    } catch (error) {
      setNotice({ status: 'error', message: error.message || 'Không tải được dữ liệu Phép năm / Nghỉ làm đẹp.' })
    } finally {
      setLoading(false)
    }
  }, [canOpen, role])

  useEffect(() => { void load() }, [load, refreshRevision])
  useEffect(() => {
    if (!canUseForm && canUseResignation) {
      setForm((current) => ({ ...current, request_type: RESIGNATION, end_date: current.start_date }))
    }
  }, [canUseForm, canUseResignation])

  const isAnnual = form.request_type === ANNUAL
  const isResignation = form.request_type === RESIGNATION
  const resignationMinDate = overview?.resignation_eligibility?.earliest_resignation_date || addDays(today(), 30)
  const annualMaxEnd = useMemo(() => addDays(form.start_date, 6), [form.start_date])
  const approvedRequests = overview?.approved_requests || EMPTY_REQUESTS
  const resignationRequests = overview?.resignation_requests || EMPTY_REQUESTS
  const approvedItems = useMemo(() => filterApprovedLeaveItems(approvedRequests, resignationRequests), [approvedRequests, resignationRequests])
  const filteredApprovedItems = useMemo(() => filterApprovedLeaveItems(approvedRequests, resignationRequests, {
    filter: approvedFilter, search: approvedSearch,
  }), [approvedRequests, resignationRequests, approvedFilter, approvedSearch])
  const filterCounts = useMemo(() => Object.fromEntries(APPROVED_LEAVE_FILTERS.map(({ id }) => [id,
    filterApprovedLeaveItems(approvedRequests, resignationRequests, { filter: id, search: approvedSearch }).length,
  ])), [approvedRequests, resignationRequests, approvedSearch])
  const approvedToday = vietnamToday()
  const [returnDrafts, setReturnDrafts] = useState({})
  const [returnBusyId, setReturnBusyId] = useState('')
  const canSubmit = !saving && (isResignation
    ? canUseResignation && overview?.can_submit_resignation === true
    : canUseForm && overview?.can_submit === true)

  if (!canOpen) return null

  const changeRequestType = (requestType) => {
    setNotice(null)
    setForm((current) => {
      const startDate = requestType === RESIGNATION && current.start_date < resignationMinDate
        ? resignationMinDate
        : current.start_date
      return {
        ...current,
        request_type: requestType,
        start_date: startDate,
        reason: requestType === ANNUAL || requestType === RESIGNATION ? '' : current.reason,
        end_date: requestType === RESIGNATION
          ? startDate
          : (requestType === ANNUAL && current.end_date > addDays(current.start_date, 6)
              ? current.start_date
              : current.end_date),
      }
    })
  }

  const changeStartDate = (value) => {
    setForm((current) => {
      const maxEnd = addDays(value, 6)
      const invalidEnd = current.end_date < value || (current.request_type === ANNUAL && current.end_date > maxEnd)
      return { ...current, start_date: value, end_date: current.request_type === RESIGNATION || invalidEnd ? value : current.end_date }
    })
  }

  const submit = async (event) => {
    event.preventDefault()
    if (!canSubmit) return
    setSaving(true)
    setNotice(null)
    try {
      const result = await veraApi.createLongLeaveRequest(form)
      setNotice({
        status: 'success',
        message: `${result.message} Mã yêu cầu: ${result.request_id}.${(result.warnings || []).length ? ` ${result.warnings.join(' ')}` : ''}`,
      })
      setForm(emptyForm())
      await load()
    } catch (error) {
      setNotice({ status: 'error', message: `KHÔNG THÀNH CÔNG (${error.message || 'Không gửi được đơn.'})` })
    } finally {
      setSaving(false)
    }
  }

  const markReturned = async (item) => {
    const draft = returnDrafts[item.id] || {}
    if (!draft.return_date || !String(draft.note || '').trim()) {
      setNotice({ status: 'error', message: 'Vui lòng nhập ngày quay lại và ghi chú.' })
      return
    }
    if (!window.confirm(`Xác nhận ${shortEmployeeName(item.employee_name)} đã quay lại làm việc và kết thúc kỳ nghỉ?`)) return
    setReturnBusyId(item.id); setNotice(null)
    try {
      const result = await veraApi.markLongLeaveReturned(item.id, draft)
      setNotice({ status: 'success', message: result.message })
      setReturnDrafts((current) => ({ ...current, [item.id]: {} }))
      await load()
    } catch (error) {
      setNotice({ status: 'error', message: error.message || 'Không cập nhật được ngày quay lại.' })
    } finally { setReturnBusyId('') }
  }

  const saveApproved = async event => {
    event.preventDefault()
    setApprovedBusy(true)
    try {
      const { id, revision, start_date, end_date, reason, detail } = approvedEditor
      const result = await veraApi.editApprovedLongLeave(id, { revision, start_date, end_date, reason, detail })
      setPendingSync(result.mirror_pending ? id : '')
      setNotice({ status: 'success', message: result.message })
      setApprovedEditor(null)
      await load()
    } catch (error) { setNotice({ status: 'error', message: error.message }) }
    finally { setApprovedBusy(false) }
  }
  const cancelApproved = async item => {
    const note = window.prompt(`Hủy đơn ${item.id} của ${shortEmployeeName(item.employee_name)}. Nhập lý do hủy:`)
    if (!note?.trim()) return
    setApprovedBusy(true)
    try {
      const result = await veraApi.cancelApprovedLongLeave(item.id, { revision: item.revision, note: note.trim() })
      setPendingSync(result.mirror_pending ? item.id : '')
      setNotice({ status: 'success', message: result.message })
      await load()
    } catch (error) { setNotice({ status: 'error', message: error.message }) }
    finally { setApprovedBusy(false) }
  }
  const approvedActions = item => role === 'admin' && <div className="approved-request-actions">
    <button type="button" className="secondary-button compact" disabled={approvedBusy || loading}
      onClick={() => setApprovedEditor({ ...item, end_date: item.end_date || item.start_date })}>Sửa đơn</button>
    <button type="button" className="danger-button compact" disabled={approvedBusy || loading}
      onClick={() => cancelApproved(item)}>Hủy đơn</button>
  </div>
  const retrySync = async () => {
    setApprovedBusy(true)
    try {
      const result = await veraApi.syncApprovedLongLeave(pendingSync)
      if (!result.mirror_pending) { setPendingSync(''); setNotice({ status: 'success', message: 'Đã đồng bộ bảng dữ liệu cũ.' }) }
      else setNotice({ status: 'error', message: 'Chưa đồng bộ được bảng dữ liệu cũ. Dữ liệu máy chủ đã được lưu.' })
    } catch (error) { setNotice({ status: 'error', message: error.message }) }
    finally { setApprovedBusy(false) }
  }

  return (
    <section data-ui-key="u-25ce0d02cdc9" className="long-leave-section" aria-labelledby="long-leave-heading">
      <div data-ui-key="u-2b5d8cc42548" className="long-leave-heading-row">
        <div>
          <span className="eyebrow"><CalendarDays size={14} /> Quy trình xin duyệt</span>
          <h2 id="long-leave-heading">PHÉP NĂM / NGHỈ LÀM ĐẸP / NGHỈ VIỆC</h2>
          <p>Đơn mới được chuyển vào quy trình duyệt hiện tại. Chỉ đơn Phép năm đã duyệt mới ghi vào lịch nghỉ hằng ngày.</p>
        </div>
        <button data-ui-key="u-914b7aa7a213" data-ui-label-default="Làm mới" type="button" className="secondary-button compact" onClick={load} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'spin' : ''} /><UiCustomText uiKey="u-914b7aa7a213"> Làm mới
        </UiCustomText></button>
      </div>

      <StableFeedback>{notice && (
        <div className={`long-leave-notice ${notice.status}`} role={notice.status === 'error' ? 'alert' : 'status'}>
          {notice.status === 'success' ? <CheckCircle2 size={17} /> : <Clock3 size={17} />}
          <span>{notice.message}</span>
          <button data-ui-key="u-611f824d1c77" data-ui-label-default="×" type="button" onClick={() => setNotice(null)} aria-label="Đóng thông báo"><UiCustomText uiKey="u-611f824d1c77">×</UiCustomText></button>
        </div>
      )}</StableFeedback>

      {role !== 'admin' && (canUseForm || canUseResignation) && (
        <section data-ui-key="u-93da09a1ad4e" className="panel long-leave-form-panel">
          <div data-ui-key="u-277313a4cbea" className="panel-title-row">
            <div>
              <h2>FORM MẪU ĐĂNG KÝ</h2>
              <p>Nhân viên gửi đơn cho chính tài khoản đang đăng nhập.</p>
            </div>
          </div>

          <UiToolbar data-ui-key="u-ccb867101a1e" className="long-leave-type-tabs" role="group" aria-label="Chọn loại đơn">
            {[
              ...(canUseForm ? [ANNUAL, LONG] : []),
              ...(canUseResignation ? [RESIGNATION] : []),
            ].map((requestType) => (
              <button data-ui-key="u-c1812054792b"
                type="button"
                key={requestType}
                className={form.request_type === requestType ? 'active' : ''}
                onClick={() => changeRequestType(requestType)}
              >
                {requestType === ANNUAL
                  ? 'ĐƠN XIN NGHỈ PHÉP NĂM'
                  : (requestType === RESIGNATION ? 'ĐƠN XIN NGHỈ VIỆC' : 'ĐƠN XIN NGHỈ LÀM ĐẸP')}
              </button>
            ))}
          </UiToolbar>

          {!isResignation && overview?.paused && <div className="warning-box long-leave-gate"><strong>Đang tạm dừng nhận đơn.</strong> {overview.pause_message}</div>}
          {!isResignation && overview?.eligibility && (
            <div className={`${overview.eligibility.allowed ? 'success-box' : 'warning-box'} long-leave-gate`}>
              {overview.eligibility.message}
            </div>
          )}
          {isResignation && overview?.resignation_eligibility && (
            <div className={`${overview.resignation_eligibility.allowed ? 'success-box' : 'warning-box'} long-leave-gate`}>
              {overview.resignation_eligibility.message}
            </div>
          )}

          <form className="long-leave-form" onSubmit={submit}>
            <label className="long-leave-employee-field">
              <span>Tên nhân viên</span>
              <input value={shortEmployeeName(user?.employee_username)} readOnly />
            </label>

            <DateField label={isResignation ? 'Ngày nghỉ việc dự kiến' : (isAnnual ? 'Từ ngày Phép năm' : 'Từ ngày')} value={form.start_date} min={isResignation ? resignationMinDate : today()} onChange={changeStartDate} />
            {!isResignation && (
              <DateField
                label={isAnnual ? 'Đến ngày Phép năm' : 'Đến ngày'}
                value={form.end_date}
                min={form.start_date}
                max={isAnnual ? annualMaxEnd : undefined}
                onChange={(value) => setForm((current) => ({ ...current, end_date: value }))}
              />
            )}

            {!isAnnual && !isResignation && (
              <label className="long-leave-wide-field">
                <span>Lý do nghỉ làm đẹp</span>
                <input
                  value={form.reason}
                  onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))}
                  placeholder="Nhập lý do nghỉ làm đẹp"
                  required
                />
              </label>
            )}

            <label className="long-leave-wide-field">
              <span>{isResignation ? 'Lý do xin nghỉ việc' : (isAnnual ? 'Nội dung / ghi chú xin Phép năm' : 'Chi tiết lý do nghỉ làm đẹp')}</span>
              <textarea
                value={form.detail}
                onChange={(event) => setForm((current) => ({ ...current, detail: event.target.value }))}
                placeholder={isResignation ? 'Ghi rõ lý do và nội dung bàn giao dự kiến.' : (isAnnual ? 'Ghi chú cho Admin khi duyệt (không bắt buộc).' : 'Ghi rõ nội dung, thời gian và thông tin cần thiết.')}
                rows="4"
                required={!isAnnual}
              />
            </label>

            {isAnnual && <div className="long-leave-form-note">Đơn Phép năm được chọn tối đa 7 ngày liên tiếp và chỉ trừ quỹ sau khi Admin duyệt.</div>}
            {isResignation && <div className="long-leave-form-note">Ngày nghỉ việc dự kiến phải đủ ít nhất 30 ngày kể từ ngày làm đơn.</div>}

            <button data-ui-key="u-e992bb3a539c" type="submit" className="primary-button long-leave-submit" disabled={!canSubmit}>
              <Send size={16} /> {saving ? 'Đang gửi đơn…' : `Gửi đơn ${form.request_type}`}
            </button>
          </form>
        </section>
      )}

      {pendingSync && role === 'admin' && <button type="button" className="secondary-button" disabled={approvedBusy} onClick={retrySync}>Đồng bộ lại đơn {pendingSync}</button>}
      {approvedEditor && role === 'admin' && <section className="panel approved-request-editor">
        <h3>Sửa đơn đã duyệt · {approvedEditor.employee_name} · {approvedEditor.request_type}</h3>
        <form onSubmit={saveApproved}>
          <label>Từ ngày<VeraDateInput required disabled={approvedBusy} value={approvedEditor.start_date}
            onChange={event => setApprovedEditor(current => ({ ...current, start_date: event.target.value,
              end_date: current.request_type === RESIGNATION ? event.target.value : current.end_date }))} /></label>
          <label>Đến ngày<VeraDateInput required disabled={approvedBusy || approvedEditor.request_type === RESIGNATION}
            min={approvedEditor.start_date} value={approvedEditor.end_date}
            onChange={event => setApprovedEditor(current => ({ ...current, end_date: event.target.value }))} /></label>
          <label>Lý do<input disabled={approvedBusy} value={approvedEditor.reason || ''}
            onChange={event => setApprovedEditor(current => ({ ...current, reason: event.target.value }))} /></label>
          <label>Chi tiết<textarea disabled={approvedBusy} value={approvedEditor.detail || ''}
            onChange={event => setApprovedEditor(current => ({ ...current, detail: event.target.value }))} /></label>
          <div className="approved-request-actions"><button type="submit" className="primary-button" disabled={approvedBusy}>Lưu thay đổi</button>
            <button type="button" className="secondary-button" disabled={approvedBusy} onClick={() => setApprovedEditor(null)}>Đóng</button></div>
        </form>
      </section>}
      {canViewApproved && (
        <section data-ui-key="u-4b4ef7220440" className="panel approved-leave-panel">
          <div data-ui-key="u-d06aabe803eb" className="panel-title-row">
            <div>
              <h2>DANH SÁCH NHÂN VIÊN ĐÃ ĐƯỢC DUYỆT</h2>
              <p>{filteredApprovedItems.length} / {approvedItems.length} đơn nghỉ đã được duyệt.</p>
            </div>
            <div className="approved-count-chip"><UserRoundCheck size={15} /> {filteredApprovedItems.length}</div>
          </div>

          <div className="approved-leave-filters">
            <label className="approved-leave-search">
              <span>Tìm theo tên nhân viên</span>
              <input type="search" value={approvedSearch} onChange={(event) => setApprovedSearch(event.target.value)}
                placeholder="Nhập tên nhân viên" aria-label="Tìm theo tên nhân viên" />
            </label>
            <div className="approved-leave-filter-buttons" role="group" aria-label="Bộ lọc đơn đã duyệt">
              {APPROVED_LEAVE_FILTERS.map(({ id, label }) => (
                <button key={id} type="button" className={approvedFilter === id ? 'active' : ''}
                  aria-pressed={approvedFilter === id} onClick={() => setApprovedFilter(id)}>
                  {label}<span>{filterCounts[id] || 0}</span>
                </button>
              ))}
            </div>
          </div>

          {filteredApprovedItems.length === 0 ? (
            <div className="setup-note">{approvedItems.length ? 'Không tìm thấy đơn phù hợp với bộ lọc.' : 'Chưa có nhân viên được duyệt.'}</div>
          ) : (
            <>
              <div className="approved-leave-desktop table-wrap">
                <table data-ui-key="u-db44f0f2b18e">
                  <thead><tr><th>Nhân viên</th><th>Loại đơn</th><th>Từ ngày</th><th>Đến ngày</th><th className="center">Số ngày</th><th>Trạng thái</th><th>Nội dung</th><th>Chi tiết</th><th>Người duyệt</th>{role === 'admin' && <th>Thao tác / quay lại làm việc</th>}</tr></thead>
                  <tbody>
                    {filteredApprovedItems.map((item) => {
                      const status = approvedLeaveStatus(item, approvedToday)
                      return (
                      <tr key={item.id}>
                        <td><strong>{shortEmployeeName(item.employee_name)}</strong></td>
                        <td><span className={`request-type-chip ${item.request_type === ANNUAL ? 'annual' : (item.source === 'resignation' ? 'resignation' : 'long')}`}>{item.request_type}</span></td>
                        <td>{formatDateDisplay(item.start_date)}</td>
                        <td>{formatDateDisplay(item.end_date)}</td>
                        <td className="center"><strong>{item.days || '—'}</strong></td>
                        <td><span className={`approved-leave-status ${status.id}`}>{status.label}</span></td>
                        <td>{item.reason || '—'}</td>
                        <td className="detail-cell">{item.detail || '—'}</td>
                        <td>{item.approved_by || '—'}<small>{item.approved_date || ''}</small></td>
                        {role === 'admin' && <td className="long-leave-return-cell">{approvedActions(item)}{item.source === 'resignation'
                          ? null
                          : item.leave_completed
                            ? <><strong>{formatDateDisplay(item.return_date)}</strong><small>{item.return_note}</small><em>Đã kết thúc kỳ nghỉ</em></>
                            : <><VeraDateInput value={returnDrafts[item.id]?.return_date || ''} min={item.start_date} onChange={(event) => setReturnDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], return_date: event.target.value } }))} aria-label="Ngày quay lại làm việc"/><input value={returnDrafts[item.id]?.note || ''} onChange={(event) => setReturnDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], note: event.target.value } }))} placeholder="Ghi chú đã quay lại"/><button data-ui-key="u-560863cab625" data-ui-label-default="Kết thúc kỳ nghỉ" type="button" className="secondary-button compact" disabled={returnBusyId === item.id} onClick={() => markReturned(item)}><UiCustomText uiKey="u-560863cab625">Kết thúc kỳ nghỉ</UiCustomText></button></>}
                        </td>}
                      </tr>
                    )})}
                  </tbody>
                </table>
              </div>

              <div className="approved-leave-mobile-list">
                {filteredApprovedItems.map((item) => {
                  const status = approvedLeaveStatus(item, approvedToday)
                  return (
                  <article className="approved-leave-mobile-card" key={item.id}>
                    <div className="approved-leave-mobile-head">
                      <div><strong>{shortEmployeeName(item.employee_name)}</strong><small>{item.id}</small></div>
                      <span className={`request-type-chip ${item.request_type === ANNUAL ? 'annual' : (item.source === 'resignation' ? 'resignation' : 'long')}`}>{item.request_type}</span>
                    </div>
                    <span className={`approved-leave-status ${status.id}`}>{status.label}</span>
                    <div className="approved-leave-mobile-period">
                      <span><small>Từ ngày</small><strong>{formatDateDisplay(item.start_date)}</strong></span>
                      <span><small>Đến ngày</small><strong>{formatDateDisplay(item.end_date)}</strong></span>
                      <span><small>Số ngày</small><strong>{item.days || '—'}</strong></span>
                    </div>
                    <p><strong>Nội dung:</strong> {item.reason || '—'}</p>
                    <p><strong>Chi tiết:</strong> {item.detail || '—'}</p>
                    <p><strong>Người duyệt:</strong> {item.approved_by || '—'} · {item.approved_date || '—'}</p>
                    {role === 'admin' && <div className="long-leave-return-mobile">{approvedActions(item)}{item.source === 'resignation'
                      ? null
                      : item.leave_completed
                        ? <p><strong>Đã quay lại:</strong> {formatDateDisplay(item.return_date)} · {item.return_note}</p>
                        : <><VeraDateInput value={returnDrafts[item.id]?.return_date || ''} min={item.start_date} onChange={(event) => setReturnDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], return_date: event.target.value } }))} aria-label="Ngày quay lại làm việc"/><input value={returnDrafts[item.id]?.note || ''} onChange={(event) => setReturnDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], note: event.target.value } }))} placeholder="Ghi chú đã quay lại"/><button data-ui-key="u-ad93a1e80149" data-ui-label-default="Kết thúc kỳ nghỉ" type="button" className="secondary-button compact" disabled={returnBusyId === item.id} onClick={() => markReturned(item)}><UiCustomText uiKey="u-ad93a1e80149">Kết thúc kỳ nghỉ</UiCustomText></button></>}
                    </div>}
                  </article>
                  )
                })}
              </div>
            </>
          )}
        </section>
      )}
    </section>
  )
}

function DateField({ label, value, min, max, onChange }) {
  return (
    <label className="long-leave-date-field leave-date-input-group">
      <span>{label}</span>
      <VeraDateInput value={value} min={min} max={max} onChange={(event) => onChange(event.target.value)} required aria-label={label} />
    </label>
  )
}
