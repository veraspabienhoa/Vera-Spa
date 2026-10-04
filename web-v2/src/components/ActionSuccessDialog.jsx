import { useId } from 'react'
import { CheckCircle2, X } from 'lucide-react'
import EmployeeProfileModal from './EmployeeProfileModal'
import './ActionSuccessDialog.css'

export default function ActionSuccessDialog({ message, onClose, title = 'Thao tác thành công' }) {
  const titleId = useId()
  if (!message) return null
  return <EmployeeProfileModal className="action-success-dialog" labelledBy={titleId} onClose={onClose}>
    <header><CheckCircle2 size={32} aria-hidden="true" /><h2 id={titleId}>{title}</h2>
      <button type="button" className="secondary-button" onClick={onClose} aria-label="Đóng thông báo"><X size={20} /></button>
    </header>
    <p role="status">{message}</p>
    <footer><button type="button" className="primary-button" onClick={onClose}>Đã hiểu</button></footer>
  </EmployeeProfileModal>
}
