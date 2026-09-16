"""Resolve employee bank labels to VietQR shortName codes safely.

Existing employee rows historically store either a VietQR shortName (VCB, ACB, MB),
a common bank brand (Vietcombank, Techcombank), or a full legal Vietnamese bank name.
This module normalizes all three forms without exposing account numbers.
"""
from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

import requests

_CACHE: dict[str, Any] = {"loaded_at": 0.0, "aliases": {}}

# Offline aliases cover the common Vietnamese banks and their legacy labels.
# Live VietQR catalog data extends this map when network access is available.
_FALLBACK = {
    "VCB": ["VCB", "Vietcombank", "Ngân hàng TMCP Ngoại Thương Việt Nam", "Ngân hàng Ngoại Thương Việt Nam"],
    "ICB": ["ICB", "VietinBank", "Vietin Bank", "Ngân hàng TMCP Công Thương Việt Nam"],
    "BIDV": ["BIDV", "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam"],
    "VBA": ["VBA", "Agribank", "Ngân hàng Nông nghiệp và Phát triển Nông thôn Việt Nam"],
    "MB": ["MB", "MBBank", "MB Bank", "Ngân hàng TMCP Quân Đội"],
    "TCB": ["TCB", "Techcombank", "Ngân hàng TMCP Kỹ Thương Việt Nam"],
    "ACB": ["ACB", "Ngân hàng TMCP Á Châu"],
    "VPB": ["VPB", "VPBank", "Ngân hàng TMCP Việt Nam Thịnh Vượng"],
    "TPB": ["TPB", "TPBank", "Ngân hàng TMCP Tiên Phong"],
    "STB": ["STB", "Sacombank", "Ngân hàng TMCP Sài Gòn Thương Tín"],
    "HDB": ["HDB", "HDBank", "Ngân hàng TMCP Phát triển Thành phố Hồ Chí Minh"],
    "VIB": ["VIB", "Ngân hàng TMCP Quốc Tế Việt Nam"],
    "MSB": ["MSB", "Maritime Bank", "Ngân hàng TMCP Hàng Hải Việt Nam"],
    "SHB": ["SHB", "Ngân hàng TMCP Sài Gòn - Hà Nội", "Ngân hàng TMCP Sài Gòn Hà Nội"],
    "OCB": ["OCB", "Ngân hàng TMCP Phương Đông"],
    "SEAB": ["SEAB", "SeABank", "Ngân hàng TMCP Đông Nam Á"],
    "EIB": ["EIB", "Eximbank", "Ngân hàng TMCP Xuất Nhập khẩu Việt Nam"],
    "LPB": ["LPB", "LPBank", "LienVietPostBank", "Ngân hàng TMCP Lộc Phát Việt Nam", "Ngân hàng TMCP Bưu điện Liên Việt"],
    "NAB": ["NAB", "Nam A Bank", "NamABank", "Ngân hàng TMCP Nam Á"],
    "PVCB": ["PVCB", "PVcomBank", "Ngân hàng TMCP Đại Chúng Việt Nam"],
    "BAB": ["BAB", "Bac A Bank", "BacABank", "Ngân hàng TMCP Bắc Á"],
    "ABB": ["ABB", "ABBank", "Ngân hàng TMCP An Bình"],
    "NCB": ["NCB", "Ngân hàng TMCP Quốc Dân"],
    "VAB": ["VAB", "VietABank", "Ngân hàng TMCP Việt Á"],
    "VBB": ["VBB", "VietBank", "Ngân hàng TMCP Việt Nam Thương Tín"],
    "KLB": ["KLB", "KienlongBank", "Ngân hàng TMCP Kiên Long"],
    "SGB": ["SGB", "Saigonbank", "Ngân hàng TMCP Sài Gòn Công Thương"],
    "BVB": ["BVB", "BVBank", "Ngân hàng TMCP Bản Việt"],
    "BVBANK": ["BaoViet Bank", "Bao Viet Bank", "Ngân hàng TMCP Bảo Việt"],
    "PGB": ["PGB", "PGBank", "Ngân hàng TMCP Thịnh vượng và Phát triển"],
    "GPB": ["GPB", "GPBank", "Ngân hàng TNHH MTV Dầu Khí Toàn Cầu"],
    "COOPBANK": ["Co-opBank", "CoopBank", "Ngân hàng Hợp tác xã Việt Nam"],
    "SHBVN": ["Shinhan Bank Việt Nam", "Shinhan Bank Vietnam", "ShinhanBank"],
    "WVN": ["Woori Bank Việt Nam", "Woori Bank Vietnam", "WooriBank"],
    "UOB": ["UOB Việt Nam", "UOB Vietnam", "UOB"],
    "CIMB": ["CIMB Việt Nam", "CIMB Vietnam", "CIMB"],
}


def _key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d").replace("Đ", "D").casefold()
    return re.sub(r"[^a-z0-9]", "", text)


def _fallback_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for code, values in _FALLBACK.items():
        for value in {code, *values}:
            aliases[_key(value)] = code
    return aliases


def _aliases(force: bool = False) -> dict[str, str]:
    if not force and _CACHE["aliases"] and time.monotonic() - float(_CACHE["loaded_at"]) < 12 * 3600:
        return dict(_CACHE["aliases"])
    aliases = _fallback_aliases()
    try:
        response = requests.get("https://api.vietqr.io/v2/banks", timeout=5)
        response.raise_for_status()
        for item in response.json().get("data") or []:
            short = str(item.get("shortName") or "").strip()
            code = short or str(item.get("code") or "").strip()
            if not code:
                continue
            for value in (code, item.get("shortName"), item.get("name"), item.get("code"), item.get("bin")):
                if str(value or "").strip():
                    aliases[_key(value)] = code
    except Exception:
        pass
    _CACHE.update({"loaded_at": time.monotonic(), "aliases": aliases})
    return dict(aliases)


def resolve_vietqr_bank_id(value: object) -> str:
    """Return a VietQR-compatible bank shortName/code, or empty when unknown."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    return _aliases().get(_key(raw), "")


def normalize_bank_for_storage(value: object) -> str:
    """Canonicalize known banks while preserving an unknown label for correction."""
    raw = str(value or "").strip()
    return resolve_vietqr_bank_id(raw) or raw
