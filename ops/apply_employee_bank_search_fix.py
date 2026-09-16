#!/usr/bin/env python3
from pathlib import Path


def once(path, old, new, label):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')

# 1) VietQR: always resolve to the compact code users expect (VCB/ACB/TCB...).
once('vera_vietqr_bank.py',
'''            short = str(item.get("shortName") or "").strip()\n            code = short or str(item.get("code") or "").strip()\n''',
'''            short = str(item.get("shortName") or "").strip()\n            code = str(item.get("code") or "").strip() or short\n''', 'VietQR live code preference')

bank_module = Path('vera_vietqr_bank.py')
s = bank_module.read_text(encoding='utf-8')
if 'def vietqr_bank_options(' not in s:
    s += '''\n\ndef vietqr_bank_options(force: bool = False) -> list[dict[str, object]]:\n    """Return safe UI options with human labels and an automatic VietQR code."""\n    options: dict[str, dict[str, object]] = {}\n    for code, aliases in _FALLBACK.items():\n        human = next((value for value in aliases if _key(value) != _key(code)), code)\n        legal = aliases[-1] if aliases else human\n        options[code] = {"code": code, "short_name": human, "name": legal, "aliases": list(dict.fromkeys([code, *aliases]))}\n    try:\n        response = requests.get("https://api.vietqr.io/v2/banks", timeout=5)\n        response.raise_for_status()\n        for item in response.json().get("data") or []:\n            short = str(item.get("shortName") or "").strip()\n            code = str(item.get("code") or "").strip() or short\n            if not code:\n                continue\n            name = str(item.get("name") or short or code).strip()\n            aliases = [value for value in (code, short, name, item.get("bin")) if str(value or "").strip()]\n            options[code] = {"code": code, "short_name": short or code, "name": name, "aliases": list(dict.fromkeys(map(str, aliases)))}\n    except Exception:\n        pass\n    return sorted(options.values(), key=lambda item: str(item.get("short_name") or item.get("code") or '').casefold())\n'''
    bank_module.write_text(s, encoding='utf-8')

# 2) Live Tour payment accepts legacy/full bank names transparently.
once('vera_web_v2_live_tour_payment.py',
'from vera_partial_leave_hours import DEFAULT_HOURS\n',
'from vera_partial_leave_hours import DEFAULT_HOURS\nfrom vera_vietqr_bank import resolve_vietqr_bank_id\n', 'payment import')
once('vera_web_v2_live_tour_payment.py',
'''    bank = {'enabled': True, 'bank_id': str(row.get('bank_name') or '').strip(),\n            'account_no': str(row.get('bank_account') or '').strip(),\n            'account_name': str(row.get('full_name') or '').strip()}\n''',
'''    bank = {'enabled': True, 'bank_id': resolve_vietqr_bank_id(row.get('bank_name')),\n            'account_no': str(row.get('bank_account') or '').strip(),\n            'account_name': str(row.get('full_name') or '').strip()}\n''', 'payment profile bank resolver')

# 3) Self-service profile returns/uses an automatic bank code and normalizes future saves.
once('vera_web_v2_profile.py',
'from vera_web_v2_staff_security import validate_saved_identity_matches\n',
'from vera_web_v2_staff_security import validate_saved_identity_matches\nfrom vera_vietqr_bank import normalize_bank_for_storage, resolve_vietqr_bank_id, vietqr_bank_options\n', 'profile import')
once('vera_web_v2_profile.py',
'''        profile.update({\n            "gender": str(payload.get("Giới tính") or ""),\n''',
'''        profile["bank_code"] = resolve_vietqr_bank_id(profile.get("bank_name"))\n        profile.update({\n            "gender": str(payload.get("Giới tính") or ""),\n''', 'profile bank code response')
once('vera_web_v2_profile.py',
'''            "banks": banks,\n            "wards": _wards(province_code, force=refresh) if province_code is not None else [],\n''',
'''            "banks": banks,\n            "bank_options": vietqr_bank_options(force=refresh),\n            "wards": _wards(province_code, force=refresh) if province_code is not None else [],\n''', 'profile bank options response')
once('vera_web_v2_profile.py',
'''                "bank_account": body.bank_account.strip(), "bank_name": body.bank_name.strip(),\n''',
'''                "bank_account": body.bank_account.strip(), "bank_name": normalize_bank_for_storage(body.bank_name),\n''', 'profile bank normalize save')
once('vera_web_v2_profile.py',
'''            validate_saved_identity_matches(\n''',
'''            if updated["bank_account"] and updated["bank_name"] and not resolve_vietqr_bank_id(updated["bank_name"]):\n                raise HTTPException(400, "Ngân hàng chưa khớp danh mục VietQR. Hãy chọn ngân hàng từ danh sách.")\n            validate_saved_identity_matches(\n''', 'profile bank validation')

# 4) Admin/management employee API exposes bank options+derived code and normalizes saves.
once('vera_web_v2_staff.py',
'from vera_web_v2_staff_security import validate_saved_identity_matches\n',
'from vera_web_v2_staff_security import validate_saved_identity_matches\nfrom vera_vietqr_bank import normalize_bank_for_storage, resolve_vietqr_bank_id, vietqr_bank_options\n', 'staff bank import')
once('vera_web_v2_staff.py',
'''        all_public = list(public_rows)\n''',
'''        for public_row in public_rows:\n            public_row["bank_code"] = resolve_vietqr_bank_id(public_row.get("bank_name"))\n        all_public = list(public_rows)\n''', 'staff derived bank code')
once('vera_web_v2_staff.py',
'''            "shifts_by_department": _shift_catalog(conn, rows),\n''',
'''            "shifts_by_department": _shift_catalog(conn, rows),\n            "bank_options": vietqr_bank_options(),\n''', 'staff bank options')
once('vera_web_v2_staff.py',
'''        if {"province", "district", "ward", "address_detail"}.intersection(values):\n            merged["address"] = _composed_address(merged)\n''',
'''        if "bank_name" in values:\n            merged["bank_name"] = normalize_bank_for_storage(values["bank_name"])\n            if merged.get("bank_account") and merged["bank_name"] and not resolve_vietqr_bank_id(merged["bank_name"]):\n                raise HTTPException(400, "Ngân hàng chưa khớp danh mục VietQR. Hãy chọn ngân hàng từ danh sách.")\n        if {"province", "district", "ward", "address_detail"}.intersection(values):\n            merged["address"] = _composed_address(merged)\n''', 'staff normalize update')
once('vera_web_v2_staff.py',
'''                "address": _composed_address(address_parts), "bank_account": body.bank_account.strip(),\n                "bank_name": body.bank_name.strip(), "monthly_generated": 0,\n''',
'''                "address": _composed_address(address_parts), "bank_account": body.bank_account.strip(),\n                "bank_name": normalize_bank_for_storage(body.bank_name), "monthly_generated": 0,\n''', 'staff normalize create')

# 5) Profile self-service: select bank, show automatic read-only code box.
profile = Path('web-v2/src/pages/ProfilePage.jsx')
s = profile.read_text(encoding='utf-8')
s = s.replace("const [references, setReferences] = useState({ provinces: [], wards: [], banks: [] })", "const [references, setReferences] = useState({ provinces: [], wards: [], banks: [], bank_options: [] })", 1)
s = s.replace("setReferences({ provinces: catalogs.provinces || [], banks: catalogs.banks || [], wards })", "setReferences({ provinces: catalogs.provinces || [], banks: catalogs.banks || [], bank_options: catalogs.bank_options || [], wards })", 1)
s = s.replace("const payload = { ...form, birth_date: toVnDate(form.birth_date), cccd_issue_date: toVnDate(form.cccd_issue_date) }", "const payload = { ...form, birth_date: toVnDate(form.birth_date), cccd_issue_date: toVnDate(form.cccd_issue_date) }; delete payload.bank_code", 1)
s = s.replace("banks: result.banks || current.banks,\n        wards:", "banks: result.banks || current.banks,\n        bank_options: result.bank_options || current.bank_options,\n        wards:", 1)
old_bank = '''        <label>Tên ngân hàng<select value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })}><option value="">-- Chọn ngân hàng --</option>{form.bank_name && !references.banks.includes(form.bank_name) && <option>{form.bank_name}</option>}{references.banks.map((bank) => <option key={bank}>{bank}</option>)}</select><button type="button" className="secondary-button compact" onClick={() => void refreshReference('banks')} disabled={Boolean(referenceBusy)}><RefreshCw size={14} className={referenceBusy === 'banks' ? 'spin' : ''}/> Cập nhật danh mục</button></label>\n        <label>Số tài khoản ngân hàng<input value={form.bank_account} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} /></label>\n'''
new_bank = '''        <label>Tên ngân hàng<select value={form.bank_code || form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value, bank_code: e.target.value })}><option value="">-- Chọn ngân hàng --</option>{(references.bank_options || []).map((bank) => <option key={bank.code} value={bank.code}>{bank.short_name || bank.code}{bank.name && bank.name !== bank.short_name ? ` · ${bank.name}` : ''}</option>)}</select><button type="button" className="secondary-button compact" onClick={() => void refreshReference('banks')} disabled={Boolean(referenceBusy)}><RefreshCw size={14} className={referenceBusy === 'banks' ? 'spin' : ''}/> Cập nhật danh mục</button></label>\n        <label>Mã ngân hàng tự động<input value={form.bank_code || ''} readOnly aria-label="Mã ngân hàng tự động" placeholder="Tự động: VCB / ACB / TCB…" /></label>\n        <label>Số tài khoản ngân hàng<input value={form.bank_account} onChange={(e) => setForm({ ...form, bank_account: e.target.value.replace(/\\D/g, '').slice(0, 19) })} inputMode="numeric" /></label>\n'''
if old_bank not in s: raise SystemExit('ProfilePage bank UI anchor missing')
s = s.replace(old_bank, new_bank, 1)
profile.write_text(s, encoding='utf-8')

# 6) Employee admin profile: use API bank options + read-only automatic code.
page = Path('web-v2/src/pages/EmployeePage.jsx')
s = page.read_text(encoding='utf-8')
s = s.replace("    ['bank_name', 'Tên ngân hàng'], ['bank_account', 'Số tài khoản ngân hàng'],", "    ['bank_name', 'Tên ngân hàng'], ['bank_code', 'Mã ngân hàng tự động'], ['bank_account', 'Số tài khoản ngân hàng'],", 1)
s = s.replace("      field,\n      field.includes('date') ? toInputDate(employee[field]) : employee[field] ?? '',", "      field,\n      field.includes('date') ? toInputDate(employee[field]) : employee[field] ?? '',", 1)
# Never send derived field back through StaffUpdate.
s = s.replace("    const payload = { ...profileDraft }\n", "    const payload = { ...profileDraft }; delete payload.bank_code\n", 1)
# Render bank select and derived read-only code before generic input branch.
anchor = "                if (field === 'gender') return <label key={field}>{label}<select value={profileDraft[field] ?? ''} onChange={(event) => setProfileDraft({ ...profileDraft, [field]: event.target.value })}><option value=\"\">-- Chọn Nam/Nữ --</option><option>Nam</option><option>Nữ</option></select></label>\n                if (isDate) return"
replace = "                if (field === 'gender') return <label key={field}>{label}<select value={profileDraft[field] ?? ''} onChange={(event) => setProfileDraft({ ...profileDraft, [field]: event.target.value })}><option value=\"\">-- Chọn Nam/Nữ --</option><option>Nam</option><option>Nữ</option></select></label>\n                if (field === 'bank_name') return <label key={field}>{label}<select value={profileDraft.bank_code || profileDraft.bank_name || ''} onChange={(event) => setProfileDraft({ ...profileDraft, bank_name: event.target.value, bank_code: event.target.value })}><option value=\"\">-- Chọn ngân hàng --</option>{(data?.bank_options || []).map((bank) => <option key={bank.code} value={bank.code}>{bank.short_name || bank.code}{bank.name && bank.name !== bank.short_name ? ` · ${bank.name}` : ''}</option>)}</select></label>\n                if (field === 'bank_code') return <label key={field}>{label}<input value={profileDraft.bank_code || ''} readOnly aria-label=\"Mã ngân hàng tự động\" placeholder=\"Tự động: VCB / ACB / TCB…\" /></label>\n                if (isDate) return"
if anchor not in s: raise SystemExit('EmployeePage profile field anchor missing')
s = s.replace(anchor, replace, 1)
# Native React-owned profile header actions: no imperative DOM children.
s = s.replace('''        <div className="panel-title-row"><div><h2>SỬA HỒ SƠ · {profileUser}</h2><p>Cập nhật thông tin cá nhân.</p></div></div>\n''', '''        <div className="panel-title-row"><div><h2>SỬA HỒ SƠ · {profileUser}</h2><p>Cập nhật thông tin cá nhân.</p></div><div className="staff-profile-react-actions"><button type="button" className="secondary-button" onClick={() => setProfileUser('')}>✕ Đóng</button><button type="button" className="primary-button" disabled={busy === 'profile'} onClick={saveProfile}><Save size={16}/> Lưu hồ sơ</button></div></div>\n''', 1)
page.write_text(s, encoding='utf-8')

# 7) Root-cause white-screen fix: stop injecting/removing arbitrary children in React's profile subtree.
dirux = Path('web-v2/src/lib/employeeDirectoryUx.js')
s = dirux.read_text(encoding='utf-8')
start = s.index('function ensureProfileHeaderActions() {')
end = s.index('\nfunction reconcile()', start)
s = s[:start] + '''function ensureProfileHeaderActions() {\n  // Legacy versions imperatively appended buttons inside React-owned profile headers.\n  // Closing/filtering the profile could then make React reconcile nodes that had been\n  // moved or removed outside React, producing a fatal blank-screen DOM exception.\n  // EmployeePage now renders these controls itself; only remove stale legacy nodes.\n  document.querySelectorAll('.vera-profile-header-actions').forEach((node) => node.remove())\n}\n''' + s[end:]
dirux.write_text(s, encoding='utf-8')

# Regression tests.
Path('tests/test_vietqr_bank_normalization.py').write_text('''from vera_vietqr_bank import normalize_bank_for_storage, resolve_vietqr_bank_id, vietqr_bank_options\nfrom vera_web_v2_live_tour_payment import profile_bank\n\n\ndef test_full_legal_vietcombank_name_resolves_offline():\n    assert resolve_vietqr_bank_id('Ngân hàng TMCP Ngoại Thương Việt Nam') == 'VCB'\n\ndef test_brand_and_code_resolve_to_same_bank():\n    assert resolve_vietqr_bank_id('Vietcombank') == 'VCB'\n    assert resolve_vietqr_bank_id('VCB') == 'VCB'\n    assert resolve_vietqr_bank_id('Techcombank') == 'TCB'\n\ndef test_storage_normalizes_known_bank():\n    assert normalize_bank_for_storage('Ngân hàng TMCP Kỹ Thương Việt Nam') == 'TCB'\n\ndef test_profile_bank_accepts_legacy_full_name():\n    bank = profile_bank({'bank_name':'Ngân hàng TMCP Ngoại Thương Việt Nam','bank_account':'0123456789','full_name':'Nguyễn Gia Anh'})\n    assert bank == {'enabled': True, 'bank_id': 'VCB', 'account_no': '0123456789', 'account_name': 'Nguyễn Gia Anh'}\n\ndef test_bank_options_have_readonly_code_field():\n    options = vietqr_bank_options()\n    assert any(item['code'] == 'VCB' for item in options)\n    assert all(item.get('code') for item in options)\n''', encoding='utf-8')

Path('tests/test_employee_search_blank_screen_guard.py').write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_employee_profile_controls_are_react_owned():\n    page = (ROOT / 'web-v2/src/pages/EmployeePage.jsx').read_text(encoding='utf-8')\n    ux = (ROOT / 'web-v2/src/lib/employeeDirectoryUx.js').read_text(encoding='utf-8')\n    assert 'staff-profile-react-actions' in page\n    block = ux.split('function ensureProfileHeaderActions()', 1)[1].split('function reconcile()', 1)[0]\n    assert 'appendChild' not in block\n    assert 'insertBefore' not in block\n    assert "querySelectorAll('.vera-profile-header-actions').forEach((node) => node.remove())" in block\n\ndef test_search_change_closes_profile_without_legacy_dom_mutation():\n    page = (ROOT / 'web-v2/src/pages/EmployeePage.jsx').read_text(encoding='utf-8')\n    assert 'const changeEmployeeSearch = (value) =>' in page\n    assert "setProfileUser('')" in page\n    assert 'onChange={changeEmployeeSearch}' in page\n\ndef test_employee_profile_has_automatic_bank_code_box():\n    page = (ROOT / 'web-v2/src/pages/EmployeePage.jsx').read_text(encoding='utf-8')\n    profile = (ROOT / 'web-v2/src/pages/ProfilePage.jsx').read_text(encoding='utf-8')\n    for source in (page, profile):\n        assert 'Mã ngân hàng tự động' in source\n        assert 'VCB / ACB / TCB' in source\n''', encoding='utf-8')
