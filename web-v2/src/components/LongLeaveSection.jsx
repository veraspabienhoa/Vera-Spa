import { CalendarDays, CheckCircle2, Clock3, RefreshCw, Send, UserRoundCheck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { isApiConfigured, veraApi } from '../lib/api'
import VeraDateInput from './VeraDateInput'

const ANNUAL = 'Nghỉ Phép năm'
const LONG = 'Nghỉ làm đẹp'
const RESIGNATION = 'Nghỉ việc'

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
  return year && month && day ? `${day}/${month}/${year}` : '—'
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

export default function LongLeaveSection({ user }) {
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

  const load = useCallback(async () => {
    if (!canOpen || !isApiConfigured) return
    setLoading(true)
    try {
      const result = await veraApi.longLeaveOverview()
      setOverview(result)
      setNotice((current) => current?.status === 'success' ? current : null)
    } catch (error) {
      setNotice({ status: 'error', message: error.message || 'Không tải được dữ liệu Phép năm / Nghỉ làm đẹp.' })
    } finally {
      setLoading(false)
    }
  }, [canOpen])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (!canUseForm && canUseResignation) {
      setForm((current) => ({ ...current, request_type: RESIGNATION, end_date: current.start_date }))
    }
  }, [canUseForm, canUseResignation])

  const isAnnual = form.request_type === ANNUAL
  const isResignation = form.request_type === RESIGNATION
  const resignationMinDate = overview?.resignation_eligibility?.earliest_resignation_date || addDays(today(), 30)
  const annualMaxEnd = useMemo(() => addDays(form.start_date, 6), [form.start_date])
  const approvedRequests = overview?.approved_requests || []
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

  return (
    <section className="long-leave-section" aria-labelledby="long-leave-heading">
      <div className="long-leave-heading-row">
        <div>
          <span className="eyebrow"><CalendarDays size={14} /> Quy trình xin duyệt</span>
          <h2 id="long-leave-heading">PHÉP NĂM / NGHỈ LÀM ĐẸP / NGHỈ VIỆC</h2>
          <p>Đơn mới được chuyển vào quy trình duyệt hiện tại. Chỉ đơn Phép năm đã duyệt mới ghi vào lịch nghỉ hằng ngày.</p>
        </div>
        <button type="button" className="secondary-button compact" onClick={load} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'spin' : ''} /> Làm mới
        </button>
      </div>

      {notice && (
        <div className={`long-leave-notice ${notice.status}`} role={notice.status === 'error' ? 'alert' : 'status'}>
          {notice.status === 'success' ? <CheckCircle2 size={17} /> : <Clock3 size={17} />}
          <span>{notice.message}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Đóng thông báo">×</button>
        </div>
      )}

      {(canUseForm || canUseResignation) && (
        <section className="panel long-leave-form-panel">
          <div className="panel-title-row">
            <div>
              <h2>FORM MẪU ĐĂNG KÝ</h2>
              <p>Nhân viên gửi đơn cho chính tài khoản đang đăng nhập.</p>
            </div>
          </div>

          <div className="long-leave-type-tabs" role="group" aria-label="Chọn loại đơn">
            {[
              ...(canUseForm ? [ANNUAL, LONG] : []),
              ...(canUseResignation ? [RESIGNATION] : []),
            ].map((requestType) => (
              <button
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
          </div>

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

            <button type="submit" className="primary-button long-leave-submit" disabled={!canSubmit}>
              <Send size={16} /> {saving ? 'Đang gửi đơn…' : `Gửi đơn ${form.request_type}`}
            </button>
          </form>
        </section>
      )}

      {canViewApproved && (
        <section className="panel approved-leave-panel">
          <div className="panel-title-row">
            <div>
              <h2>DANH SÁCH NHÂN VIÊN ĐÃ ĐƯỢC DUYỆT</h2>
              <p>{approvedRequests.length} đơn Phép năm / Nghỉ làm đẹp ở trạng thái Đã duyệt.</p>
            </div>
            <div className="approved-count-chip"><UserRoundCheck size={15} /> {approvedRequests.length}</div>
          </div>

          {approvedRequests.length === 0 ? (
            <div className="setup-note">Chưa có nhân viên được duyệt.</div>
          ) : (
            <>
              <div className="approved-leave-desktop table-wrap">
                <table>
                  <thead><tr><th>Nhân viên</th><th>Loại đơn</th><th>Từ ngày</th><th>Đến ngày</th><th className="center">Số ngày</th><th>Nội dung</th><th>Chi tiết</th></tr></thead>
                  <tbody>
                    {approvedRequests.map((item) => (
                      <tr key={item.id}>
                        <td><strong>{shortEmployeeName(item.employee_name)}</strong></td>
                        <td><span className={`request-type-chip ${item.request_type === ANNUAL ? 'annual' : 'long'}`}>{item.request_type}</span></td>
                        <td>{formatDateDisplay(item.start_date)}</td>
                        <td>{formatDateDisplay(item.end_date)}</td>
                        <td className="center"><strong>{item.days}</strong></td>
                        <td>{item.reason || '—'}</td>
                        <td className="detail-cell">{item.detail || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="approved-leave-mobile-list">
                {approvedRequests.map((item) => (
                  <article className="approved-leave-mobile-card" key={item.id}>
                    <div className="approved-leave-mobile-head">
                      <div><strong>{shortEmployeeName(item.employee_name)}</strong><small>{item.id}</small></div>
                      <span className={`request-type-chip ${item.request_type === ANNUAL ? 'annual' : 'long'}`}>{item.request_type}</span>
                    </div>
                    <div className="approved-leave-mobile-period">
                      <span><small>Từ ngày</small><strong>{formatDateDisplay(item.start_date)}</strong></span>
                      <span><small>Đến ngày</small><strong>{formatDateDisplay(item.end_date)}</strong></span>
                      <span><small>Số ngày</small><strong>{item.days}</strong></span>
                    </div>
                    <p><strong>Nội dung:</strong> {item.reason || '—'}</p>
                    <p><strong>Chi tiết:</strong> {item.detail || '—'}</p>
                  </article>
                ))}
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
    <label className="long-leave-date-field">
      <span>{label}</span>
      <div className="long-leave-date-control">
        <span>{formatDateDisplay(value)}</span>
        <CalendarDays size={17} aria-hidden="true" />
        <VeraDateInput value={value} min={min} max={max} onChange={(event) => onChange(event.target.value)} required aria-label={label} />
      </div>
    </label>
  )
}
