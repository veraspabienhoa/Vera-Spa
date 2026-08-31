"""Compatibility installer for the canonical TimeSoft payroll reader.

The resilient reader now lives directly in :mod:`vera_web_v2_payroll`, so all
entrypoints read the exact ``Báo cáo doanh thu hóa đơn`` worksheet and ignore
TimeSoft's stale worksheet dimension.  This module remains as a small startup
compatibility layer for existing API installers.
"""
from __future__ import annotations

import vera_web_v2_payroll as _payroll


RELEASE = _payroll.PAYROLL_SOURCE_READER_RELEASE
TIP_ITEM_PATTERN = r"^tip(?:$|[_\-\s])"


def install_payroll_timesoft_upload_fix() -> None:
    """Patch the canonical payroll module once for every Web V2 calculator."""
    if getattr(_payroll, "_timesoft_upload_dimension_fix_installed", False):
        return
    _payroll.TIP_ITEM_PATTERN = TIP_ITEM_PATTERN
    _payroll._timesoft_upload_dimension_fix_installed = True
    _payroll._timesoft_upload_dimension_fix_release = RELEASE
