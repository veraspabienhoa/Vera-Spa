import { memo } from "react";
import UiToolbar from "../components/UiToolbar";
import { Plus } from "lucide-react";
import UiCustomText from "../components/UiCustomText";
import { Download } from "lucide-react";
import { Search } from "lucide-react";
import ClearableSearchInput from "../components/ClearableSearchInput";
import { bookingTimeLabel } from "../lib/liveTourCheckout";
import { History } from "lucide-react";
function LiveTourCustomersPanel({
  canCustomers,
  canExportKind,
  canImportCombo,
  canPayment,
  capabilities,
  customerComboPurchases,
  customerSearch,
  data,
  exportData,
  filteredCustomers,
  isAdmin,
  itemId,
  itemLabel,
  openCustomerHistory,
  openModal,
  setCustomerContext,
  setCustomerSearch,
  setError,
  stableCustomerId
}) {
  return <div data-ui-key="u-649716fc4d68" className="live-tour-panel-body">
        <UiToolbar data-ui-key="u-ae8ed624a03d" className="live-tour-panel-toolbar"><h2>KHÁCH HÀNG</h2><UiToolbar data-ui-key="u-ef65687e6300" className="live-tour-panel-toolbar-actions"><button data-ui-key="u-7aaa167545c1" data-ui-label-default="Mua combo cho khách hàng" type="button" className="primary-button" disabled={!canPayment} onClick={() => openModal('combo_purchase', {
          rowIds: []
        })}><Plus size={13} /><UiCustomText uiKey="u-7aaa167545c1"> Mua combo cho khách hàng</UiCustomText></button>{canImportCombo && <button data-ui-key="u-ab651dafd8bd" data-ui-label-default="Nhập combo" type="button" className="secondary-button" onClick={() => openModal('combo_import')}><UiCustomText uiKey="u-ab651dafd8bd">Nhập combo</UiCustomText></button>}<button data-ui-key="u-ef56fb891e1c" data-ui-label-default="Xuất khách hàng" type="button" className="secondary-button" disabled={!canExportKind('customers')} onClick={() => exportData('customers')}><Download size={13} /><UiCustomText uiKey="u-ef56fb891e1c"> Xuất khách hàng</UiCustomText></button></UiToolbar></UiToolbar>
        <label className="live-tour-customer-search"><Search size={14} /><ClearableSearchInput type="search" aria-label="Tìm tên hoặc số điện thoại khách hàng" autoComplete="off" value={customerSearch} onChange={event => setCustomerSearch(event.target.value)} placeholder="Tìm tên hoặc số điện thoại khách hàng…" /></label>
        <div data-ui-key="u-957d44b6b75e" className="live-tour-card-grid" style={{
      marginTop: 8
    }}>
          {filteredCustomers.map((customer, index) => <article className="live-tour-data-card live-tour-customer-card" role="button" tabIndex="0" aria-label={`Xem lịch sử ${itemLabel(customer, `Khách hàng ${index + 1}`)}`} onClick={event => {
        if (!event.target.closest('button')) void openCustomerHistory(customer);
      }} onKeyDown={event => {
        if (event.key === 'Enter' && !event.target.closest('button')) void openCustomerHistory(customer);
      }} key={itemId(customer, index)}>
            <strong>{itemLabel(customer, `Khách hàng ${index + 1}`)}</strong>
            <span>{customer?.phone || 'Chưa có số điện thoại'}</span>
            <small>Số dư combo: {customer?.combo_balance ?? customer?.remaining_tickets ?? customer?.balance ?? 0}</small>
            {customerComboPurchases(customer).map((combo, comboIndex) => <div key={itemId(combo, comboIndex)}><small>{itemLabel(combo)} · còn {combo?.remaining ?? combo?.balance ?? 0}/{combo?.total ?? ''} vé · mua {bookingTimeLabel(combo?.purchased_at || combo?.created_at)}</small>{isAdmin && capabilities.customer_combo_edit && <button data-ui-key="u-50ce352c9444" data-ui-label-default="Sửa combo" className="text-button" onClick={() => {
            setError('');
            setCustomerContext({
              customer,
              purchase: combo,
              mode: 'edit',
              revision: data.revision
            });
          }}><UiCustomText uiKey="u-50ce352c9444">Sửa combo</UiCustomText></button>}{capabilities.customer_combo_delete && <button data-ui-key="u-4205e0d3f38a" data-ui-label-default="Xóa combo" className="text-button" onClick={() => {
            setError('');
            setCustomerContext({
              customer,
              purchase: combo,
              mode: 'delete',
              revision: data.revision
            });
          }}><UiCustomText uiKey="u-4205e0d3f38a">Xóa combo</UiCustomText></button>}</div>)}
            <UiToolbar data-ui-key="u-77415787e4c3" className="live-tour-card-actions">{capabilities.customers_edit && <button data-ui-key="u-2df061d02fff" data-ui-label-default="Sửa khách hàng" className="secondary-button" onClick={() => {
            setError('');
            setCustomerContext({
              customer,
              mode: 'edit',
              revision: data.revision
            });
          }}><UiCustomText uiKey="u-2df061d02fff">Sửa khách hàng</UiCustomText></button>}{capabilities.customers_delete && <button data-ui-key="u-cd9355677b53" data-ui-label-default="Xóa khách hàng" className="secondary-button danger-button" onClick={() => {
            setError('');
            setCustomerContext({
              customer,
              mode: 'delete',
              revision: data.revision
            });
          }}><UiCustomText uiKey="u-cd9355677b53">Xóa khách hàng</UiCustomText></button>}</UiToolbar>
            <UiToolbar data-ui-key="u-be9313da7745" className="live-tour-card-actions"><button data-ui-key="u-91be5cd41cd8" data-ui-label-default="Lịch sử sử dụng" type="button" className="secondary-button" disabled={!canCustomers} onClick={() => openCustomerHistory(customer)}><History size={12} /><UiCustomText uiKey="u-91be5cd41cd8"> Lịch sử sử dụng</UiCustomText></button><button data-ui-key="u-c1b380bd08b6" data-ui-label-default="Mua combo" type="button" className="secondary-button" disabled={!canPayment} onClick={() => openModal('combo_purchase', {
            item: customer,
            rowIds: [],
            defaults: {
              customer_id: stableCustomerId(customer),
              customer_name: itemLabel(customer),
              phone: customer?.phone || customer?.customer_phone || ''
            }
          })}><Plus size={12} /><UiCustomText uiKey="u-c1b380bd08b6"> Mua combo</UiCustomText></button></UiToolbar>
          </article>)}
          {!filteredCustomers.length && <div className="live-tour-empty">Không tìm thấy khách hàng phù hợp.</div>}
        </div>
      </div>;
}
export default memo(LiveTourCustomersPanel);
