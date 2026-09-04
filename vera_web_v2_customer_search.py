"""VERA SPA Web V2 - Customer Search Integration with TimeSoft.

Provides secure backend API to search customers from TimeSoft
without exposing credentials to the frontend.
Only admin, le_tan, quan_ly roles are allowed to search.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from fastapi import HTTPException, Query

VN_TZ = timezone(timedelta(hours=7))

# TimeSoft integration config
TIMESOFT_BASE_URL = os.getenv("TIMESOFT_BASE_URL", "https://vera.timesoft.vn").rstrip("/")
TIMESOFT_CUSTOMER_SEARCH_ENDPOINT = "/ListMan/Customer/SearchCustomerServiceElastics"

# Vault/Secret Manager keys for TimeSoft credentials
TIMESOFT_SESSION_SECRET_KEY = "timesoft_session_id"  # Store session from Secret Manager
TIMESOFT_AUTH_COOKIE_KEY = "timesoft_aspnet_auth"    # ASPXAUTH cookie from Secret Manager

# Search config
MIN_QUERY_LENGTH = 2
MAX_RESULTS = 10
SEARCH_TIMEOUT_SECONDS = 5


def _vault_secret(conn, name: str) -> str:
    """Retrieve secret from Supabase Vault."""
    try:
        from sqlalchemy import text
        value = conn.execute(text("""
            SELECT decrypted_secret
            FROM vault.decrypted_secrets
            WHERE name=:name
            LIMIT 1
        """), {"name": name}).scalar_one_or_none()
        return str(value or "").strip()
    except Exception:
        return ""


def _get_timesoft_headers(conn) -> dict[str, str]:
    """Build headers for TimeSoft API request with stored credentials."""
    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "VERA-SPA/1.0",
    }
    
    # Try to get auth cookie from Secret Manager
    auth_cookie = _vault_secret(conn, TIMESOFT_AUTH_COOKIE_KEY)
    if auth_cookie:
        headers["Cookie"] = f".ASPXAUTH={auth_cookie}"
    
    return headers


def _normalize_phone(phone: str) -> str:
    """Normalize phone number for search (remove spaces, dashes, etc.)."""
    return re.sub(r"[^\d]", "", str(phone or ""))


def _search_timesoft_customers(
    query: str,
    conn,
) -> dict[str, Any]:
    """
    Call TimeSoft Elasticsearch customer search API.
    
    Args:
        query: Search string (customer name or phone number)
        conn: Database connection for retrieving credentials
    
    Returns:
        dict with 'customers' list containing matched results
    """
    query = str(query or "").strip()
    if len(query) < MIN_QUERY_LENGTH:
        return {"customers": []}
    
    headers = _get_timesoft_headers(conn)
    payload = {
        "search": query,
        "pageSize": MAX_RESULTS,
        "pageIndex": 0,
    }
    
    try:
        response = requests.post(
            f"{TIMESOFT_BASE_URL}{TIMESOFT_CUSTOMER_SEARCH_ENDPOINT}",
            json=payload,
            headers=headers,
            timeout=(4, SEARCH_TIMEOUT_SECONDS),
        )
    except requests.Timeout:
        raise HTTPException(
            504,
            f"TimeSoft search timeout ({SEARCH_TIMEOUT_SECONDS}s). Hãy nhập thủ công hoặc thử lại."
        )
    except requests.RequestException as exc:
        raise HTTPException(
            503,
            f"Không kết nối được TimeSoft: {exc}. Vui lòng nhập thủ công."
        )
    
    if response.status_code not in {200, 400}:
        raise HTTPException(
            response.status_code,
            f"TimeSoft trả về lỗi {response.status_code}. Vui lòng nhập thủ công."
        )
    
    try:
        data = response.json()
    except Exception as exc:
        raise HTTPException(
            503,
            f"Phản hồi TimeSoft không hợp lệ: {exc}"
        )
    
    # Parse response - adjust based on actual TimeSoft API format
    customers = []
    if isinstance(data, dict):
        raw_items = data.get("data", []) or data.get("results", []) or data.get("items", [])
        if isinstance(raw_items, list):
            for item in raw_items[:MAX_RESULTS]:
                if not isinstance(item, dict):
                    continue
                customer = {
                    "id": str(item.get("id") or item.get("mID") or ""),
                    "name": str(item.get("name") or item.get("fullName") or "").strip(),
                    "phone": str(item.get("phone") or item.get("phoneNumber") or "").strip(),
                    "email": str(item.get("email") or item.get("emailAddress") or "").strip(),
                    "address": str(item.get("address") or item.get("addressDetail") or "").strip(),
                }
                if customer["name"]:  # Only include if has name
                    customers.append(customer)
    
    return {"customers": customers}


def install_customer_search_routes(
    app,
    engine_instance,
    current_identity,
    require_feature,
    identity_type,
):
    """Install customer search routes to FastAPI app."""
    
    @app.get("/v2/customer/search")
    def search_customers(
        query: str = Query(min_length=MIN_QUERY_LENGTH, max_length=100),
        ident: identity_type = require_feature,  # Auth check
    ):
        """
        Search customers by name or phone number from TimeSoft.
        
        **Authorization:**
        - Only admin, le_tan, quan_ly roles allowed
        
        **Query Parameters:**
        - query: Search string (min 2 chars) - name or phone
        
        **Returns:**
        - List of matched customers with id, name, phone, email, address
        
        **Examples:**
        ```
        GET /v2/customer/search?query=Nguyễn
        GET /v2/customer/search?query=0912345678
        ```
        """
        # Check role permission
        if ident.role not in {"admin", "letan", "quanly"}:
            raise HTTPException(
                403,
                "Chỉ admin, lê tân, quản lý được phép tìm kiếm khách hàng."
            )
        
        with engine_instance().connect() as conn:
            try:
                # Optionally require a specific feature permission
                require_feature(conn, ident, "customer_search")
            except HTTPException as e:
                # If permission doesn't exist yet, allow based on role
                if e.status_code != 403:
                    pass
            
            result = _search_timesoft_customers(query.strip(), conn)
        
        return {
            "ok": True,
            "query": query.strip(),
            "count": len(result.get("customers", [])),
            "customers": result.get("customers", []),
        }
    
    @app.get("/v2/customer/search/health")
    def customer_search_health():
        """Health check for TimeSoft integration."""
        return {
            "ok": True,
            "service": "vera-customer-search",
            "timesoft_url": TIMESOFT_BASE_URL,
            "endpoint": TIMESOFT_CUSTOMER_SEARCH_ENDPOINT,
            "min_query_length": MIN_QUERY_LENGTH,
            "max_results": MAX_RESULTS,
        }
