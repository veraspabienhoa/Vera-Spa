"""Phase 17 patch-order hotfix for V92.22.2.

The original Phase 17 source patch renames legacy functions and appends its wrapper
block at EOF. Streamlit can execute leave-registration UI before EOF, so the renamed
loader may be referenced before the replacement wrapper exists.

This adapter reuses the original Phase 17 patch, removes its EOF wrapper block, then
relocates that block immediately after the renamed legacy
``_phase17_legacy_load_live_leave_registration_cached`` function. That anchor is before
``_load_live_leave_registration_for_validation`` in the V92.6.99 core, so the public
``load_live_leave_registration_cached`` wrapper is guaranteed to exist before the UI
validation path can call it. The legacy core itself remains immutable.
"""
from __future__ import annotations

import ast

import vera_postgres_phase17_patch as _base

MARKER = "_PHASE17_FINAL_CUTOVER_ORDER_V3 = True"
LEGACY_LEAVE_LOADER = "_phase17_legacy_load_live_leave_registration_cached"


def _offset_after_top_level_function(source: str, function_name: str) -> int:
    """Return the source offset immediately after a named top-level function."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            end_line = int(getattr(node, "end_lineno", node.lineno))
            return sum(len(line) for line in lines[:end_line])
    raise LookupError(function_name)


def _remove_eof_helper_block(patched: str, block: str):
    """Remove the exact Phase 17 helper block from EOF without touching core code."""
    trimmed = patched.rstrip()
    if trimmed.endswith(block):
        return trimmed[: -len(block)].rstrip() + "\n", True

    # Defensive fallback: locate the final exact block and only accept whitespace after it.
    idx = trimmed.rfind(block)
    if idx >= 0 and not trimmed[idx + len(block):].strip():
        return trimmed[:idx].rstrip() + "\n", True
    return patched, False


def apply(source: str):
    if MARKER in source:
        return source, []

    patched, warnings = _base.apply(source)
    warnings = list(warnings or [])
    block = str(getattr(_base, "HELPER_BLOCK", "") or "").strip()
    if not block:
        warnings.append("phase17_order_v3:helper_block_missing")
        return patched, warnings

    body, removed = _remove_eof_helper_block(patched, block)
    if not removed:
        warnings.append("phase17_order_v3:helper_block_not_at_eof")
        return patched, warnings

    try:
        pos = _offset_after_top_level_function(body, LEGACY_LEAVE_LOADER)
    except Exception as exc:
        warnings.append(f"phase17_order_v3:leave_anchor:{type(exc).__name__}:{exc}")
        return patched, warnings

    early_block = "\n\n" + block + "\n" + MARKER + "\n\n"
    reordered = body[:pos] + early_block + body[pos:]

    try:
        tree = ast.parse(reordered)
    except Exception as exc:
        warnings.append(f"phase17_order_v3:patched_parse:{type(exc).__name__}:{exc}")
        return patched, warnings

    # Hard assertion for the exact production failure: public wrapper must be defined
    # before the validation function that calls it.
    wrapper_line = None
    validation_line = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "load_live_leave_registration_cached":
                wrapper_line = int(node.lineno)
            elif node.name == "_load_live_leave_registration_for_validation":
                validation_line = int(node.lineno)
    if wrapper_line is None:
        warnings.append("phase17_order_v3:public_loader_missing")
        return patched, warnings
    if validation_line is not None and wrapper_line >= validation_line:
        warnings.append(
            f"phase17_order_v3:public_loader_after_validation:{wrapper_line}>={validation_line}"
        )
        return patched, warnings

    return reordered, warnings
