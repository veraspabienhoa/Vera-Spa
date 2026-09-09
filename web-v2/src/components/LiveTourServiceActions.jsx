import './LiveTourServiceActions.css'

export default function LiveTourServiceActions({ target, room = false, waiting = 0, doing = 0, busy, onStart, onFinish }) {
  const scope = room ? `cả phòng ${target}` : target
  return <div className={`live-tour-service-actions${room ? ' room-actions' : ''}`}>
    <button type="button" className="live-tour-start-button" disabled={busy || !waiting} onClick={onStart}
      aria-label={`Thực hiện ${scope}`} title={`Thực hiện ${scope} · ${waiting} nhân viên đang chờ`}>Thực hiện{room && <small>{waiting}</small>}</button>
    <button type="button" className="live-tour-finish-button" disabled={busy || !doing} onClick={onFinish}
      aria-label={`Hoàn thành ${scope}`} title={`Hoàn thành ${scope} · ${doing} nhân viên đang thực hiện`}>Hoàn thành{room && <small>{doing}</small>}</button>
  </div>
}
