from pathlib import Path

backend_path = Path('vera_web_v2_revenue_leave_list.py')
backend = backend_path.read_text(encoding='utf-8')

old_model = "class RevenueTipUpdate(BaseModel):\n    amount: float = Field(ge=0, le=10_000_000_000_000)\n"
new_model = "class RevenueTipUpdate(BaseModel):\n    amount: float = Field(ge=0, le=10_000_000_000_000)\n    start_date: date | None = None\n    end_date: date | None = None\n"
if old_model in backend:
    backend = backend.replace(old_model, new_model, 1)
elif new_model not in backend:
    raise SystemExit('RevenueTipUpdate marker not found')

start = backend.find('def _period_tip(')
end = backend.find('def _read_public_revenue_values()', start)
if start < 0 or end < 0:
    raise SystemExit('TIP helper block not found')
helper_block = '''def _period_tip(conn, default_start_date_text: str = "", default_end_date_text: str = "") -> dict[str, Any]:
    payload = conn.execute(text("""
        SELECT value_json
        FROM vera_app_setting
        WHERE category='revenue' AND setting_key=:key
        LIMIT 1
    """), {"key": REVENUE_TIP_SETTING}).scalar_one_or_none()
    if not isinstance(payload, dict):
        payload = {}
    return {
        "amount": max(0.0, _money(payload.get("amount", 0))),
        "period_start": str(payload.get("period_start") or default_start_date_text or ""),
        "period_end": str(payload.get("period_end") or default_end_date_text or ""),
    }


def _save_period_tip(conn, start_date_text: str, end_date_text: str, amount: float, actor: str) -> None:
    payload = {
        "period_start": str(start_date_text or ""),
        "period_end": str(end_date_text or ""),
        "amount": round(max(0.0, float(amount)), 2),
    }
    conn.execute(text("""
        INSERT INTO vera_app_setting(
            category, setting_key, value_json, source, updated_by,
            revision, created_at, updated_at
        ) VALUES (
            'revenue', :key, CAST(:payload AS jsonb), 'web_v2', :actor,
            1, NOW(), NOW()
        )
        ON CONFLICT(category, setting_key) DO UPDATE SET
            value_json=EXCLUDED.value_json,
            source='web_v2',
            updated_by=EXCLUDED.updated_by,
            revision=vera_app_setting.revision+1,
            updated_at=NOW()
    """), {
        "key": REVENUE_TIP_SETTING,
        "payload": json.dumps(payload, ensure_ascii=False),
        "actor": str(actor or ""),
    })


'''
backend = backend[:start] + helper_block + backend[end:]

old_summary = '''        with engine_instance().connect() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            tip = _period_tip(conn, summary.get("start_date", ""))
            can_edit_tip = bool(feature_allowed(conn, ident, REVENUE_TIP_FEATURE))
        summary["period_tip"] = round(tip, 2)
        summary["balance"] = round(summary["total_income"] - summary["total_expense"] - tip, 2)
'''
new_summary = '''        with engine_instance().connect() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            tip_setting = _period_tip(conn, summary.get("start_date", ""), summary.get("current_date", ""))
            can_edit_tip = bool(feature_allowed(conn, ident, REVENUE_TIP_FEATURE))
        tip = float(tip_setting["amount"])
        summary["period_tip"] = round(tip, 2)
        summary["period_tip_start"] = tip_setting["period_start"]
        summary["period_tip_end"] = tip_setting["period_end"]
        summary["balance"] = round(summary["total_income"] - summary["total_expense"] - tip, 2)
'''
if old_summary in backend:
    backend = backend.replace(old_summary, new_summary, 1)
elif new_summary not in backend:
    raise SystemExit('Revenue summary TIP block not found')

route_start = backend.find('    @app.put("/v2/revenue/tip")')
route_end = backend.find('    @app.get("/v2/leave/records")', route_start)
if route_start < 0 or route_end < 0:
    raise SystemExit('Revenue TIP route block not found')
save_route = '''    @app.put("/v2/revenue/tip")
    def save_revenue_tip(body: RevenueTipUpdate, ident=Depends(current_identity)):
        values = _read_revenue_values(google_client)
        period_start = _revenue_period_start(norm, values)
        summary = _revenue_summary(values, norm, period_start=period_start)
        summary.update(_report_totals(_read_revenue_report_values(google_client)))
        default_start = str(summary.get("start_date") or "")
        default_end = str(summary.get("current_date") or "")
        tip_start = body.start_date.isoformat() if body.start_date else default_start
        tip_end = body.end_date.isoformat() if body.end_date else default_end
        if not tip_start or not tip_end:
            raise HTTPException(409, "Chọn đủ Ngày bắt đầu và Đến ngày cho Tiền TIP trong kỳ.")
        if tip_start > tip_end:
            raise HTTPException(400, "Ngày bắt đầu Tiền TIP không được sau Đến ngày.")
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_TIP_FEATURE)
            _save_period_tip(conn, tip_start, tip_end, body.amount, getattr(ident, "employee_username", ""))
        tip = round(float(body.amount), 2)
        balance = round(summary["total_income"] - summary["total_expense"] - tip, 2)
        return {
            "ok": True,
            "release": RELEASE,
            "period_tip": tip,
            "balance": balance,
            "period_tip_start": tip_start,
            "period_tip_end": tip_end,
            "period_start": tip_start,
            "period_end": tip_end,
            "message": f"Đã lưu Tiền TIP trong kỳ {tip_start} đến {tip_end}: {round(tip):,}đ.".replace(",", "."),
        }

'''
backend = backend[:route_start] + save_route + backend[route_end:]
backend_path.write_text(backend, encoding='utf-8')

frontend_path = Path('web-v2/src/pages/RevenuePage.jsx')
front = frontend_path.read_text(encoding='utf-8')
old_save = '''async function savePeriodTip(amount) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}/v2/revenue/tip`, {
    method: 'PUT',
    headers: await authorizedHeaders(true),
    body: JSON.stringify({ amount: Number(amount || 0) }),
  })'''
new_save = '''async function savePeriodTip(amount, startDate, endDate) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const response = await fetch(`${apiBase}/v2/revenue/tip`, {
    method: 'PUT',
    headers: await authorizedHeaders(true),
    body: JSON.stringify({ amount: Number(amount || 0), start_date: startDate || null, end_date: endDate || null }),
  })'''
if old_save in front:
    front = front.replace(old_save, new_save, 1)
elif new_save not in front:
    raise SystemExit('savePeriodTip marker not found')

state_marker = "  const [tip, setTip] = useState(0)\n"
state_insert = "  const [tipStart, setTipStart] = useState('')\n  const [tipEnd, setTipEnd] = useState('')\n"
if state_insert not in front:
    if state_marker not in front:
        raise SystemExit('TIP state marker not found')
    front = front.replace(state_marker, state_marker + state_insert, 1)

old_load = '''          setData(result)
          setTip(Number(result.period_tip || 0))'''
new_load = '''          setData(result)
          setTip(Number(result.period_tip || 0))
          setTipStart(result.period_tip_start || result.start_date || '')
          setTipEnd(result.period_tip_end || result.current_date || '')'''
if old_load in front:
    front = front.replace(old_load, new_load, 1)
elif new_load not in front:
    raise SystemExit('Revenue load TIP marker not found')

old_submit = '''      if (!Number.isFinite(Number(tip)) || Number(tip) < 0) throw new Error('Tiền TIP trong kỳ phải là số không âm.')
      const result = await savePeriodTip(tip)
      setData((current) => current ? ({ ...current, period_tip: result.period_tip, balance: result.balance }) : current)
      setTip(Number(result.period_tip || 0))
      setNotice(result.message || 'Đã lưu Tiền TIP trong kỳ.')'''
new_submit = '''      if (!Number.isFinite(Number(tip)) || Number(tip) < 0) throw new Error('Tiền TIP trong kỳ phải là số không âm.')
      if (!tipStart || !tipEnd) throw new Error('Chọn đủ Ngày bắt đầu và Đến ngày cho Tiền TIP trong kỳ.')
      if (tipStart > tipEnd) throw new Error('Ngày bắt đầu Tiền TIP không được sau Đến ngày.')
      const result = await savePeriodTip(tip, tipStart, tipEnd)
      setData((current) => current ? ({ ...current, period_tip: result.period_tip, balance: result.balance, period_tip_start: result.period_tip_start, period_tip_end: result.period_tip_end }) : current)
      setTip(Number(result.period_tip || 0))
      setTipStart(result.period_tip_start || tipStart)
      setTipEnd(result.period_tip_end || tipEnd)
      setNotice(result.message || 'Đã lưu Tiền TIP trong kỳ.')'''
if old_submit in front:
    front = front.replace(old_submit, new_submit, 1)
elif new_submit not in front:
    raise SystemExit('TIP submit block not found')

old_css = ".revenue-tip-editor{display:grid;grid-template-columns:minmax(220px,380px) auto 1fr;gap:10px;align-items:end;margin-bottom:14px;padding:14px;border:1px solid #dfd5b9;border-radius:15px;background:#fffaf0}.revenue-tip-editor label{display:grid;gap:5px;font-size:12px;font-weight:900}.revenue-tip-editor input{font-size:18px;font-weight:800;text-align:right}.revenue-tip-editor small{color:#75694d;line-height:1.45}"
new_css = ".revenue-tip-editor{display:grid;grid-template-columns:minmax(180px,1.2fr) minmax(150px,.8fr) minmax(150px,.8fr) auto;gap:10px;align-items:end;margin-bottom:14px;padding:14px;border:1px solid #dfd5b9;border-radius:15px;background:#fffaf0}.revenue-tip-editor label{display:grid;gap:5px;font-size:12px;font-weight:900}.revenue-tip-editor input{font-size:16px;font-weight:800}.revenue-tip-editor .revenue-tip-amount input{text-align:right;font-size:18px}.revenue-tip-editor small{grid-column:1/-1;color:#75694d;line-height:1.45}.revenue-tip-current{display:flex;align-items:center;gap:6px;font-size:11px;color:#75694d;margin-top:4px}.revenue-tip-current button{min-height:30px;padding:4px 8px;font-size:11px}"
if old_css in front:
    front = front.replace(old_css, new_css, 1)
elif new_css not in front:
    raise SystemExit('TIP editor CSS marker not found')

old_editor = '''    {canEditTip && <section className="revenue-tip-editor">
      <label>TIỀN TIP TRONG KỲ<input type="number" min="0" step="1000" inputMode="numeric" value={numberInputDisplayValue(tip)} disabled={savingTip} onChange={(event) => setTip(event.target.value)} /></label>
      <button type="button" className="primary-button" onClick={submitTip} disabled={savingTip || busy}><Save size={16}/> {savingTip ? 'Đang lưu…' : 'Lưu Tiền TIP'}</button>
      <small>Số tiền này được lưu theo kỳ Doanh thu hiện tại. Công thức Còn lại sẽ trừ Tiền TIP trong kỳ ngay sau khi lưu.</small>
    </section>}'''
new_editor = '''    {canEditTip && <section className="revenue-tip-editor">
      <label className="revenue-tip-amount">TIỀN TIP TRONG KỲ<input type="number" min="0" step="1000" inputMode="numeric" value={numberInputDisplayValue(tip)} disabled={savingTip} onChange={(event) => setTip(event.target.value)} /></label>
      <label>Ngày bắt đầu<VeraDateInput aria-label="Ngày bắt đầu Tiền TIP" value={tipStart} disabled={savingTip} onChange={(event) => setTipStart(event.target.value)} /></label>
      <label>Đến ngày<VeraDateInput aria-label="Đến ngày Tiền TIP" value={tipEnd} disabled={savingTip} onChange={(event) => setTipEnd(event.target.value)} /><span className="revenue-tip-current">Ngày hiện tại: {data?.current_date_label || '—'} <button type="button" className="secondary-button" disabled={savingTip || !data?.current_date} onClick={() => setTipEnd(data?.current_date || '')}>Dùng ngày hiện tại</button></span></label>
      <button type="button" className="primary-button" onClick={submitTip} disabled={savingTip || busy}><Save size={16}/> {savingTip ? 'Đang lưu…' : 'Lưu Tiền TIP'}</button>
      <small>Tiền TIP được lưu cho khoảng từ Ngày bắt đầu đến Đến ngày. Đến ngày mặc định theo Ngày hiện tại của dữ liệu (ví dụ 13/09/2026) và vẫn có thể nhập tay. Công thức Còn lại trừ Tiền TIP ngay sau khi lưu.</small>
    </section>}'''
if old_editor in front:
    front = front.replace(old_editor, new_editor, 1)
elif new_editor not in front:
    raise SystemExit('TIP editor JSX marker not found')

frontend_path.write_text(front, encoding='utf-8')

assert 'start_date: date | None = None' in backend
assert 'end_date: date | None = None' in backend
assert 'summary["period_tip_start"]' in backend and 'summary["period_tip_end"]' in backend
assert '_save_period_tip(conn, tip_start, tip_end' in backend
assert 'setTipStart(result.period_tip_start' in front
assert 'Dùng ngày hiện tại' in front
assert 'savePeriodTip(tip, tipStart, tipEnd)' in front
print('REVENUE_TIP_PERIOD_RANGE=OK')