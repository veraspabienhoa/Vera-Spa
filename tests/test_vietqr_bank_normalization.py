from vera_vietqr_bank import normalize_bank_for_storage, resolve_vietqr_bank_id, vietqr_bank_options
from vera_web_v2_live_tour_payment import profile_bank


def test_full_legal_vietcombank_name_resolves_offline():
    assert resolve_vietqr_bank_id('Ngân hàng TMCP Ngoại Thương Việt Nam') == 'VCB'

def test_brand_and_code_resolve_to_same_bank():
    assert resolve_vietqr_bank_id('Vietcombank') == 'VCB'
    assert resolve_vietqr_bank_id('VCB') == 'VCB'
    assert resolve_vietqr_bank_id('Techcombank') == 'TCB'

def test_storage_normalizes_known_bank():
    assert normalize_bank_for_storage('Ngân hàng TMCP Kỹ Thương Việt Nam') == 'TCB'

def test_profile_bank_accepts_legacy_full_name():
    bank = profile_bank({'bank_name':'Ngân hàng TMCP Ngoại Thương Việt Nam','bank_account':'0123456789','full_name':'Nguyễn Gia Anh'})
    assert bank == {'enabled': True, 'bank_id': 'VCB', 'account_no': '0123456789', 'account_name': 'Nguyễn Gia Anh'}

def test_bank_options_have_readonly_code_field():
    options = vietqr_bank_options()
    assert any(item['code'] == 'VCB' for item in options)
    assert all(item.get('code') for item in options)
