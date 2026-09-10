"""Employee-name matching shared by screen queries and their Excel exports.

Keep in sync with web-v2/src/lib/employeeSearch.js and the shared test cases.
These are name-filter rules, never identity or authorization rules.
"""
import re
import unicodedata
from typing import Any


def normalize_employee_search(value: Any) -> str:
    value = unicodedata.normalize("NFD", str(value or "").lower())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return " ".join(value.replace("đ", "d").split())


def employee_name_matches(value: Any, query: Any) -> bool:
    needle = normalize_employee_search(query)
    if not needle:
        return True
    short_name = re.split(r"\s*[-–—]\s*", str(value or ""), maxsplit=1)[0]
    return needle in {normalize_employee_search(value), normalize_employee_search(short_name)}
