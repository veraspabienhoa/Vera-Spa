import { memo } from "react";
import { formatVeraDateTime } from "../lib/veraDate";
import LiveTourInvoiceChanges from "../components/LiveTourInvoiceChanges";
import UiToolbar from "../components/UiToolbar";
import { Download } from "lucide-react";
import UiCustomText from "../components/UiCustomText";
import { History } from "lucide-react";
function LiveTourHistoryPanel({
  actionBusy,
  backups,
  canBackup,
  canCustomers,
  canExportKind,
  canHistory,
  executeAction,
  exportData,
  filteredBreakEvents,
  filteredCustomerChanges,
  filteredInvoiceChanges,
  itemId,
  itemLabel
}) {
  return <div data-ui-key="u-65e23a4355d1" className="live-tour-panel-body">
        {canHistory && canCustomers && filteredCustomerChanges.length > 0 && <div className="live-tour-catalog-section"><h3>Lịch sử sửa / xóa khách hàng và combo</h3>{filteredCustomerChanges.slice().reverse().map(change => <details className="live-tour-data-card" key={change.id}><summary>{formatVeraDateTime(change.at)} · {change.actor} · {change.before?.name || change.before?.combo_name}</summary><p>Lý do: {change.reason}</p><p>{change.before?.remaining != null ? `Số vé: ${change.before.remaining} → ${change.after?.deleted_at ? 'Đã xóa' : change.after?.remaining}` : `${change.before?.name} → ${change.after?.deleted_at ? 'Đã xóa' : change.after?.name}`}</p></details>)}</div>}
        {canHistory && <LiveTourInvoiceChanges changes={filteredInvoiceChanges} />}
        {canHistory && <div className="live-tour-catalog-section">
          <UiToolbar data-ui-key="u-110ca1e95d1c" className="live-tour-panel-toolbar"><h3>LỊCH SỬ NGHỈ GIỮA CA</h3><button data-ui-key="u-79ff49120d1a" data-ui-label-default="Xuất nghỉ giữa ca" type="button" className="secondary-button" disabled={!canExportKind('breaks')} onClick={() => exportData('breaks')}><Download size={13} /><UiCustomText uiKey="u-79ff49120d1a"> Xuất nghỉ giữa ca</UiCustomText></button></UiToolbar>
          <div className="live-tour-history-list">{filteredBreakEvents.slice().reverse().map((event, index) => <article key={event.id || index}>
            <strong>{event.employee_name} · {event.event_type === 'start' ? 'Bắt đầu nghỉ' : 'Vào lại'}</strong>
            <span>{formatVeraDateTime(event.at)} · {event.outcome || 'Định mức 90 phút'}{event.minutes != null ? ` · ${event.minutes} phút` : ''}</span>
            <small>{event.actor}</small>
          </article>)}{!filteredBreakEvents.length && <div className="live-tour-empty">Chưa có lịch sử nghỉ giữa ca trong bộ lọc.</div>}</div>
        </div>}
        <UiToolbar data-ui-key="u-9f2705675a28" className="live-tour-panel-toolbar"><h2>LỊCH SỬ & SAO LƯU</h2><UiToolbar data-ui-key="u-dde9e54568c0" className="live-tour-panel-toolbar-actions">{canBackup && <button data-ui-key="u-7bc66b66d171" data-ui-label-default="Tạo bản sao lưu" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => executeAction('backup', {
          name: `Backup ${formatVeraDateTime(Date.now())}`
        }, [])}><History size={13} /><UiCustomText uiKey="u-7bc66b66d171"> Tạo bản sao lưu</UiCustomText></button>}{canHistory && <button data-ui-key="u-24479c9977be" data-ui-label-default="Xuất lịch sử" type="button" className="secondary-button" disabled={!canExportKind('history')} onClick={() => exportData('history')}><Download size={13} /><UiCustomText uiKey="u-24479c9977be"> Xuất lịch sử</UiCustomText></button>}</UiToolbar></UiToolbar>
        {canBackup && <div className="live-tour-catalog-section"><h3>Bản sao lưu</h3>{backups.length ? <div data-ui-key="u-334b0dee496c" className="live-tour-card-grid">{backups.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{itemLabel(item, `Bản sao ${index + 1}`)}</strong><small>{formatVeraDateTime(item?.created_at || item?.timestamp)}</small><UiToolbar data-ui-key="u-e9f0d291335d" className="live-tour-card-actions"><button data-ui-key="u-dacfd97fd33b" data-ui-label-default="Khôi phục" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => {
              if (window.confirm('Khôi phục bản sao này? Chỉ phục hồi cấu hình/bảng tua khi không còn phiên mở; sổ hóa đơn, vé và lịch sử không bị quay lùi.')) void executeAction('restore', {
                backup_id: item?._id ?? item?.id
              }, []);
            }}><UiCustomText uiKey="u-dacfd97fd33b">Khôi phục</UiCustomText></button></UiToolbar></article>)}</div> : <div className="live-tour-empty">Chưa có bản sao lưu.</div>}</div>}
      </div>;
}
export default memo(LiveTourHistoryPanel);
