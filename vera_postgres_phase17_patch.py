"""Source hooks for Phase 17 final PostgreSQL cutover.

The legacy core remains immutable. Only runtime functions that still require Google
Sheets are renamed and wrapped. Explicit Admin import/export/refresh paths remain.
"""
from __future__ import annotations

import ast
import re

MARKER = "_PHASE17_FINAL_CUTOVER_V1 = True"
TARGETS = [
    "load_usage_guide_document",
    "save_usage_guide_document",
    "update_usage_guide_metadata",
    "delete_usage_guide_document",
    "register_birthday_notice_login",
    "mute_birthday_notice_today",
    "load_dismissed_notice_ids",
    "dismiss_account_notice",
    "load_auto_email_config_v92675",
    "set_auto_email_paused_v92675",
    "_load_midshift_auto_daily_state_v92668",
    "_write_midshift_auto_daily_state_v92668",
    "_append_auto_update_email_log_v92674",
    "load_live_leave_registration_cached",
    "_load_live_primary_leave_sheet",
    "_auto_update_unsent_records_v92674",
    "ensure_employee_in_leave_employee_list",
]

HELPER_BLOCK = r'''
_PHASE17_FINAL_CUTOVER_V1 = True


def _phase17_active():
    try:
        fn = getattr(vpg, "phase17_is_enabled", None) if vpg is not None else None
        return bool(fn()) if callable(fn) else False
    except Exception:
        return False


def _phase17_mirror_mode():
    try:
        fn = getattr(vpg, "phase17_mirror_mode", None) if vpg is not None else None
        return str(fn() or "sync").strip().lower() if callable(fn) else "sync"
    except Exception:
        return "sync"


def _phase17_safe_mirror(fn, context=""):
    helper = getattr(vpg, "phase17_safe_mirror", None) if vpg is not None else None
    if callable(helper):
        return helper(fn, context=context)
    return fn()


def _phase17_clear_cache(fn):
    try:
        clear = getattr(fn, "clear", None)
        if callable(clear):
            clear()
    except Exception:
        pass


def _phase17_leave_df():
    if vpg is not None:
        fn = getattr(vpg, "phase17_leave_dataframe", None)
        if callable(fn):
            value = fn()
            if isinstance(value, pd.DataFrame):
                return value.copy()
    return pd.DataFrame(columns=LEAVE_DATA_COLUMNS + ["__source_sheet_id", "__source_row", "__record_uid"])


def load_live_leave_registration_cached():
    if not _phase17_active():
        return _phase17_legacy_load_live_leave_registration_cached()
    try:
        return combine_leave_sources_for_daily_stats(_phase17_leave_df())
    except Exception:
        return _phase17_leave_df()


def _load_live_primary_leave_sheet(client=None):
    if not _phase17_active():
        return _phase17_legacy__load_live_primary_leave_sheet(client)
    try:
        return combine_leave_sources_for_daily_stats(_phase17_leave_df())
    except Exception:
        return _phase17_leave_df()


def _auto_update_unsent_records_v92674(start_date, end_date):
    if not _phase17_active():
        return _phase17_legacy__auto_update_unsent_records_v92674(start_date, end_date)
    try:
        d = _phase17_leave_df()
        if not isinstance(d, pd.DataFrame) or d.empty:
            return pd.DataFrame()
        all_main = d.copy()
        d = d.copy()
        d["_date"] = pd.to_datetime(d.get("Ngày"), errors="coerce", dayfirst=True).dt.date
        d["_penalty"] = pd.to_numeric(d.get("Phạt vi phạm", 0), errors="coerce").fillna(0)
        updater = d.get("Người cập nhật", pd.Series([""] * len(d), index=d.index)).astype(str)
        d = d[d["_date"].between(start_date, end_date) & d["_penalty"].gt(0) & updater.str.upper().str.startswith("AUTO UPDATE")].copy()
        if d.empty:
            return d
        log = load_leave_activity_log()
        success_keys = set()
        if isinstance(log, pd.DataFrame) and not log.empty:
            action_s = log.get("Hành động", pd.Series([""] * len(log), index=log.index)).astype(str)
            status_s = log.get("Trạng thái", pd.Series([""] * len(log), index=log.index)).astype(str)
            q = log[action_s.eq("EMAIL AUTO PHẠT") & status_s.str.upper().eq("SUCCESS")]
            for _, r in q.iterrows():
                success_keys.add((
                    normalize_schedule_date(r.get("Ngày lịch nghỉ", "")),
                    normalize_login_name(r.get("Tên nhân viên", "")),
                    normalize_leave_reason(r.get("Lý do sau", "") or r.get("Lý do trước", "")),
                ))
        keep = []
        for _, r in d.iterrows():
            if is_nghi_khong_phep_reason(r.get("Lý do nghỉ", "")):
                rd = _parse_vn_date(r.get("Ngày", ""))
                covered = _leave_coverage_employee_keys_for_date(all_main, rd) if rd else set()
                exempt = _auto_check_faceid_exempt_employee_keys_v92682(all_main, rd) if rd else set()
                rk = normalize_employee_match_name(r.get("Tên nhân viên", ""))
                if rk in exempt or rk in covered:
                    keep.append(False)
                    continue
            key = (
                normalize_schedule_date(r.get("Ngày", "")),
                normalize_login_name(r.get("Tên nhân viên", "")),
                normalize_leave_reason(r.get("Lý do nghỉ", "")),
            )
            keep.append(key not in success_keys)
        return d.loc[keep].drop(columns=["_date", "_penalty"], errors="ignore")
    except Exception:
        return pd.DataFrame()


def load_usage_guide_document():
    if not _phase17_active():
        return _phase17_legacy_load_usage_guide_document()
    try:
        getter = getattr(vpg, "phase17_guide_get", None)
        meta, raw = getter() if callable(getter) else (None, None)
        if meta and raw is not None:
            return meta, raw, ""
        legacy_meta, legacy_raw, legacy_err = _phase17_legacy_load_usage_guide_document()
        if legacy_meta and legacy_raw is not None and not legacy_err:
            saver = getattr(vpg, "phase17_guide_save", None)
            if callable(saver):
                saver(legacy_meta, legacy_raw, "phase17-seed")
            return legacy_meta, legacy_raw, ""
        return legacy_meta, legacy_raw, legacy_err
    except Exception as e:
        return None, None, f"Lỗi đọc Hướng dẫn sử dụng từ PostgreSQL: {e}"


def save_usage_guide_document(uploaded_file, title, version, note, actor):
    if not _phase17_active():
        return _phase17_legacy_save_usage_guide_document(uploaded_file, title, version, note, actor)
    if uploaded_file is None:
        return False, "Chưa chọn file tài liệu."
    try:
        raw = uploaded_file.getvalue()
    except Exception:
        raw = b""
    if not raw:
        return False, "File tài liệu đang trống."
    if len(raw) > USAGE_GUIDE_MAX_BYTES:
        return False, f"File vượt giới hạn {USAGE_GUIDE_MAX_BYTES // (1024*1024)} MB. Hãy giảm dung lượng PDF/ảnh trước khi tải lên."
    filename = str(getattr(uploaded_file, "name", "") or "huong-dan").strip()
    mime = str(getattr(uploaded_file, "type", "") or "").strip().lower()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in {"pdf", "png", "jpg", "jpeg", "webp"}:
        return False, "Chỉ hỗ trợ PDF, PNG, JPG/JPEG hoặc WEBP."
    if not mime:
        mime = "application/pdf" if ext == "pdf" else f"image/{'jpeg' if ext in {'jpg','jpeg'} else ext}"
    b64_len = len(base64.b64encode(raw))
    chunks = max(1, int((b64_len + int(USAGE_GUIDE_CHUNK_SIZE) - 1) // int(USAGE_GUIDE_CHUNK_SIZE)))
    meta = {
        "Tên tài liệu": str(title or filename).strip(), "Phiên bản": str(version or "").strip(),
        "Tên file": filename, "MIME": mime, "Dung lượng": str(len(raw)),
        "SHA256": hashlib.sha256(raw).hexdigest(),
        "Cập nhật lúc": datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M:%S"),
        "Người cập nhật": str(actor or "").strip(), "Ghi chú": str(note or "").strip(),
        "Số chunk": str(chunks),
    }
    try:
        saver = getattr(vpg, "phase17_guide_save", None)
        if not callable(saver):
            return False, "PostgreSQL Phase 17 chưa sẵn sàng."
        saver(meta, raw, str(actor or ""))
        _phase17_safe_mirror(lambda: _phase17_legacy_save_usage_guide_document(uploaded_file, title, version, note, actor), "usage_guide_save")
        _phase17_clear_cache(load_usage_guide_document)
        return True, f"Đã lưu '{filename}' ({len(raw)/1024/1024:.2f} MB) làm Hướng dẫn sử dụng."
    except Exception as e:
        return False, f"Lỗi lưu Hướng dẫn sử dụng vào PostgreSQL: {e}"


def update_usage_guide_metadata(title, version, note, actor):
    if not _phase17_active():
        return _phase17_legacy_update_usage_guide_metadata(title, version, note, actor)
    meta, raw, err = load_usage_guide_document()
    if err:
        return False, err
    if not meta or raw is None:
        return False, "Chưa có tài liệu để sửa thông tin."
    updates = {
        "Tên tài liệu": str(title or meta.get("Tên tài liệu", "")).strip(),
        "Phiên bản": str(version or "").strip(), "Ghi chú": str(note or "").strip(),
        "Cập nhật lúc": datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M:%S"),
        "Người cập nhật": str(actor or "").strip(),
    }
    try:
        fn = getattr(vpg, "phase17_guide_update_metadata", None)
        if not callable(fn) or not fn(updates, str(actor or "")):
            return False, "Không cập nhật được thông tin tài liệu trong PostgreSQL."
        _phase17_safe_mirror(lambda: _phase17_legacy_update_usage_guide_metadata(title, version, note, actor), "usage_guide_metadata")
        _phase17_clear_cache(load_usage_guide_document)
        return True, "Đã cập nhật thông tin Hướng dẫn sử dụng."
    except Exception as e:
        return False, f"Lỗi sửa thông tin tài liệu: {e}"


def delete_usage_guide_document(actor):
    if not _phase17_active():
        return _phase17_legacy_delete_usage_guide_document(actor)
    try:
        fn = getattr(vpg, "phase17_guide_delete", None)
        if callable(fn):
            fn()
        _phase17_safe_mirror(lambda: _phase17_legacy_delete_usage_guide_document(actor), "usage_guide_delete")
        _phase17_clear_cache(load_usage_guide_document)
        return True, f"Đã xóa Hướng dẫn sử dụng bởi {actor}."
    except Exception as e:
        return False, f"Lỗi xóa Hướng dẫn sử dụng: {e}"


def register_birthday_notice_login(username):
    if not _phase17_active():
        return _phase17_legacy_register_birthday_notice_login(username)
    try:
        fn = getattr(vpg, "phase17_birthday_login", None)
        if not callable(fn):
            return 1, False
        count, muted = fn(normalize_login_name(username), str(username or ""), get_vn_today().isoformat())
        _phase17_safe_mirror(lambda: _phase17_legacy_register_birthday_notice_login(username), "birthday_login")
        return int(count), bool(muted)
    except Exception:
        return 1, False


def mute_birthday_notice_today(username):
    if not _phase17_active():
        return _phase17_legacy_mute_birthday_notice_today(username)
    try:
        fn = getattr(vpg, "phase17_birthday_mute", None)
        if not callable(fn):
            return False, "PostgreSQL Phase 17 chưa sẵn sàng."
        fn(normalize_login_name(username), str(username or ""), get_vn_today().isoformat())
        _phase17_safe_mirror(lambda: _phase17_legacy_mute_birthday_notice_today(username), "birthday_mute")
        return True, "Đã tạm tắt thông báo sinh nhật đến hết hôm nay."
    except Exception as e:
        return False, f"Không thể tạm tắt thông báo: {e}"


def load_dismissed_notice_ids(username):
    if not _phase17_active():
        return _phase17_legacy_load_dismissed_notice_ids(username)
    user_key = normalize_login_name(username)
    if not user_key:
        return set()
    try:
        ids_fn = getattr(vpg, "phase17_notice_ids", None)
        state_fn = getattr(vpg, "phase17_get_state", None)
        seed_fn = getattr(vpg, "phase17_seed_notice_ids", None)
        ids = set(ids_fn(user_key) if callable(ids_fn) else set())
        seeded = state_fn(f"notice_seeded:{user_key}", None) if callable(state_fn) else None
        if not seeded and _phase17_mirror_mode() != "off":
            try:
                legacy_ids = set(_phase17_legacy_load_dismissed_notice_ids(username) or set())
            except Exception:
                legacy_ids = set()
            if callable(seed_fn):
                seed_fn(user_key, legacy_ids)
            ids |= legacy_ids
        return ids
    except Exception:
        return set()


def dismiss_account_notice(username, notice_id, notice_key, message):
    if not _phase17_active():
        return _phase17_legacy_dismiss_account_notice(username, notice_id, notice_key, message)
    username = str(username or "").strip(); notice_id = str(notice_id or "").strip()
    if not username or not notice_id:
        return False, "Không xác định được thông báo cần đóng."
    try:
        fn = getattr(vpg, "phase17_dismiss_notice", None)
        if not callable(fn):
            return False, "PostgreSQL Phase 17 chưa sẵn sàng."
        fn(normalize_login_name(username), notice_id, notice_key, message)
        _phase17_safe_mirror(lambda: _phase17_legacy_dismiss_account_notice(username, notice_id, notice_key, message), "notice_dismiss")
        _phase17_clear_cache(load_dismissed_notice_ids)
        return True, "Đã đóng thông báo."
    except Exception as e:
        return False, f"Không thể đóng thông báo: {e}"


def load_auto_email_config_v92675():
    if not _phase17_active():
        return _phase17_legacy_load_auto_email_config_v92675()
    default = {"paused": False, "status": AUTO_PENALTY_RUNNING, "updated_date": "", "updated_time": "", "updated_by": "", "error": ""}
    try:
        get_fn = getattr(vpg, "phase17_get_state", None); set_fn = getattr(vpg, "phase17_set_state", None)
        value = get_fn("auto_email_config", None) if callable(get_fn) else None
        if isinstance(value, dict):
            out = default.copy(); out.update(value); out["error"] = ""; return out
        legacy = _phase17_legacy_load_auto_email_config_v92675()
        if isinstance(legacy, dict) and not str(legacy.get("error", "") or "").strip():
            if callable(set_fn):
                set_fn("auto_email_config", legacy, "phase17-seed", "google_sheets_seed")
            out = default.copy(); out.update(legacy); return out
        return default
    except Exception as e:
        default["error"] = str(e); return default


def set_auto_email_paused_v92675(paused, updated_by):
    if not _phase17_active():
        return _phase17_legacy_set_auto_email_paused_v92675(paused, updated_by)
    try:
        now = datetime.now(VN_TZ); status = AUTO_PENALTY_PAUSED if bool(paused) else AUTO_PENALTY_RUNNING
        value = {
            "paused": bool(paused), "status": status,
            "updated_date": now.strftime("%d/%m/%Y"), "updated_time": now.strftime("%H:%M:%S"),
            "updated_by": str(updated_by or "Admin"), "error": "",
        }
        set_fn = getattr(vpg, "phase17_set_state", None)
        if not callable(set_fn):
            return False, "PostgreSQL Phase 17 chưa sẵn sàng."
        set_fn("auto_email_config", value, str(updated_by or "Admin"), "postgres_primary")
        _phase17_safe_mirror(lambda: _phase17_legacy_set_auto_email_paused_v92675(paused, updated_by), "auto_email_config")
        return True, f"Gửi mail tự động của Auto Update đã chuyển sang {'TẠM DỪNG' if paused else 'HOẠT ĐỘNG'}."
    except Exception as e:
        return False, f"Không cập nhật được trạng thái gửi mail Auto Update: {e}"


def _load_midshift_auto_daily_state_v92668():
    if not _phase17_active():
        return _phase17_legacy__load_midshift_auto_daily_state_v92668()
    default = {"key": MIDSHIFT_AUTO_DAILY_STATE_KEY, "status": "", "run_date": "", "run_time": "", "actor": "", "note": "", "error": ""}
    try:
        get_fn = getattr(vpg, "phase17_get_state", None); set_fn = getattr(vpg, "phase17_set_state", None)
        value = get_fn("midshift_auto_daily", None) if callable(get_fn) else None
        if isinstance(value, dict):
            out = default.copy(); out.update(value); out["key"] = MIDSHIFT_AUTO_DAILY_STATE_KEY; out["error"] = ""; return out
        legacy = _phase17_legacy__load_midshift_auto_daily_state_v92668()
        if isinstance(legacy, dict) and not str(legacy.get("error", "") or "").strip():
            if callable(set_fn):
                set_fn("midshift_auto_daily", legacy, "phase17-seed", "google_sheets_seed")
            out = default.copy(); out.update(legacy); return out
        return default
    except Exception as e:
        default["error"] = str(e); return default


def _write_midshift_auto_daily_state_v92668(status, now_vn=None, actor="AUTO UPDATE", note=""):
    if not _phase17_active():
        return _phase17_legacy__write_midshift_auto_daily_state_v92668(status, now_vn=now_vn, actor=actor, note=note)
    try:
        now_vn = now_vn or datetime.now(VN_TZ)
        value = {
            "key": MIDSHIFT_AUTO_DAILY_STATE_KEY, "status": str(status or "").strip().upper(),
            "run_date": now_vn.strftime("%d/%m/%Y"), "run_time": now_vn.strftime("%H:%M:%S"),
            "actor": str(actor or "AUTO UPDATE"), "note": str(note or ""), "error": "",
        }
        set_fn = getattr(vpg, "phase17_set_state", None)
        if not callable(set_fn):
            return False, "PostgreSQL Phase 17 chưa sẵn sàng."
        set_fn("midshift_auto_daily", value, str(actor or "AUTO UPDATE"), "postgres_primary")
        _phase17_safe_mirror(lambda: _phase17_legacy__write_midshift_auto_daily_state_v92668(status, now_vn=now_vn, actor=actor, note=note), "midshift_auto_daily")
        return True, ""
    except Exception as e:
        return False, str(e)


def _append_auto_update_email_log_v92674(employee, email_to, cc_text, reason, status, detail, count=1):
    if not _phase17_active():
        return _phase17_legacy__append_auto_update_email_log_v92674(employee, email_to, cc_text, reason, status, detail, count=count)
    try:
        now_vn = datetime.now(VN_TZ)
        payload = {
            "Ngày": now_vn.strftime("%d/%m/%Y"), "Tên nhân viên": str(employee or ""),
            "Email": str(email_to or ""), "CC": str(cc_text or ""), "Số dòng mới": int(count or 0),
            "Lý do": str(reason or ""), "Trạng thái": str(status or ""),
            "Thời gian gửi": now_vn.strftime("%H:%M:%S"), "Chi tiết": str(detail or ""),
        }
        fn = getattr(vpg, "phase17_append_auto_email_log", None)
        if callable(fn):
            fn(payload)
        _phase17_safe_mirror(lambda: _phase17_legacy__append_auto_update_email_log_v92674(employee, email_to, cc_text, reason, status, detail, count=count), "auto_update_email_log")
    except Exception:
        pass
    return None


def ensure_employee_in_leave_employee_list(employee_name, start_work_date=None):
    if not _phase17_active():
        return _phase17_legacy_ensure_employee_in_leave_employee_list(employee_name, start_work_date=start_work_date)
    try:
        result = _phase17_safe_mirror(lambda: _phase17_legacy_ensure_employee_in_leave_employee_list(employee_name, start_work_date=start_work_date), "leave_employee_list_mirror")
        if _phase17_mirror_mode() == "sync":
            return result
        return True, "PostgreSQL đã lưu nhân viên; DanhSachNV Google Sheets là mirror tùy chọn."
    except Exception as e:
        if _phase17_mirror_mode() == "sync":
            return False, str(e)
        return True, "PostgreSQL đã lưu nhân viên; Google Sheets mirror chưa cập nhật."
'''


def apply(source: str):
    if MARKER in source:
        return source, []
    warnings = []
    try:
        ast.parse(source)
    except Exception as exc:
        return source, [f"source_parse:{type(exc).__name__}"]

    for name in TARGETS:
        legacy = f"_phase17_legacy_{name}"
        pattern = rf"(?m)^def\s+{re.escape(name)}\s*\("
        matches = list(re.finditer(pattern, source))
        if len(matches) != 1:
            warnings.append(f"{name}:{len(matches)}")
            continue
        source = re.sub(pattern, f"def {legacy}(", source, count=1)

    source = source.rstrip() + "\n\n" + HELPER_BLOCK.strip() + "\n"
    try:
        ast.parse(source)
    except Exception as exc:
        warnings.append(f"patched_parse:{type(exc).__name__}:{exc}")
    return source, warnings
