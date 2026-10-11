"""HC attendance eligibility, separate from account authorization roles.

The database expression uses the HR registry without adding a second connection.
Therapist/leader/admin account policy always wins over an HR reassignment.
"""
import vera_web_v2_hr as hr

EXCLUDED_ROLES = frozenset({'admin', 'leader', 'nhanvien'})
HC_CHECKOUT_SQL = f"(({hr.ADMIN_PAY_SQL}) AND lower(btrim(COALESCE(role,''))) NOT IN ('admin','leader','nhanvien'))"


def checkout_eligible(profile):
    role = str(profile.get('role') or profile.get('employee_role') or '').strip().lower()
    if role in EXCLUDED_ROLES:
        return False
    if 'hc_checkout_eligible' in profile:
        return profile['hc_checkout_eligible'] is True
    # Compatibility for pure projections/old callers without HR metadata. Live
    # database paths always supply the explicit registry-derived value.
    definition = hr.DEFAULT_DEPARTMENTS.get(role, {})
    return bool(definition.get('active') and definition.get('salary_mode') in {'hourly', 'monthly'})


def daily_schedule_required(profile):
    return checkout_eligible(profile) or str(profile.get('role') or '').lower() in {'quanly', 'letan', 'locker', 'tapvu'}
