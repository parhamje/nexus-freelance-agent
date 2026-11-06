"""Text utilities: HTML stripping, Persian-aware normalization, similarity, hashing."""
from __future__ import annotations

import hashlib
import html as html_lib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Arabic -> Persian character unification
_CHAR_MAP = str.maketrans({
    "ي": "ی", "ك": "ک", "ؤ": "و", "إ": "ا", "أ": "ا", "ة": "ه", "ۀ": "ه",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6",
    "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6",
    "۷": "7", "۸": "8", "۹": "9",
})

_PUNCT_RE = re.compile(r"[^\w\s\u0600-\u06FF]", re.UNICODE)
_ZWNJ = "\u200c"


def strip_html(text: str) -> str:
    text = _TAG_RE.sub(" ", text or "")
    text = _HTML_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    text = (text or "").translate(_CHAR_MAP)
    text = text.replace(_ZWNJ, " ")
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def content_hash(title: str, description: str = "") -> str:
    joined = normalize_text(strip_html(title)) + "\n" + normalize_text(strip_html(description))[:4000]
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def canonicalize_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith(("utm_", "ref", "gclid", "fbclid"))]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def tokenize(text: str) -> set[str]:
    return {t for t in normalize_text(text).split() if len(t) >= 2}


def token_similarity(a: str, b: str) -> float:
    """Jaccard similarity of word tokens (0..1)."""
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def count_words(text: str) -> int:
    # ZWNJ joins Persian compound words ("نرم‌افزارهای") - remove it, never split on it
    text = (text or "").replace(_ZWNJ, "")
    return len([w for w in _WS_RE.split(text.strip()) if w])


PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def format_toman(amount: float | None, persian_digits: bool = True) -> str:
    if amount is None:
        return "نامشخص"
    s = f"{int(amount):,}"
    return s.translate(PERSIAN_DIGITS) + " تومان" if persian_digits else s + " Toman"


def extract_json(text: str) -> dict:
    """Extract the first balanced JSON object from model output with robust error recovery."""
    import json
    text = (text or "").strip()
    if not text:
        raise ValueError("no JSON object found in model output")

    # 1. Try direct parsing if the entire text is pure JSON
    try:
        data = json.loads(text, strict=False)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Check for markdown code fences (```json ... ``` or ``` ... ```)
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1), strict=False)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Strip leading/trailing markdown fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", text)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned, strict=False)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 4. Search for the outermost JSON object using balanced bracket tracking
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in model output")

    bracket_stack = []
    in_str = False
    esc = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in ("{", "["):
            bracket_stack.append(ch)
        elif ch == "}":
            if bracket_stack and bracket_stack[-1] == "{":
                bracket_stack.pop()
                if not bracket_stack:
                    snippet = text[start:i + 1]
                    try:
                        return json.loads(snippet, strict=False)
                    except json.JSONDecodeError:
                        cleaned_snippet = re.sub(r",\s*([\}\]])", r"\1", snippet)
                        return json.loads(cleaned_snippet, strict=False)
        elif ch == "]":
            if bracket_stack and bracket_stack[-1] == "[":
                bracket_stack.pop()

    # 5. Fallback: If output was cut off (e.g. token limit hit), attempt partial JSON recovery
    if bracket_stack:
        repaired = text[start:]
        if in_str:
            repaired += '"'
        for b in reversed(bracket_stack):
            repaired += '}' if b == '{' else ']'
        repaired = re.sub(r",\s*([\}\]])", r"\1", repaired)
        try:
            data = json.loads(repaired, strict=False)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    raise ValueError("unbalanced JSON in model output: output was cut off before closing all brackets")
