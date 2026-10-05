import { useEffect, useState } from 'react'
import { Plus, Save, Trash2, LoaderCircle } from 'lucide-react'
import { veraApi } from '../lib/api'
import { numberInputDisplayValue } from '../lib/numberInput'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import usePageRefresh from '../lib/usePageRefresh'
import './DepartmentRulesPanel.css'

const departmentRuleLabels = { locker: 'Locker', letan: 'Lễ tân' }
export default function DepartmentRulesPanel() {
  const [data, setData] = useState(null)
  const [departmentRules, setDepartmentRules] = useState({ locker: [], letan: [] })
  const [departmentRulesOriginal, setDepartmentRulesOriginal] = useState({ locker: '[]', letan: '[]' })
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const canEditDepartmentRules = data?.can_edit_department_rules === true
  const departmentRulesDirty = department => JSON.stringify(departmentRules[department] || []) !== departmentRulesOriginal[department]
  const load = async () => {
    setBusy('load'); setError('')
    try {
      const result = await veraApi.rules()
      setData(result)
      const rows = Object.fromEntries(Object.keys(departmentRuleLabels).map(d => [d, (result.department_rules?.[d]?.rules || []).map(r => ({ ...r }))]))
      setDepartmentRules(rows)
      setDepartmentRulesOriginal(Object.fromEntries(Object.entries(rows).map(([d, rows]) => [d, JSON.stringify(rows)])))
    } catch (cause) { setError(cause.message || 'Không tải được nội quy bộ phận.') }
    finally { setBusy('') }
  }
  useEffect(() => { void load() }, [])
  usePageRefresh(load, () => Boolean(busy || Object.keys(departmentRuleLabels).some(departmentRulesDirty)))
  const updateDepartmentRule = (department, id, field, value) => {
    setDepartmentRules((current) => ({
      ...current,
      [department]: current[department].map((item) => item.id === id ? { ...item, [field]: value } : item),
    }))
  }

  const addDepartmentRule = (department) => {
    setDepartmentRules((current) => ({
      ...current,
      [department]: [...current[department], { id: crypto.randomUUID(), name: '', amount: 0, note: '', enabled: true }],
    }))
  }

  const removeDepartmentRule = (department, id) => {
    setDepartmentRules((current) => ({
      ...current,
      [department]: current[department].filter((item) => item.id !== id),
    }))
  }

  const saveDepartmentRules = async department => {
    setBusy(`department-${department}`); setError(''); setNotice('')
    try {
      await veraApi.saveDepartmentRules(department, { rules: departmentRules[department], expected_revision: Number(data?.department_rules?.[department]?.revision || 0) })
      const result = await veraApi.rules()
      setData(current => ({ ...current, department_rules: { ...current.department_rules, [department]: result.department_rules?.[department] } }))
      const saved = result.department_rules?.[department]?.rules || []
      setDepartmentRules(rows => ({ ...rows, [department]: saved }))
      setDepartmentRulesOriginal(rows => ({ ...rows, [department]: JSON.stringify(saved) }))
      setNotice(`Đã áp dụng nội quy ${departmentRuleLabels[department]}.`)
    } catch (cause) { setError(cause.message || 'Không áp dụng được nội quy.') }
    finally { setBusy('') }
  }
  return <>
    {error && <p className="error-box" role="alert">{error}</p>}
    {notice && <p className="success-box" role="status">{notice}</p>}
      <section data-ui-key="u-c044cb90c7c2" className="panel department-rules-panel">
        <div data-ui-key="u-6de79bf12a5d" className="panel-title-row">
          <div>
            <h2>NỘI QUY LOCKER / LỄ TÂN</h2>
            <p>Admin nhập nội dung và mức phạt tại đây. Khi bấm áp dụng, cùng cấu hình này được sử dụng trong hệ thống và bảng lương bộ phận.</p>
          </div>
        </div>
        <div className="department-rules-grid">{Object.entries(departmentRuleLabels).map(([department, label]) => {
          const rules = departmentRules[department] || []
          const ruleDirty = departmentRulesDirty(department)
          return <div data-ui-key="u-c91b62368f20" className="department-rules-card" key={department}>
            <div data-ui-key="u-2057f6a29fd5" className="department-rules-card-head"><h3>{label.toUpperCase()}</h3>{ruleDirty && <span className="rules-unsaved-chip">Chưa áp dụng</span>}</div>
            <div className="department-rules-list">{rules.map((rule) => <div className="department-rule-row" key={rule.id}>
              <input type="checkbox" checked={rule.enabled !== false} disabled={!canEditDepartmentRules || Boolean(busy)} onChange={(event) => updateDepartmentRule(department, rule.id, 'enabled', event.target.checked)} aria-label={`Áp dụng ${rule.name || label}`} />
              <input type="text" placeholder="Nội dung vi phạm" value={rule.name || ''} disabled={!canEditDepartmentRules || Boolean(busy)} onChange={(event) => updateDepartmentRule(department, rule.id, 'name', event.target.value)} />
              <input className="department-rule-amount" type="number" min="0" inputMode="numeric" placeholder="Mức phạt" value={numberInputDisplayValue(rule.amount)} disabled={!canEditDepartmentRules || Boolean(busy)} onChange={(event) => updateDepartmentRule(department, rule.id, 'amount', Number(event.target.value))} />
              <input className="department-rule-note" type="text" placeholder="Ghi chú" value={rule.note || ''} disabled={!canEditDepartmentRules || Boolean(busy)} onChange={(event) => updateDepartmentRule(department, rule.id, 'note', event.target.value)} />
              {canEditDepartmentRules && <button data-ui-key="u-cedb2f83521b" type="button" className="icon-button danger" disabled={Boolean(busy)} onClick={() => removeDepartmentRule(department, rule.id)} aria-label={`Xóa nội quy ${label}`}><Trash2 size={15} /></button>}
            </div>)}</div>
            {!rules.length && <div className="department-rules-empty">Chưa có nội dung phạt. Admin sẽ nhập sau.</div>}
            {canEditDepartmentRules && <UiToolbar data-ui-key="u-7a5b303285d8" className="department-rules-actions">
              <button data-ui-key="u-151d867779a2" data-ui-label-default="Thêm nội quy" type="button" className="secondary-button" disabled={Boolean(busy)} onClick={() => addDepartmentRule(department)}><Plus size={15} /><UiCustomText uiKey="u-151d867779a2"> Thêm nội quy</UiCustomText></button>
              <button data-ui-key="u-1fe5427e0433" type="button" className="primary-button" disabled={!ruleDirty || Boolean(busy)} onClick={() => saveDepartmentRules(department)}>{busy === `department-${department}` ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />} Áp dụng {label}</button>
            </UiToolbar>}
          </div>
        })}</div>
      </section>

  </>
}
