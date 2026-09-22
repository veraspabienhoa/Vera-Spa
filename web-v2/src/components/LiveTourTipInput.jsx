import { useState } from 'react'
import { sortedTipCards } from '../lib/paymentPresentation'
import { defaultTipMode, money, tipCardLabel } from '../lib/liveTourCheckout'
import VeraMoneyInput from './VeraMoneyInput'

export default function LiveTourTipInput({ form, setForm, cards, preferenceKey, total }) {
  const [preferred, setPreferred] = useState(() => defaultTipMode(preferenceKey))
  const [preferenceError, setPreferenceError] = useState('')
  const selectedCardIds = Array.isArray(form.tip_card_ids) ? form.tip_card_ids : []
  const selectedCount = (cardId) => selectedCardIds.reduce((count, id) => count + (id === cardId ? 1 : 0), 0)
  const addTipCard = (cardId) => setForm((current) => {
    const currentIds = Array.isArray(current.tip_card_ids) ? current.tip_card_ids : []
    if (currentIds.length >= 30) return current
    return { ...current, tip_card_ids: [...currentIds, cardId] }
  })
  const remember = (mode) => {
    try { window.localStorage.setItem(preferenceKey, mode); setPreferred(mode); setPreferenceError('') }
    catch { setPreferenceError('Không lưu được lựa chọn mặc định trên thiết bị này.') }
    setForm((current) => ({ ...current, tip_mode: mode }))
  }
  return <fieldset className="tour-tip-input wide"><legend>Cách nhận TIP</legend>
    {[['manual', 'Nhập tiền TIP'], ['cards', 'Chọn thẻ tiền TIP']].map(([mode, label]) => <div className="tour-tip-mode" key={mode}>
      <label><input type="checkbox" checked={form.tip_mode === mode} onChange={() => setForm((current) => ({ ...current, tip_mode: mode }))}/>{label}</label>
      <button data-ui-key="u-9a86a98bcbfa" type="button" className="secondary-button" aria-label={`Mặc định: ${label}`} aria-pressed={preferred === mode} onClick={() => remember(mode)}>{preferred === mode ? 'Mặc định' : 'Đặt mặc định'}</button>
    </div>)}
    {form.tip_mode === 'manual' ? <label className="live-tour-field tour-tip-amount"><span>Tiền TIP</span><VeraMoneyInput max="10000000000" value={form.tip} onChange={(event) => setForm((current) => ({ ...current, tip: event.target.value }))}/></label>
      : <div data-ui-key="u-6570b853992a" className="tour-tip-cards"><div className="tour-page-items-content">{sortedTipCards(cards).map((card) => {
        const count = selectedCount(card.id)
        const label = tipCardLabel(card)
        return <button data-ui-key="u-06a89203e206" type="button" className="secondary-button" key={card.id} disabled={selectedCardIds.length >= 30} aria-label={`Thêm thẻ TIP ${label}${count ? `; đã chọn ${count} lần` : ''}`} onClick={() => addTipCard(card.id)}>+ {label}{count > 0 && <span className="tour-tip-card-count">×{count}</span>}</button>
      })}</div><div className="tour-tip-selected" aria-label="Thẻ TIP đã chọn">{selectedCardIds.map((id, index) => <button data-ui-key="u-cbef13f101eb" type="button" className="secondary-button" key={`${id}:${index}`} aria-label={`Bỏ thẻ TIP ${index + 1}`} onClick={() => setForm(current => ({ ...current, tip_card_ids: (Array.isArray(current.tip_card_ids) ? current.tip_card_ids : []).filter((_, position) => position !== index) }))}>{tipCardLabel(cards.find(card => card.id === id) || { amount: 0 })} ×</button>)}</div></div>}
    <p className="tour-tip-total">Tổng TIP: <strong>{money(total)}</strong></p>
    {preferenceError && <small role="alert">{preferenceError}</small>}
  </fieldset>
}
