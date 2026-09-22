import { memo } from "react";
import UiToolbar from "../components/UiToolbar";
import { Download } from "lucide-react";
import UiCustomText from "../components/UiCustomText";
import { bookingTimeLabel } from "../lib/liveTourCheckout";
import { Trash2 } from "lucide-react";
function LiveTourPendingPanel({
  actionBusy,
  asArray,
  canExportKind,
  canInvoiceDelete,
  canInvoiceEdit,
  canInvoiceView,
  canPayment,
  data,
  exportData,
  itemId,
  openModal,
  pendingPayments,
  setError,
  setPendingContext
}) {
  return <div data-ui-key="u-5aae89cf5f13" className="live-tour-panel-body" id="live-tour-pending-panel" role="tabpanel" aria-label="Hóa đơn chờ thanh toán">
        <UiToolbar data-ui-key="u-4ccbed71d695" className="live-tour-panel-toolbar"><h2>HÓA ĐƠN CHỜ THANH TOÁN <span className="live-tour-invoice-count" aria-label={`${pendingPayments.length} hóa đơn chờ thanh toán`}>{pendingPayments.length}</span></h2><UiToolbar data-ui-key="u-bc66c94c498e" className="live-tour-panel-toolbar-actions"><button data-ui-key="u-26b22989fcab" data-ui-label-default="Xuất chờ thanh toán" type="button" className="secondary-button" disabled={!canExportKind('pending')} onClick={() => exportData('pending')}><Download size={13} /><UiCustomText uiKey="u-26b22989fcab"> Xuất chờ thanh toán</UiCustomText></button></UiToolbar></UiToolbar>
        {pendingPayments.length ? <div data-ui-key="u-ee50e97f2347" className="live-tour-card-grid">{pendingPayments.map((item, index) => {
        const id = String(item?._id ?? item?.id ?? '');
        const entries = asArray(item?.entries);
        const cardEntries = entries.length ? entries : [{
          employee_name: item.employee_name,
          room: item.room,
          service: item.service || item.services,
          booked_at: item.booked_at,
          started_at: item.started_at
        }];
        return <article className="live-tour-data-card" key={itemId(item, index)}>
            {cardEntries.map((entry, entryIndex) => <strong key={entryIndex}>{entry.employee_name || 'Chưa có nhân viên'} – {entry.service || 'Chưa ghi dịch vụ'} – {entry.room || 'Chưa có phòng'}</strong>)}
            <small>{item?.customer_name || item?.customer || 'Khách lẻ'} {item?.customer_phone || item?.phone ? `· ${item?.customer_phone || item?.phone}` : ''}</small>
            {cardEntries.map((entry, entryIndex) => <small key={entryIndex}>Booking: {bookingTimeLabel(entry.booked_at || item.effective_at || item.booked_at || item.created_at)} · Thực hiện: {bookingTimeLabel(entry.started_at)}</small>)}
            <UiToolbar data-ui-key="u-5c381f1b69d9" className="live-tour-card-actions"><button data-ui-key="u-d3f310ed4bc5" data-ui-label-default="Thanh toán" type="button" className="primary-button" disabled={!canPayment || Boolean(actionBusy)} onClick={() => openModal('checkout', {
              item,
              rowIds: [],
              defaults: {
                pending_id: id
              }
            })}><UiCustomText uiKey="u-d3f310ed4bc5">Thanh toán</UiCustomText></button>
              {canInvoiceView && <button data-ui-key="u-7e13d63908b4" data-ui-label-default="Xem hóa đơn" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => {
              setError('');
              setPendingContext({
                item,
                mode: 'view',
                revision: data.revision
              });
            }}><UiCustomText uiKey="u-7e13d63908b4">Xem hóa đơn</UiCustomText></button>}
              {canInvoiceEdit && <button data-ui-key="u-b9839ff6697d" data-ui-label-default="Sửa hóa đơn" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => {
              setError('');
              setPendingContext({
                item,
                mode: 'edit',
                revision: data.revision
              });
            }}><UiCustomText uiKey="u-b9839ff6697d">Sửa hóa đơn</UiCustomText></button>}
              {canInvoiceDelete && <button data-ui-key="u-c9f44b19c631" data-ui-label-default="Xóa hóa đơn" type="button" className="secondary-button danger-button" disabled={Boolean(actionBusy)} onClick={() => {
              setError('');
              setPendingContext({
                item,
                mode: 'delete',
                revision: data.revision
              });
            }}><Trash2 size={14} /><UiCustomText uiKey="u-c9f44b19c631"> Xóa hóa đơn</UiCustomText></button>}
            </UiToolbar>
          </article>;
      })}</div> : <div className="live-tour-empty">{canInvoiceView ? 'Không có hóa đơn chờ thanh toán.' : `Có ${data.pending_count || 0} phiếu. Cần quyền Xem hóa đơn chờ thanh toán để mở chi tiết.`}</div>}
      </div>;
}
export default memo(LiveTourPendingPanel);
