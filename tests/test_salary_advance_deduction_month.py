from vera_web_v2_salary_advances import _clean_entry, _month_rows, _summary, SalaryAdvanceCreate
from pydantic import ValidationError

def test_advance_deducts_selected_month_not_payment_date():
    rows = [_clean_entry({'id':'a','employee_username':'employee','advance_date':'2026-10-06','deduction_month':'2026-09','amount':500000}),
            _clean_entry({'id':'b','employee_username':'employee','advance_date':'2026-10-06','amount':100000})]
    assert [r['id'] for r in _month_rows(rows,'2026-09')] == ['a']
    assert _summary(rows,'2026-09')['by_employee']['employee']['payroll_total'] == 500000
    assert _summary(rows,'2026-10')['month_total'] == 100000

def test_old_settled_entries_preserve_payroll_month():
    entry = _clean_entry({'id':'a','employee_username':'employee','advance_date':'2026-10-06','payroll_month':'2026-09','settled_at':'saved','amount':500000})
    assert entry['deduction_month'] == '2026-09'
    assert _summary([entry],'2026-09')['settled_total'] == 500000

def test_invalid_deduction_month_rejected():
    for month in ['2026-00','2026-13','09-2026']:
        try:
            SalaryAdvanceCreate(employee_username='employee',advance_date='2026-10-06',amount=100000,deduction_month=month)
        except ValidationError:
            continue
        raise AssertionError(month)
