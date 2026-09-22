import { memo } from "react";
import UiToolbar from "../components/UiToolbar";
import UiCustomText from "../components/UiCustomText";
import LiveTourPaymentSettings from "../components/LiveTourPaymentSettings";
import { Plus } from "lucide-react";
function LiveTourCatalogPanel({
  actionBusy,
  asArray,
  canAdmin,
  canManageCatalog,
  catalogRooms,
  combos,
  confirmExpired,
  data,
  executeAction,
  expiredGrace,
  expiredPreview,
  formatMoney,
  isVipRoom,
  itemId,
  itemLabel,
  openModal,
  previewExpired,
  removeCatalogItem,
  roomLabel,
  services,
  setExpiredGrace,
  setExpiredPreview
}) {
  return <div data-ui-key="u-c412dc5c7747" className="live-tour-panel-body">
        <UiToolbar data-ui-key="u-07b105a3b9d3" className="live-tour-panel-toolbar"><h2>DANH MỤC LIVE TOUR</h2></UiToolbar>
        {canAdmin && <div className="live-tour-catalog-section">
          <h3>Chuyển phiên quá hạn sang chờ thanh toán</h3>
          <label>Quá giờ dịch vụ ít nhất (phút)<input type="number" min="0" max="1440" step="1" value={expiredGrace} disabled={Boolean(actionBusy)} onChange={event => {
          setExpiredGrace(event.target.value);
          setExpiredPreview(null);
        }} /></label>
          <button data-ui-key="u-6e6911625b75" data-ui-label-default="Xem trước phiên quá hạn" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={previewExpired}><UiCustomText uiKey="u-6e6911625b75">Xem trước phiên quá hạn</UiCustomText></button>
          {expiredPreview && <div className="warning-box">
            <strong>{expiredPreview.count} phiên quá hạn từ {expiredPreview.grace_minutes} phút</strong>
            <p>Các phiên được chuyển sang chờ thanh toán; chưa ghi nhận thu tiền.</p>
            <div className="live-tour-history-list">{asArray(expiredPreview.employees).map(item => <article key={item.employee_id}><strong>{item.employee_name}</strong><span>{item.service} · Phòng {item.room}</span><small>Hết giờ: {item.ends_at}</small></article>)}</div>
            {expiredPreview.base_revision !== data.revision && <p>Bảng đã thay đổi. Hãy xem trước lại.</p>}
            <button data-ui-key="u-3eeac560ed56" type="button" className="primary-button" disabled={Boolean(actionBusy) || !expiredPreview.count || expiredPreview.base_revision !== data.revision} onClick={confirmExpired}>Xác nhận chuyển {expiredPreview.count} phiên</button>
            <button data-ui-key="u-00594babb6dd" data-ui-label-default="Hủy" type="button" className="secondary-button" disabled={Boolean(actionBusy)} onClick={() => setExpiredPreview(null)}><UiCustomText uiKey="u-00594babb6dd">Hủy</UiCustomText></button>
          </div>}
        </div>}
        {!canManageCatalog && <div className="live-tour-empty">Chỉ Admin hoặc tài khoản được cấp quyền mới được sửa danh mục.</div>}
        {canAdmin && <LiveTourPaymentSettings key={JSON.stringify(data.payment_settings)} value={data.payment_settings} busy={Boolean(actionBusy)} onSave={payload => executeAction('payment_settings_update', payload, [])} />}
        {canManageCatalog && <>
          <div className="live-tour-catalog-section"><UiToolbar data-ui-key="u-d9d3789a8ef4" className="live-tour-panel-toolbar"><h3>Phòng / giường</h3><button data-ui-key="u-ce823dd69517" data-ui-label-default="Thêm phòng" type="button" className="secondary-button" onClick={() => openModal('room_upsert')}><Plus size={12} /><UiCustomText uiKey="u-ce823dd69517"> Thêm phòng</UiCustomText></button></UiToolbar><div data-ui-key="u-30db9a0dfabf" className="live-tour-card-grid">{catalogRooms.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{roomLabel(item)}</strong><small>{isVipRoom(item) ? 'VIP' : 'Standard'}</small><UiToolbar data-ui-key="u-f31c06ec5c21" className="live-tour-card-actions"><button data-ui-key="u-de2a37e5a5c1" data-ui-label-default="Sửa" type="button" className="secondary-button" onClick={() => openModal('room_upsert', {
                item
              })}><UiCustomText uiKey="u-de2a37e5a5c1">Sửa</UiCustomText></button><button data-ui-key="u-36871ed520b8" data-ui-label-default="Xóa" type="button" className="secondary-button danger-button" onClick={() => removeCatalogItem('room_delete', item)}><UiCustomText uiKey="u-36871ed520b8">Xóa</UiCustomText></button></UiToolbar></article>)}</div></div>
          <div className="live-tour-catalog-section"><UiToolbar data-ui-key="u-70b2ade51fb2" className="live-tour-panel-toolbar"><h3>Dịch vụ</h3><button data-ui-key="u-67dbc64dfa55" data-ui-label-default="Thêm dịch vụ" type="button" className="secondary-button" onClick={() => openModal('service_upsert')}><Plus size={12} /><UiCustomText uiKey="u-67dbc64dfa55"> Thêm dịch vụ</UiCustomText></button></UiToolbar>{services.length ? <div data-ui-key="u-ad9c4a0dfba6" className="live-tour-card-grid">{services.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{itemLabel(item)}</strong><span>{item?.duration ?? item?.minutes ?? 0} phút · {formatMoney(item?.price ?? item?.amount ?? 0)}</span><UiToolbar data-ui-key="u-927e28a1d633" className="live-tour-card-actions"><button data-ui-key="u-661481c5beff" data-ui-label-default="Sửa" type="button" className="secondary-button" onClick={() => openModal('service_upsert', {
                item
              })}><UiCustomText uiKey="u-661481c5beff">Sửa</UiCustomText></button><button data-ui-key="u-07a2c7cd4a22" data-ui-label-default="Xóa" type="button" className="secondary-button danger-button" onClick={() => removeCatalogItem('service_delete', item)}><UiCustomText uiKey="u-07a2c7cd4a22">Xóa</UiCustomText></button></UiToolbar></article>)}</div> : <div className="live-tour-empty">Chưa có dịch vụ.</div>}</div>
          <div className="live-tour-catalog-section"><UiToolbar data-ui-key="u-9ced5b68f52c" className="live-tour-panel-toolbar"><h3>Combo</h3><button data-ui-key="u-86d6070de0aa" data-ui-label-default="Thêm combo" type="button" className="secondary-button" onClick={() => openModal('combo_upsert')}><Plus size={12} /><UiCustomText uiKey="u-86d6070de0aa"> Thêm combo</UiCustomText></button></UiToolbar>{combos.length ? <div data-ui-key="u-5b550ecfc1ea" className="live-tour-card-grid">{combos.map((item, index) => <article className="live-tour-data-card" key={itemId(item, index)}><strong>{itemLabel(item)}</strong><span>{item?.quantity ?? item?.tickets ?? 0} lượt · {formatMoney(item?.price ?? item?.amount ?? 0)}</span>{item.requires_admin_approval === true && <small>Admin duyệt bán</small>}<UiToolbar data-ui-key="u-9fcb9f514a8e" className="live-tour-card-actions"><button data-ui-key="u-83b8b20fc4ed" data-ui-label-default="Sửa" type="button" className="secondary-button" onClick={() => openModal('combo_upsert', {
                item
              })}><UiCustomText uiKey="u-83b8b20fc4ed">Sửa</UiCustomText></button><button data-ui-key="u-7dc6d1f7e697" data-ui-label-default="Xóa" type="button" className="secondary-button danger-button" onClick={() => removeCatalogItem('combo_delete', item)}><UiCustomText uiKey="u-7dc6d1f7e697">Xóa</UiCustomText></button></UiToolbar></article>)}</div> : <div className="live-tour-empty">Chưa có combo.</div>}</div>
        </>}
      </div>;
}
export default memo(LiveTourCatalogPanel);
