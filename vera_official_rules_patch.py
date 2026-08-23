"""Source patch that upgrades the legacy reason-management page to "Nội quy"."""
from __future__ import annotations

import ast
import re

MARKER = "_OFFICIAL_RULES_PAGE_PATCH_V1 = True"

_MODERN_RULE_RUNTIME_MARKERS = (
    "def _load_persistent_loai_nghi_snapshot(",
    "def load_runtime_loai_nghi(",
    "LOAI_NGHI_RULE_SETTING_CATEGORY",
    "LOAI_NGHI_RULE_SETTING_KEY",
)

_MODERN_INLINE_RULES_MARKERS = (
    "def render_refresh_loai_nghi_button(",
    'elif selected_page == "📅 Đăng ký nghỉ phép":',
    "render_refresh_loai_nghi_button(",
)


def _has_all_markers(source: str, markers: tuple[str, ...]) -> bool:
    return all(marker in source for marker in markers)


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
        # V92.6.99 already owns the canonical PostgreSQL-backed LoaiNghi runtime.
        # There is no legacy get_loai_nghi function left to wrap in this core.
        return source, _has_all_markers(source, _MODERN_RULE_RUNTIME_MARKERS)
    node = max(nodes, key=lambda n: int(getattr(n, "lineno", 0) or 0))
    lines = source.splitlines(keepends=True)
    def_idx = int(node.lineno) - 1
    original = lines[def_idx]
    if "def get_loai_nghi" not in original:
        return source, False
    lines[def_idx] = original.replace("def get_loai_nghi", "def _vera_legacy_get_loai_nghi", 1)
    insert_at = int(node.end_lineno)
    wrapper = '''\n\n@st.cache_data(ttl=15, show_spinner=False)\ndef get_loai_nghi():\n    """Canonical official rules from PostgreSQL, seeded once from legacy LoaiNghi."""\n    try:\n        _seed_rules = _vera_legacy_get_loai_nghi()\n        import vera_official_rules as _vera_rules\n        import vera_postgres as _vpg_rules\n        return _vera_rules.load_dataframe(_vpg_rules, seed_df=_seed_rules, bootstrap=True)\n    except Exception:\n        return _vera_legacy_get_loai_nghi()\n'''
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
    # Current V92.6.99 exposes the Admin rule refresh in the leave-registration
    # page instead of the retired reason-management route. Treat that explicit
    # inline surface as compatible; older cores still require a branch rewrite.
    return source, _has_all_markers(source, _MODERN_INLINE_RULES_MARKERS)


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
