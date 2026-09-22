import { memo } from "react";
import UiToolbar from "../components/UiToolbar";
import UiCustomText from "../components/UiCustomText";
import { Download } from "lucide-react";
import { ClipboardCopy } from "lucide-react";
import LiveTourRevenueSummary from "../components/LiveTourRevenueSummary";
import { formatVeraDateTime } from "../lib/veraDate";
import { Printer } from "lucide-react";
function LiveTourReportsPanel({
  EXPORT_KINDS,
  actionBusy,
  asArray,
  canExportKind,
  canPaidInvoiceView,
  columns,
  copyBoardImage,
  customColumns,
  customScope,
  data,
  exportData,
  formatMoney,
  itemId,
  itemLabel,
  reportInvoiceCount,
  reports,
  setCustomColumns,
  setCustomScope,
  setReceipt
}) {
  return <div data-ui-key="u-78fd579b358b" className="live-tour-panel-body">
        <details className="live-tour-catalog-section">
          <summary>Xuất bảng tùy chỉnh</summary>
          <label>Phạm vi nhân viên<select value={customScope} onChange={event => setCustomScope(event.target.value)}><option value="displayed">Đang hiển thị</option><option value="selected">Đã chọn</option><option value="all">Tất cả</option></select></label>
          <UiToolbar data-ui-key="u-9fcd2124e9d0" className="live-tour-panel-toolbar-actions"><button data-ui-key="u-045c84dccf85" data-ui-label-default="Chọn tất cả cột" type="button" className="secondary-button" onClick={() => setCustomColumns(null)}><UiCustomText uiKey="u-045c84dccf85">Chọn tất cả cột</UiCustomText></button><button data-ui-key="u-6835ed3633b1" data-ui-label-default="Bỏ chọn cột" type="button" className="secondary-button" onClick={() => setCustomColumns([])}><UiCustomText uiKey="u-6835ed3633b1">Bỏ chọn cột</UiCustomText></button></UiToolbar>
          <div data-ui-key="u-709b75c050c4" className="live-tour-card-grid">{columns.map(column => <label key={column}><input type="checkbox" checked={(customColumns ?? columns).includes(column)} onChange={event => setCustomColumns(previous => event.target.checked ? columns.filter(item => item === column || (previous ?? columns).includes(item)) : (previous ?? columns).filter(item => item !== column))} />{column}</label>)}</div>
          <button data-ui-key="u-a4134718e40e" data-ui-label-default="Xuất Excel tùy chỉnh" type="button" className="secondary-button" disabled={!canExportKind('custom') || Boolean(actionBusy)} onClick={() => exportData('custom')}><Download size={13} /><UiCustomText uiKey="u-a4134718e40e"> Xuất Excel tùy chỉnh</UiCustomText></button>
          <p>Bộ lọc ngày/giờ báo cáo không áp dụng cho bảng tua hiện tại.</p>
        </details>
        <UiToolbar data-ui-key="u-9c36d2dbb4d9" className="live-tour-panel-toolbar"><h2>BÁO CÁO · DOANH THU · TIỀN TIP</h2><UiToolbar data-ui-key="u-c3776eda40b8" className="live-tour-panel-toolbar-actions">{EXPORT_KINDS.map(([kind, label]) => <button data-ui-key="u-25d830c3b45e" type="button" className="primary-button" disabled={!canExportKind(kind)} onClick={() => exportData(kind)} key={kind}><Download size={13} /> {label}</button>)}<button data-ui-key="u-7c09c9a51c17" data-ui-label-default="Copy B.Tua" type="button" className="primary-button live-tour-desktop-only" disabled={!canExportKind('board') || Boolean(actionBusy)} onClick={copyBoardImage}><ClipboardCopy size={13} /><UiCustomText uiKey="u-7c09c9a51c17"> Copy B.Tua</UiCustomText></button></UiToolbar></UiToolbar>
        <LiveTourRevenueSummary summary={data.report_totals} rows={reports} invoiceCount={reportInvoiceCount} />
        {!reports.length && <div className="live-tour-empty">Chưa có số liệu báo cáo.</div>}
        {reports.length > 0 && <div data-ui-key="u-dc15b1c36418" className="live-tour-card-grid">{reports.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{item?.employee_name || itemLabel(item, `Báo cáo ${index + 1}`)}</strong><span>{item?.service || 'Dịch vụ'} · {formatMoney(item?.total ?? item?.revenue ?? item?.amount)}</span><small>TIP: {formatMoney(item?.tip ?? 0)} · {formatVeraDateTime(item?.effective_at || item?.created_at)}</small>{canPaidInvoiceView && asArray(data.state?.invoices).some(invoice => invoice.id === item.invoice_id) && <button data-ui-key="u-fdc0ceae7323" data-ui-label-default="Xem / in hóa đơn" type="button" className="secondary-button" onClick={() => setReceipt({
          invoice: data.state.invoices.find(invoice => invoice.id === item.invoice_id),
          autoPrint: false
        })}><Printer size={14} /><UiCustomText uiKey="u-fdc0ceae7323"> Xem / in hóa đơn</UiCustomText></button>}</article>)}</div>}
      </div>;
}
export default memo(LiveTourReportsPanel);
