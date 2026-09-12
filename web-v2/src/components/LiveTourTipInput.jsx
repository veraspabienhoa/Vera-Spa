import { useState } from 'react'
import { sortedTipCards } from '../lib/paymentPresentation'
import { defaultTipMode, money, tipCardLabel } from '../lib/liveTourCheckout'

export default function LiveTourTipInput({ form, setForm, cards, preferenceKey, total }) {
  const [preferred, setPreferred] = useState(() => defaultTipMode(preferenceKey))
  const [preferenceError, setPreferenceError] = useState('')
  const remember = (mode) => {
    try { window.localStorage.setItem(preferenceKey, mode); setPreferred(mode); setPreferenceError('') }
    catch { setPreferenceError('Không lưu được lựa chọn mặc định trên thiết bị này.') }
    setForm((current) => ({ ...current, tip_mode: mode }))
  }
  return <fieldset className="tour-tip-input wide"><legend>Cách nhận TIP</legend>
    {[['manual', 'Nhập tiền TIP'], ['cards', 'Chọn thẻ tiền TIP']].map(([mode, label]) => <div className="tour-tip-mode" key={mode}>
      <label><input type="checkbox" checked={form.tip_mode === mode} onChange={() => setForm((current) => ({ ...current, tip_mode: mode }))}/>{label}</label>
      <button type="button" className="secondary-button" aria-label={`Mặc định: ${label}`} aria-pressed={preferred === mode} onClick={() => remember(mode)}>{preferred === mode ? 'Mặc định' : 'Đặt mặc định'}</button>
    </div>)}
    {form.tip_mode === 'manual' ? <label className="live-tour-field tour-tip-amount"><span>Tiền TIP</span><input type="number" min="0" max="10000000000" step="1" value={form.tip} onChange={(event) => setForm((current) => ({ ...current, tip: event.target.value }))}/></label>
      : <div className="tour-tip-cards"><div className="tour-page-items-content">{sortedTipCards(cards).map((card) => <button type="button" className="secondary-button" key={card.id} disabled={form.tip_card_ids.length >= 30} onClick={() => setForm((current) => ({ ...current, tip_card_ids: [...current.tip_card_ids, card.id] }))}>+ {tipCardLabel(card)}</button>)}</div><div className="tour-tip-selected" aria-label="Thẻ TIP đã chọn">{form.tip_card_ids.map((id, index) => <button type="button" className="secondary-button" key={`${id}:${index}`} aria-label={`Bỏ thẻ TIP ${index + 1}`} onClick={() => setForm(current => ({ ...current, tip_card_ids: current.tip_card_ids.filter((_, position) => position !== index) }))}>{tipCardLabel(cards.find(card => card.id === id) || { amount: 0 })} ×</button>)}</div></div>}
    <p className="tour-tip-total">Tổng TIP: <strong>{money(total)}</strong></p>
    {preferenceError && <small role="alert">{preferenceError}</small>}
  </fieldset>
}
