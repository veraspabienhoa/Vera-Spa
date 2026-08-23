"""Source patch that upgrades the legacy reason-management page to "Nội quy"."""
from __future__ import annotations

import ast
import re

MARKER = "_OFFICIAL_RULES_PAGE_PATCH_V1 = True"


def _patch_latest_get_loai_nghi(source: str) -> tuple[str, bool]:
    try:
        tree = ast.parse(source)
    except Exception:
        return source, False
    nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "get_loai_nghi"
    ]
    if not nodes:
        return source, False
    node = max(nodes, key=lambda n: int(getattr(n, "lineno", 0) or 0))
    lines = source.splitlines(keepends=True)
    def_idx = int(node.lineno) - 1
    original = lines[def_idx]
    if "def get_loai_nghi" not in original:
        return source, False
    lines[def_idx] = original.replace("def get_loai_nghi", "def _vera_legacy_get_loai_nghi", 1)
    insert_at = int(node.end_lineno)
    wrapper = '''\n\n@st.cache_data(ttl=15, show_spinner=False)\ndef get_loai_nghi():\n    """Canonical official rules from PostgreSQL, seeded once from legacy LoaiNghi."""\n    try:\n        _seed_rules = _vera_legacy_get_loai_nghi()\n        import vera_official_rules as _vera_rules\n        return _vera_rules.load_dataframe(vpg, seed_df=_seed_rules, bootstrap=True)\n    except Exception:\n        return _vera_legacy_get_loai_nghi()\n'''
    lines.insert(insert_at, wrapper)
    return "".join(lines), True


_BRANCH_PATTERNS = [
    re.compile(
        r'''(?ms)^(?P<i>[ \t]*)(?P<h>(?:if|elif)\s+[^\n:]*==\s*["']reason["']\s*:\s*\n)(?P<b>.*?)(?=^(?P=i)(?:elif\b|else\s*:))'''
    ),
    re.compile(
        r'''(?ms)^(?P<i>[ \t]*)(?P<h>(?:if|elif)\s+[^\n:]*==\s*["']🧾\s*Quản lý lý do nghỉ["']\s*:\s*\n)(?P<b>.*?)(?=^(?P=i)(?:elif\b|else\s*:))'''
    ),
]


def _patch_reason_branch(source: str) -> tuple[str, bool]:
    for pattern in _BRANCH_PATTERNS:
        match = pattern.search(source)
        if not match:
            continue
        indent = match.group("i")
        body_indent = indent + "    "
        new_body = (
            f"{body_indent}import vera_official_rules_page as _vera_rules_page\n"
            f"{body_indent}_vera_rules_page.render(globals())\n"
        )
        return source[:match.start("b")] + new_body + source[match.end("b"):], True
    return source, False


def apply(source: str):
    if MARKER in source:
        return source, []
    warnings = []
    source, ok_rules = _patch_latest_get_loai_nghi(source)
    if not ok_rules:
        warnings.append("get_loai_nghi_canonical:0")
    source, ok_page = _patch_reason_branch(source)
    if not ok_page:
        warnings.append("reason_page_branch:0")
    source = MARKER + "\n" + source
    try:
        ast.parse(source)
    except Exception as exc:
        warnings.append(f"syntax:{type(exc).__name__}:{exc}")
    return source, warnings
