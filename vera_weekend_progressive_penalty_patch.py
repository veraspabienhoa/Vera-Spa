"""Install the weekend ``Người Thứ N`` policy into the legacy Streamlit core.

The V92.6.99 core is intentionally immutable.  This source patch keeps the
existing weekday behaviour, while Saturday/Sunday absence, late-arrival and
early-leave rows only receive an ordinal/surcharge when the PostgreSQL switch
explicitly enables it. The official-rule base penalty is never removed.
"""
from __future__ import annotations

import re


_PROGRESSIVE_FUNCTION = re.compile(
    r"(?ms)^def _progressive_ordinal_and_bonus\(df_sources, ngay, loai_nghi\):\n.*?(?=^def _unexcused_ordinal_and_bonus\()"
)

_PROGRESSIVE_REASON_FUNCTION = re.compile(
    r"(?ms)^def get_progressive_penalty_reason\(value\):\n.*?(?=^def is_progressive_penalty_reason\()"
)

_PROGRESSIVE_REASON_REPLACEMENT = '''def get_progressive_penalty_reason(value):
    """Return the shared canonical group while retaining legacy exclusions."""
    key = normalize_login_name(str(value).replace("🔴", "").strip())
    if key in PROGRESSIVE_PENALTY_EXCLUDED_REASONS:
        return None
    try:
        from vera_progressive_penalty import canonical_reason as _vera_progressive_reason
        canonical = _vera_progressive_reason(value)
        if canonical:
            return canonical
    except Exception:
        pass
    return PROGRESSIVE_PENALTY_REASONS.get(key)


'''

_PROGRESSIVE_REPLACEMENT = '''@st.cache_data(ttl=15, show_spinner=False)
def _vera_weekend_unpaid_nth_enabled():
    """Read the canonical PostgreSQL switch; unavailable/invalid means OFF."""
    from vera_progressive_penalty import (
        DEFAULT_WEEKEND_UNPAID_ENABLED as _vera_weekend_nth_default,
        load_weekend_unpaid_enabled as _vera_load_weekend_nth,
    )

    try:
        if not _vpg_is_enabled():
            return bool(_vera_weekend_nth_default)
        with vpg.get_engine().connect() as _vera_weekend_nth_conn:
            return bool(_vera_load_weekend_nth(_vera_weekend_nth_conn))
    except Exception:
        return bool(_vera_weekend_nth_default)


def _vera_progressive_penalty_applies(ngay, loai_nghi):
    """Evaluate the switch against the row's real calendar date."""
    try:
        from vera_progressive_penalty import applies as _vera_progressive_applies
        return bool(_vera_progressive_applies(
            ngay,
            loai_nghi,
            weekend_unpaid_enabled=_vera_weekend_unpaid_nth_enabled(),
        ))
    except Exception:
        # Fail safely if the shared helper cannot load: the new weekend exception
        # remains OFF, while all established weekday/group behaviour is retained.
        _vera_canonical = get_progressive_penalty_reason(loai_nghi)
        _vera_target = pd.to_datetime(ngay, errors='coerce', dayfirst=True)
        if (
            _vera_canonical is not None
            and pd.notna(_vera_target)
            and _vera_target.weekday() >= 5
        ):
            return False
        return _vera_canonical is not None


def _vera_progressive_surcharge(ordinal):
    """Calculate the unconditional historical surcharge from the shared step."""
    from vera_progressive_penalty import SURCHARGE_STEP as _vera_progressive_step
    return max(0, int(ordinal or 1) - 2) * int(_vera_progressive_step)


def _progressive_ordinal_and_bonus(df_sources, ngay, loai_nghi):
    """Return the per-day ordinal/bonus only when current policy enables it."""
    canonical = get_progressive_penalty_reason(loai_nghi)
    if canonical is None or not _vera_progressive_penalty_applies(ngay, loai_nghi):
        return 1, 0

    target_date = pd.to_datetime(ngay, errors='coerce', dayfirst=True)
    if pd.isna(target_date) or df_sources is None or df_sources.empty:
        ordinal = 1
    else:
        target_date = target_date.date()
        d = df_sources.copy()
        d['Ngày_cmp'] = pd.to_datetime(d['Ngày'], errors='coerce', dayfirst=True).dt.date
        canonical_series = d['Lý do nghỉ'].astype(str).apply(get_progressive_penalty_reason)
        mask = (d['Ngày_cmp'] == target_date) & canonical_series.eq(canonical)
        ordinal = int(mask.sum()) + 1

    return ordinal, _vera_progressive_surcharge(ordinal)


'''


def _replace_once(
    source: str,
    old: str,
    new: str,
    label: str,
    warnings: list[str],
) -> str:
    count = source.count(old)
    if count != 1:
        warnings.append(f"{label}:{count}")
        return source
    return source.replace(old, new, 1)


def apply(source: str):
    warnings: list[str] = []

    reason_matches = list(_PROGRESSIVE_REASON_FUNCTION.finditer(source))
    if len(reason_matches) == 1:
        source = _PROGRESSIVE_REASON_FUNCTION.sub(
            _PROGRESSIVE_REASON_REPLACEMENT, source, count=1
        )
    else:
        warnings.append(f"progressive_reason_helper:{len(reason_matches)}")

    function_matches = list(_PROGRESSIVE_FUNCTION.finditer(source))
    if len(function_matches) == 1:
        source = _PROGRESSIVE_FUNCTION.sub(_PROGRESSIVE_REPLACEMENT, source, count=1)
    else:
        warnings.append(f"progressive_policy_helpers:{len(function_matches)}")

    source = _replace_once(
        source,
        '''        progressive_reason = get_progressive_penalty_reason(loai_nghi)
        if progressive_reason:
            ordinal, extra_penalty = _progressive_ordinal_and_bonus(combined_live, ngay, loai_nghi)''',
        '''        progressive_reason = get_progressive_penalty_reason(loai_nghi)
        if progressive_reason and _vera_progressive_penalty_applies(ngay, loai_nghi):
            ordinal, extra_penalty = _progressive_ordinal_and_bonus(combined_live, ngay, loai_nghi)''',
        "single_create",
        warnings,
    )

    source = _replace_once(
        source,
        '''    progressive_reason = get_progressive_penalty_reason(reason)
    if progressive_reason:
        # Nếu chỉ sửa nội dung nhưng vẫn cùng ngày + cùng nhóm vi phạm, giữ đúng''',
        '''    progressive_reason = get_progressive_penalty_reason(reason)
    progressive_applies = bool(
        progressive_reason and _vera_progressive_penalty_applies(ngay, reason)
    )
    if progressive_reason and not progressive_applies and not defaults:
        # Dữ liệu lịch sử không còn trong danh mục: tách phần lũy tiến cũ
        # để ngoại lệ cuối tuần vẫn giữ đúng tiền phạt gốc.
        final_penalty = _existing_base_penalty(original_row, catalog)
    if progressive_applies:
        # Nếu chỉ sửa nội dung nhưng vẫn cùng ngày + cùng nhóm vi phạm, giữ đúng''',
        "edit_recalculation",
        warnings,
    )

    source = _replace_once(
        source,
        '''        extra_penalty = max(0, int(ordinal) - 2) * 100000''',
        '''        extra_penalty = _vera_progressive_surcharge(ordinal)''',
        "edit_surcharge_step",
        warnings,
    )

    source = _replace_once(
        source,
        '''        for new_ordinal, (_, row_idx, physical) in enumerate(ordered, start=1):
            base_penalty = _existing_base_penalty(physical, catalog)
            extra_penalty = max(0, new_ordinal - 2) * 100000
            new_penalty = float(base_penalty) + float(extra_penalty)
            prefix = f"Người Thứ {new_ordinal} {canonical.lower()}"
            user_note = _strip_generated_progressive_prefix(physical.get('Chi tiết', ''))
            new_detail = f"{prefix} | {user_note}" if user_note else prefix''',
        '''        group_uses_progressive = _vera_progressive_penalty_applies(ngay, canonical)
        for new_ordinal, (_, row_idx, physical) in enumerate(ordered, start=1):
            base_penalty = _existing_base_penalty(physical, catalog)
            extra_penalty = (
                _vera_progressive_surcharge(new_ordinal) if group_uses_progressive else 0
            )
            new_penalty = float(base_penalty) + float(extra_penalty)
            user_note = _strip_generated_progressive_prefix(physical.get('Chi tiết', ''))
            if group_uses_progressive:
                prefix = f"Người Thứ {new_ordinal} {canonical.lower()}"
                new_detail = f"{prefix} | {user_note}" if user_note else prefix
            else:
                new_detail = user_note''',
        "rebalance",
        warnings,
    )

    source = _replace_once(
        source,
        '''    old_extra = max(0, int(old_ordinal or 1) - 2) * 100000''',
        '''    old_extra = _vera_progressive_surcharge(old_ordinal or 1)''',
        "historical_base_surcharge_step",
        warnings,
    )

    source = _replace_once(
        source,
        '''    return _vera_shared_validate_leave_live(payload, live_df, credentials_df, _vera_shared_runtime)''',
        '''    _vera_validation_result = _vera_shared_validate_leave_live(
        payload, live_df, credentials_df, _vera_shared_runtime
    )
    # Shared validation intentionally remains framework-neutral.  Remove only
    # generated weekend warnings for rows where the PostgreSQL policy says that
    # "Người Thứ N" does not apply; unrelated warnings remain untouched.
    if isinstance(_vera_validation_result, dict) and _vera_validation_result.get("warnings"):
        _vera_reason = payload.get("reason", "")
        _vera_start = payload.get("start_date")
        _vera_end = payload.get("end_date")
        _vera_hidden_prefixes = set()
        if isinstance(_vera_start, date) and isinstance(_vera_end, date):
            _vera_day = _vera_start
            while _vera_day <= _vera_end:
                if not _vera_progressive_penalty_applies(_vera_day, _vera_reason):
                    _vera_hidden_prefixes.add(
                        f"{_vera_day.strftime('%d/%m/%Y')}: Người Thứ "
                    )
                _vera_day += timedelta(days=1)
        if _vera_hidden_prefixes:
            _vera_validation_result["warnings"] = [
                _vera_warning
                for _vera_warning in _vera_validation_result.get("warnings", [])
                if not any(
                    str(_vera_warning).startswith(_vera_prefix)
                    for _vera_prefix in _vera_hidden_prefixes
                )
            ]
    return _vera_validation_result''',
        "registration_preview",
        warnings,
    )

    return source, warnings
