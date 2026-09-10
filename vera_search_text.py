"""Word-boundary matching for user-entered search filters (not identity checks)."""
import re
import unicodedata


def normalized_search_text(value):
    text = unicodedata.normalize("NFD", str(value or "")).lower().replace("đ", "d")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[\W_]+", " ", text).split())


def search_text_matches(fields, query):
    terms = normalized_search_text(query).split()
    if not terms:
        return True
    for field in fields if isinstance(fields, (list, tuple)) else [fields]:
        words = normalized_search_text(field).split()
        for start in range(len(words) - len(terms) + 1):
            if all(words[start + i].startswith(term) if i == len(terms) - 1
                   else words[start + i] == term for i, term in enumerate(terms)):
                return True
    return False
