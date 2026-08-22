"""Phase 17 patch-order hotfix for V92.22.2.

The original Phase 17 source patch correctly renames legacy functions, but it appends
its wrapper block at EOF. Streamlit executes UI code before EOF, so a renamed wrapper
can be referenced before its replacement definition exists. This adapter reuses the
original patch and relocates the wrapper block immediately after the module docstring /
__future__ imports, keeping the legacy core immutable and preserving all Phase 17
business logic.
"""
from __future__ import annotations

import ast

import vera_postgres_phase17_patch as _base

MARKER = "_PHASE17_FINAL_CUTOVER_ORDER_V2 = True"


def _insert_offset_after_future_imports(source: str) -> int:
    """Return a safe insertion offset after docstring and __future__ imports."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    end_line = 0
    for idx, node in enumerate(tree.body):
        is_docstring = (
            idx == 0
            and isinstance(node, ast.Expr)
            and isinstance(getattr(node, "value", None), ast.Constant)
            and isinstance(node.value.value, str)
        )
        is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
        if is_docstring or is_future:
            end_line = max(end_line, int(getattr(node, "end_lineno", node.lineno)))
            continue
        break
    return sum(len(line) for line in lines[:end_line])


def apply(source: str):
    if MARKER in source:
        return source, []

    patched, warnings = _base.apply(source)
    warnings = list(warnings or [])
    block = str(getattr(_base, "HELPER_BLOCK", "") or "").strip()
    if not block:
        warnings.append("phase17_order:helper_block_missing")
        return patched, warnings

    trimmed = patched.rstrip()
    if not trimmed.endswith(block):
        # The base patch changed shape. Do not guess/mutate an unknown source layout.
        warnings.append("phase17_order:helper_block_not_at_eof")
        return patched, warnings

    body = trimmed[: -len(block)].rstrip() + "\n"
    try:
        pos = _insert_offset_after_future_imports(body)
    except Exception as exc:
        warnings.append(f"phase17_order:anchor:{type(exc).__name__}:{exc}")
        return patched, warnings

    early_block = "\n\n" + block + "\n" + MARKER + "\n\n"
    reordered = body[:pos] + early_block + body[pos:]
    try:
        ast.parse(reordered)
    except Exception as exc:
        warnings.append(f"phase17_order:patched_parse:{type(exc).__name__}:{exc}")
        return patched, warnings
    return reordered, warnings
