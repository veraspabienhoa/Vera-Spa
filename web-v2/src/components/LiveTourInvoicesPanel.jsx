import { memo } from "react";
import UiToolbar from "../components/UiToolbar";
import { formatVeraDateTime } from "../lib/veraDate";
import { Printer } from "lucide-react";
import UiCustomText from "../components/UiCustomText";
import { Trash2 } from "lucide-react";
function LiveTourInvoicesPanel({
  actionBusy,
  asArray,
  canPaidInvoiceDelete,
  canPaidInvoiceEdit,
  data,
  formatMoney,
  setError,
  setPendingContext,
  setReceipt,
  visibleInvoices,
  invoiceTotal = visibleInvoices.length,
  page = 1,
  pages = 1
}) {
  return <div data-ui-key="u-fc3f9e651c00" className="live-tour-panel-body">
        <UiToolbar data-ui-key="u-be7b585d85e7" className="live-tour-panel-toolbar"><h2>HÓA ĐƠN ĐÃ THANH TOÁN <span className="live-tour-invoice-count" aria-label={`${invoiceTotal} hóa đơn đã thanh toán theo bộ lọc`}>{invoiceTotal}</span></h2></UiToolbar>
        <p aria-live="polite">Đang hiển thị {visibleInvoices.length} / {invoiceTotal} hóa đơn theo bộ lọc · Trang {page}/{pages}.</p>
        <p>Hiển thị hóa đơn còn hiệu lực theo bộ lọc. Hủy hóa đơn được lưu đối soát, không xóa bản gốc và không tự hoàn tiền qua ngân hàng/thẻ.</p>
        <div data-ui-key="u-3f377cb8013a" className="live-tour-card-grid">{visibleInvoices.slice().reverse().map(invoice => <article className="live-tour-data-card" key={invoice.id}>
          {(asArray(invoice.entries).length ? invoice.entries : [{
          employee_name: invoice.employee_name,
          service: invoice.service || invoice.services,
          room: invoice.room
        }]).map((entry, entryIndex) => <strong key={entryIndex}>{entry.employee_name || 'Chưa có nhân viên'} – {entry.service || 'Chưa ghi dịch vụ'} – {entry.room || 'Chưa có phòng'}</strong>)}
          <small>{invoice.bill_no} · {invoice.customer_name || 'Khách lẻ'}</small><span>{formatVeraDateTime(invoice.effective_at || invoice.business_date)} · {invoice.payment_method}</span><strong>{formatMoney(invoice.total)}</strong>
          <UiToolbar data-ui-key="u-ec8f18a16bdd" className="live-tour-card-actions"><button data-ui-key="u-6b5193fbdb97" data-ui-label-default="Xem / in hóa đơn" type="button" className="secondary-button" onClick={() => setReceipt({
            invoice,
            autoPrint: false
          })}><Printer size={14} /><UiCustomText uiKey="u-6b5193fbdb97"> Xem / in hóa đơn</UiCustomText></button>
            {canPaidInvoiceEdit && <button data-ui-key="u-762a5f45f72c" data-ui-label-default="Sửa hóa đơn" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => {
            setError('');
            setPendingContext({
              item: invoice,
              paid: true,
              mode: 'edit',
              revision: data.revision
            });
          }}><UiCustomText uiKey="u-762a5f45f72c">Sửa hóa đơn</UiCustomText></button>}
            {canPaidInvoiceDelete && <button data-ui-key="u-3c72d15ad5c9" data-ui-label-default="Xóa / hủy hóa đơn" type="button" className="secondary-button danger-button" disabled={Boolean(actionBusy)} onClick={() => {
            setError('');
            setPendingContext({
              item: invoice,
              paid: true,
              mode: 'delete',
              revision: data.revision
            });
          }}><Trash2 size={14} /><UiCustomText uiKey="u-3c72d15ad5c9"> Xóa / hủy hóa đơn</UiCustomText></button>}
          </UiToolbar>
        </article>)}</div>
        {!visibleInvoices.length && <p>Chưa có hóa đơn đã thanh toán còn hiệu lực.</p>}
      </div>;
}
export default memo(LiveTourInvoicesPanel);
