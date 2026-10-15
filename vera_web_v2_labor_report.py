"""Labor declaration report: explicit profile fields, no sample employee values."""
from sqlalchemy import text
from vera_web_v2_residence import rows, display_date
from vera_web_v2_residence_export import render_roster


def labor_rows(conn, ident, usernames):
    profiles = {row['username']: row for row in rows(conn, ident)}
    selected = [profiles[name] for name in usernames if name in profiles]
    details = conn.execute(text('''SELECT username,
        payload->>'Mức lương (giờ)' AS hourly_salary,
        payload->>'Công việc đang làm' AS job_title,
        COALESCE(payload->>'Ngày ký hợp đồng',payload->>'contract_signing_date') AS contract_signed,
        COALESCE(payload->>'Ngày hết hợp đồng',payload->>'contract_end_date') AS contract_end
        FROM employees WHERE username = ANY(:names)
        AND COALESCE(payload->>'__deleted','false') <> 'true' '''), {'names': usernames}).mappings()
    details = {row['username']: dict(row) for row in details}
    # Only saved contract configuration may supply an hourly amount. Never infer
    # signing/expiry dates from employment dates or manufacture a signed contract.
    settings = conn.execute(text("SELECT setting_key,value_json FROM vera_app_setting WHERE category='contract'" )).mappings()
    settings = {row['setting_key']: row['value_json'] for row in settings if isinstance(row['value_json'],dict)}
    for row in selected:
        detail = details.get(row['username'], {})
        code = row['department_code']
        key = 'contract_1' if code in {'leader','nhanvien'} else 'contract_1_' + code
        config = settings.get(key, {})
        salary = detail.get('hourly_salary')
        if salary is None and 'giờ' in (str(config.get('salary_unit') or '') + ' ' + str(config.get('salary_amount') or '')):
            salary = config.get('salary_amount','')
        row.update(hourly_salary=salary if salary is not None else '', job_title=detail.get('job_title') or row['department'],
                   contract_signed=display_date(detail.get('contract_signed')),
                   contract_end=display_date(detail.get('contract_end')))
    return selected


def render_labor(records, format):
    return render_roster(records, format, labor=True)
