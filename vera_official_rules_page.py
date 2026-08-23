"""Streamlit renderer for the VERA SPA official "Nội quy" policy page."""
from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd

import vera_official_rules as rules

STATE_DF = "_vera_official_rules_editor_df"
STATE_REV = "_vera_official_rules_editor_revision"
STATE_IMPORT_SIG = "_vera_official_rules_import_sig"


def _current_user(st) -> str:
    return str(st.session_state.get("current_user", "") or "").strip()


def _current_role(st) -> str:
    return str(
        st.session_state.get("current_role", "")
        or st.session_state.get("role", "")
        or ""
    ).strip().casefold()


def _can_edit(st) -> bool:
    user = _current_user(st).casefold()
    role = _current_role(st)
    return (
        user in {"quản trị viên", "quan tri vien", "admin"}
        or role in {"admin", "quanly", "quản lý", "quan ly"}
    )


def _legacy_seed(ctx: dict) -> pd.DataFrame:
    fn = ctx.get("_vera_legacy_get_loai_nghi") or ctx.get("get_loai_nghi")
    if callable(fn):
        try:
            df = fn()
            if isinstance(df, pd.DataFrame):
                return df.copy()
        except Exception:
            pass
    return pd.DataFrame(columns=rules.DEFAULT_COLUMNS)


def _get_vpg(ctx: dict):
    return ctx.get("vpg") or ctx.get("_vpg_runtime")


def _get_sheet(ctx: dict):
    sh = ctx.get("sh")
    if sh is not None:
        try:
            return sh.worksheet("LoaiNghi")
        except Exception:
            pass
    client_fn = ctx.get("get_gspread_client")
    sheet_id = ctx.get("SHEET_DU_PHONG_ID")
    if callable(client_fn) and sheet_id:
        client = client_fn()
        if client is not None:
            return client.open_by_key(sheet_id).worksheet("LoaiNghi")
    raise RuntimeError("Không kết nối được worksheet LoaiNghi để đồng bộ tương thích.")


def _a1_col(n: int) -> str:
    n = int(n)
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out or "A"


def _mirror_to_legacy_sheet(ctx: dict, df: pd.DataFrame) -> None:
    ws = _get_sheet(ctx)
    clean = rules.normalize_dataframe(df)
    rows = [list(clean.columns)] + [
        ["" if pd.isna(v) else v for v in row]
        for row in clean.itertuples(index=False, name=None)
    ]
    wanted_rows = max(100, len(rows) + 20)
    wanted_cols = max(15, len(clean.columns) + 3)
    try:
        ws.resize(
            rows=max(int(getattr(ws, "row_count", 0) or 0), wanted_rows),
            cols=max(int(getattr(ws, "col_count", 0) or 0), wanted_cols),
        )
    except Exception:
        pass
    ws.clear()
    if rows:
        ws.update(
            range_name=f"A1:{_a1_col(len(clean.columns))}{len(rows)}",
            values=rows,
            value_input_option="USER_ENTERED",
        )


def _refresh_rule_caches(ctx: dict, df: pd.DataFrame) -> None:
    for name in ("get_loai_nghi", "_vera_legacy_get_loai_nghi"):
        fn = ctx.get(name)
        clear = getattr(fn, "clear", None)
        if callable(clear):
            try:
                clear()
            except Exception:
                pass
    try:
        ctx["st"].session_state["loai_nghi_runtime"] = df.copy()
    except Exception:
        pass


def _excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        rules.normalize_dataframe(df).to_excel(writer, index=False, sheet_name="NoiQuy")
    bio.seek(0)
    return bio.getvalue()


def _read_import(uploaded) -> pd.DataFrame:
    raw = uploaded.getvalue()
    book = pd.ExcelFile(BytesIO(raw))
    sheet = "LoaiNghi" if "LoaiNghi" in book.sheet_names else (
        "NoiQuy" if "NoiQuy" in book.sheet_names else book.sheet_names[0]
    )
    return rules.normalize_dataframe(
        pd.read_excel(BytesIO(raw), sheet_name=sheet, dtype=object)
    )


def _official(ctx: dict) -> tuple[pd.DataFrame, dict]:
    vpg = _get_vpg(ctx)
    seed = _legacy_seed(ctx)
    df = rules.load_dataframe(vpg, seed_df=seed, bootstrap=True)
    return rules.normalize_dataframe(df), rules.get_metadata(vpg)


def _rerun(st):
    fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if callable(fn):
        fn()


def render(ctx: dict[str, Any]) -> None:
    st = ctx["st"]
    can_edit = _can_edit(st)
    official_df, meta = _official(ctx)
    revision = int(meta.get("revision") or 0) if meta else 0

    st.subheader("📜 Nội quy")
    st.caption(
        "Đây là bảng quy định chính thức. Dữ liệu canonical được lưu trong PostgreSQL; "
        "tab LoaiNghi cũ được đồng bộ để các job/luồng tương thích nhận thay đổi."
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    c1.metric("Phiên bản", revision or "Khởi tạo")
    c2.metric("Số dòng", len(official_df))
    updated_at = meta.get("updated_at") if meta else None
    c3.caption(
        f"Cập nhật gần nhất: {updated_at or 'chưa có'} · bởi {meta.get('updated_by','') if meta else ''}"
    )

    if STATE_DF not in st.session_state or st.session_state.get(STATE_REV) != revision:
        st.session_state[STATE_DF] = official_df.copy()
        st.session_state[STATE_REV] = revision

    editor_df = rules.normalize_dataframe(st.session_state.get(STATE_DF, official_df))

    st.markdown("**Công cụ bảng**")
    t1, t2, t3, t4 = st.columns([1.4, 1.2, 1, 1])
    new_col = t1.text_input("Tên cột mới", key="_noi_quy_new_column", disabled=not can_edit)
    if t2.button("➕ Thêm cột", use_container_width=True, disabled=not can_edit):
        name = str(new_col or "").strip()
        if not name:
            st.warning("Nhập tên cột trước khi thêm.")
        elif name in editor_df.columns:
            st.warning("Tên cột đã tồn tại.")
        else:
            editor_df[name] = ""
            st.session_state[STATE_DF] = editor_df
            _rerun(st)

    deletable = [c for c in editor_df.columns if c not in rules.REQUIRED_COLUMNS]
    delete_col = t3.selectbox(
        "Cột cần xóa", deletable or ["—"],
        disabled=(not can_edit or not deletable),
        key="_noi_quy_delete_column",
    )
    if t4.button("🗑️ Xóa cột", use_container_width=True, disabled=(not can_edit or not deletable)):
        editor_df = editor_df.drop(columns=[delete_col])
        st.session_state[STATE_DF] = editor_df
        _rerun(st)

    r1, r2, r3, r4 = st.columns([1, 1, 1, 2])
    if r1.button("➕ Thêm dòng", use_container_width=True, disabled=not can_edit):
        editor_df.loc[len(editor_df)] = [""] * len(editor_df.columns)
        st.session_state[STATE_DF] = editor_df
        _rerun(st)
    delete_row = r2.number_input(
        "Dòng cần xóa", min_value=1, max_value=max(1, len(editor_df)),
        value=max(1, len(editor_df)), step=1,
        disabled=(not can_edit or editor_df.empty), key="_noi_quy_delete_row",
    )
    if r3.button("🗑️ Xóa dòng", use_container_width=True, disabled=(not can_edit or editor_df.empty)):
        idx = int(delete_row) - 1
        if 0 <= idx < len(editor_df):
            editor_df = editor_df.drop(editor_df.index[idx]).reset_index(drop=True)
            st.session_state[STATE_DF] = editor_df
            _rerun(st)
    r4.caption("Copy/Paste trực tiếp trong bảng: Ctrl+C / Ctrl+V (Mac: ⌘C / ⌘V).")

    edited = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=False,
        num_rows="dynamic" if can_edit else "fixed",
        disabled=not can_edit,
        key="_noi_quy_data_editor",
        height=min(760, max(360, 38 * (len(editor_df) + 2))),
    )
    st.session_state[STATE_DF] = rules.normalize_dataframe(edited)

    st.markdown("**Import / Export Excel**")
    x1, x2 = st.columns(2)
    x1.download_button(
        "⬇️ Export Excel",
        data=_excel_bytes(st.session_state[STATE_DF]),
        file_name="NoiQuy_VeraSpa.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    upload = x2.file_uploader(
        "⬆️ Import Excel", type=["xlsx", "xls", "xlsb"],
        disabled=not can_edit, key="_noi_quy_import_excel",
    )
    if upload is not None and can_edit:
        sig = (upload.name, len(upload.getvalue()), hash(upload.getvalue()[:4096]))
        if st.session_state.get(STATE_IMPORT_SIG) != sig:
            try:
                imported = _read_import(upload)
                st.session_state[STATE_DF] = imported
                st.session_state[STATE_IMPORT_SIG] = sig
                st.success(f"Đã nạp {len(imported)} dòng từ Excel vào vùng chỉnh sửa. Chưa áp dụng cho hệ thống.")
                _rerun(st)
            except Exception as exc:
                st.error(f"Không đọc được file Excel: {exc}")

    a1, a2 = st.columns([2, 1])
    if a2.button("↩️ Bỏ thay đổi", use_container_width=True, disabled=not can_edit):
        st.session_state[STATE_DF] = official_df.copy()
        st.session_state[STATE_IMPORT_SIG] = None
        _rerun(st)

    if a1.button("💾 Ghi thay đổi & áp dụng", type="primary", use_container_width=True, disabled=not can_edit):
        df_to_save = rules.normalize_dataframe(st.session_state[STATE_DF])
        try:
            rules.validate_for_apply(df_to_save)
            result = rules.save_dataframe(
                _get_vpg(ctx), df_to_save,
                updated_by=_current_user(st), source="noi_quy_page",
            )
            mirror_error = ""
            try:
                _mirror_to_legacy_sheet(ctx, df_to_save)
            except Exception as exc:
                mirror_error = str(exc)
            _refresh_rule_caches(ctx, df_to_save)
            st.session_state[STATE_REV] = int(result.get("revision") or revision + 1)
            st.session_state[STATE_DF] = df_to_save.copy()
            if mirror_error:
                st.warning(
                    "Nội quy PostgreSQL đã được áp dụng, nhưng đồng bộ tab LoaiNghi cũ chưa thành công: "
                    + mirror_error
                )
            else:
                st.success("Đã ghi Nội quy chính thức và áp dụng cho hệ thống.")
            _rerun(st)
        except Exception as exc:
            st.error(f"Không thể áp dụng Nội quy: {exc}")

    if not can_edit:
        st.info("Bạn đang ở chế độ chỉ xem. Chỉ Admin/Quản lý được phép thay đổi Nội quy.")
