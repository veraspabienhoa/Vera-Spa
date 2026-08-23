"""Post-login landing-page guard for VERA SPA.

The legacy application owns the login and menu implementation inside the immutable
``app_v92699_core.py``.  This small runtime shim changes only the *initial* menu
selection of a Streamlit session: when the authenticated main-menu widget first
appears, ``📅 Đăng ký nghỉ`` is selected.  After that first render the widget is
left completely untouched, so users can navigate normally.

No authentication/session data is persisted here and no business logic is changed.
"""
from __future__ import annotations

from functools import wraps
from typing import Any


_TARGET_LABELS = (
    "📅 Đăng ký nghỉ",
    "📅 Đăng ký nghỉ phép",  # legacy/internal label for rollback compatibility
)
_FLAG = "_vera_postlogin_leave_landing_applied"
_INSTALL_ATTR = "_vera_postlogin_leave_landing_installed"


def _target_index(options: Any):
    try:
        values = list(options)
    except Exception:
        return None, None, options
    for label in _TARGET_LABELS:
        try:
            idx = values.index(label)
        except ValueError:
            continue
        return label, idx, values
    return None, None, values


def _force_index(args, kwargs, idx: int):
    """Override the selector's ``index`` whether positional or keyword."""
    new_args = list(args)
    new_kwargs = dict(kwargs)
    # radio/selectbox signature: (label, options, index=0, ...)
    if new_args:
        new_args[0] = idx
        new_kwargs.pop("index", None)
    else:
        new_kwargs["index"] = idx
    return tuple(new_args), new_kwargs


def _apply_once(st, options, args, kwargs):
    target, idx, normalized_options = _target_index(options)
    if target is None or bool(st.session_state.get(_FLAG, False)):
        return options, args, kwargs

    key = kwargs.get("key")
    applied = False
    if key:
        try:
            # This executes before the menu widget is instantiated on the current
            # rerun, so Streamlit accepts it as the widget's initial state.
            st.session_state[key] = target
            applied = True
        except Exception:
            applied = False

    if not applied:
        args, kwargs = _force_index(args, kwargs, int(idx))
        applied = True

    if applied:
        st.session_state[_FLAG] = True
    return normalized_options, args, kwargs


def install() -> bool:
    """Install the landing-page shim once per Python process."""
    import streamlit as st

    if bool(getattr(st, _INSTALL_ATTR, False)):
        return True

    # Patch top-level Streamlit selectors.  This covers st.radio/st.selectbox.
    for name in ("radio", "selectbox"):
        original = getattr(st, name, None)
        if not callable(original) or bool(getattr(original, "_vera_leave_landing_wrapper", False)):
            continue

        @wraps(original)
        def wrapped(label, options, *args, __original=original, **kwargs):
            options, args, kwargs = _apply_once(st, options, args, kwargs)
            return __original(label, options, *args, **kwargs)

        wrapped._vera_leave_landing_wrapper = True
        setattr(st, name, wrapped)

    # Sidebar widgets are DeltaGenerator methods and can bypass the module-level
    # functions above, so patch the two selector methods at class level as well.
    try:
        from streamlit.delta_generator import DeltaGenerator

        for name in ("radio", "selectbox"):
            original = getattr(DeltaGenerator, name, None)
            if not callable(original) or bool(getattr(original, "_vera_leave_landing_wrapper", False)):
                continue

            @wraps(original)
            def dg_wrapped(self, label, options, *args, __original=original, **kwargs):
                options, args, kwargs = _apply_once(st, options, args, kwargs)
                return __original(self, label, options, *args, **kwargs)

            dg_wrapped._vera_leave_landing_wrapper = True
            setattr(DeltaGenerator, name, dg_wrapped)
    except Exception:
        # Module-level wrappers are still a safe fallback on Streamlit versions
        # where DeltaGenerator internals are reorganized.
        pass

    setattr(st, _INSTALL_ATTR, True)
    return True
