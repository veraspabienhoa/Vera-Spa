import { LoaderCircle, Power, Save, ShieldCheck } from 'lucide-react'

export default function LetanLeavePolicyRules({
  policy,
  canEdit = false,
  dirty = false,
  busy = false,
  onChange,
  onSave,
}) {
  const groups = policy?.groups || []

  const updateGroup = (groupIndex, field, value) => {
    onChange?.({
      ...policy,
      groups: groups.map((group, index) => index === groupIndex ? { ...group, [field]: value } : group),
    })
  }

  const updateReason = (groupIndex, reasonIndex, value) => {
    const group = groups[groupIndex]
    updateGroup(groupIndex, 'reasons', group.reasons.map((reason, index) => index === reasonIndex ? value : reason))
  }

  return (
    <section className="panel letan-leave-policy-panel">
      <style>{`
        .letan-leave-policy-panel{margin-top:16px}
        .letan-policy-note{display:grid;gap:5px;margin:10px 0 14px;padding:11px 13px;border:1px solid #d7e2dc;border-radius:12px;background:#f7faf8;color:#31483d;font-size:13px;line-height:1.45}
        .letan-policy-note strong{color:#173329}
        .letan-policy-table-wrap{width:100%;overflow-x:auto}
        .letan-policy-table{width:100%;border-collapse:collapse;table-layout:fixed}
        .letan-policy-table th,.letan-policy-table td{border-bottom:1px solid #e5ebe7;padding:10px 12px;text-align:left;vertical-align:top}
        .letan-policy-table th{font-size:12px;color:#52675e;background:#f7faf8}
        .letan-policy-table th:first-child,.letan-policy-table td:first-child{width:150px;text-align:center;font-weight:900;color:#173329}
        .letan-policy-table input{width:100%;box-sizing:border-box}
        .letan-policy-reasons{display:grid;gap:7px;margin:0;padding:0;list-style:none}
        .letan-policy-reasons li{display:grid;grid-template-columns:28px minmax(0,1fr);gap:7px;align-items:center;line-height:1.35}
        .letan-policy-reason-number{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:#eaf2ee;color:#315d4b;font-size:11px;font-weight:900}
        .letan-policy-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-top:14px}
        .letan-policy-actions-buttons{display:flex;gap:8px;flex-wrap:wrap}
        @media(max-width:640px){
          .letan-policy-table th:first-child,.letan-policy-table td:first-child{width:92px;padding-left:6px;padding-right:6px}
          .letan-policy-table th,.letan-policy-table td{font-size:11px;padding:8px}
          .letan-policy-reasons li{grid-template-columns:22px minmax(0,1fr)}
          .letan-policy-reason-number{width:20px;height:20px}
        }
      `}</style>
      <div className="panel-title-row">
        <div>
          <h2>QUYỀN SỬA / XÓA ĐĂNG KÝ – TÀI KHOẢN LỄ TÂN</h2>
          <p>Quy tắc hệ thống áp dụng bắt buộc cho tài khoản có vai trò Lễ tân khi nội quy đang kích hoạt.</p>
        </div>
        <span className={`weekend-unpaid-nth-state ${policy?.enabled ? 'enabled' : 'disabled'}`}>
          {policy?.enabled ? 'ĐANG KÍCH HOẠT' : 'ĐANG TẠM NGƯNG'}
        </span>
      </div>

      <div className="letan-policy-note">
        <span><strong>Trước ngày hiện tại:</strong> Lễ tân không được xóa hoặc sửa bất cứ đăng ký nào.</span>
        <span><strong>Ngày hiện tại – Nhóm 1 đến Nhóm 5:</strong> Lễ tân không được xóa; chỉ được đổi <strong>Lý do nghỉ</strong> sang một trong 3 lý do thuộc đúng cùng nhóm.</span>
        <span><strong>Ngày hiện tại – Lý do/Loại nghỉ khác:</strong> nếu Lễ tân được phép nhập theo Phân quyền + Nội quy thì vẫn được <strong>xóa, sửa và thay đổi</strong> theo quyền hiện hành.</span>
        <span><strong>Ngày tương lai:</strong> tiếp tục áp dụng Phân quyền và Bảng nội quy hiện hành.</span>
        {!policy?.enabled && <span><strong>Đang tạm ngưng:</strong> hệ thống quay lại áp dụng Phân quyền và các quy tắc đăng ký/hủy trong Bảng nội quy hiện hành.</span>}
      </div>

      <div className="letan-policy-table-wrap">
        <table className="letan-policy-table">
          <thead>
            <tr><th>Nhóm</th><th>Ba Lý do nghỉ được phép đổi qua lại trong đúng cùng nhóm</th></tr>
          </thead>
          <tbody>
            {groups.map((group, groupIndex) => (
              <tr key={group.id}>
                <td>{canEdit
                  ? <input value={group.name} onChange={(event) => updateGroup(groupIndex, 'name', event.target.value)} aria-label={`Tên ${group.name}`} />
                  : group.name}
                </td>
                <td>
                  <ul className="letan-policy-reasons">
                    {group.reasons.map((reason, reasonIndex) => <li key={`${group.id}-${reasonIndex}`}>
                      <span className="letan-policy-reason-number">{reasonIndex + 1}</span>
                      {canEdit
                        ? <input value={reason} onChange={(event) => updateReason(groupIndex, reasonIndex, event.target.value)} aria-label={`${group.name} lý do ${reasonIndex + 1}`} />
                        : <span>{reason}</span>}
                    </li>)}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="letan-policy-actions">
        <span><ShieldCheck size={15} /> Chỉ Admin được kích hoạt, tạm ngưng hoặc sửa năm nhóm nội quy này.</span>
        {canEdit && <div className="letan-policy-actions-buttons">
          <button type="button" className={policy?.enabled ? 'danger-button' : 'primary-button'} disabled={busy} onClick={() => onSave?.(!policy?.enabled)}>
            {busy ? <LoaderCircle size={17} className="spin" /> : <Power size={17} />}
            {policy?.enabled ? 'Tạm ngưng kích hoạt' : 'Kích hoạt nội quy'}
          </button>
          <button type="button" className="primary-button" disabled={!dirty || busy} onClick={() => onSave?.(policy?.enabled)}>
            {busy ? <LoaderCircle size={17} className="spin" /> : <Save size={17} />} Lưu sửa đổi nội quy
          </button>
        </div>}
      </div>
    </section>
  )
}
