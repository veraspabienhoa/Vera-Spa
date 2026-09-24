import './LiveTourServiceActions.css'

export default function LiveTourServiceActions({ target, room = false, waiting = 0, doing = 0, canStart = true, busy, disabledReason = '', onStart, onFinish }) {
  const scope = room ? `cả phòng ${target}` : target
  const reason = disabledReason || (busy ? 'Đang xử lý một thao tác Live Tour. Vui lòng chờ kết quả.' : '')
  return <div className={`live-tour-service-actions${room ? ' room-actions' : ''}`}>
    {canStart && waiting > 0 && <button data-ui-key="u-8d457a739a10" type="button" className="live-tour-start-button" disabled={busy} onClick={onStart}
      aria-label={`Thực hiện ${scope}`} title={reason || `Thực hiện ${scope} · ${waiting} nhân viên đang chờ`}>Thực hiện{room && <small>{waiting}</small>}</button>}
    {doing > 0 && <button data-ui-key="u-0cb8c4faaaf6" type="button" className="live-tour-finish-button" disabled={busy} onClick={onFinish}
      aria-label={`Hoàn thành ${scope}`} title={reason || `Hoàn thành ${scope} · ${doing} nhân viên đang thực hiện`}>Hoàn thành{room && <small>{doing}</small>}</button>}
  </div>
}
