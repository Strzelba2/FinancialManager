import secrets
import logging
import csv
import io
import html
import re
import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_PL_MONTHS = {

    'sty': 1, 'lut': 2, 'mar': 3, 'kwi': 4, 'maj': 5, 'cze': 6,
    'lip': 7, 'sie': 8, 'wrz': 9, 'paź': 10, 'paz': 10, 
    'lis': 11, 'gru': 12,
}

_PL_MONTHS_FULL = {
    'styczeń': 1, 'styczen': 1, 'luty': 2, 'marzec': 3, 'kwiecień': 4, 'kwiecien': 4,
    'maj': 5, 'czerwiec': 6, 'lipiec': 7, 'sierpień': 8, 'sierpien': 8, 'wrzesień': 9, 'wrzesien': 9,
    'październik': 10, 'pazdziernik': 10, 'listopad': 11, 'grudzień': 12, 'grudzien': 12,
}


def generate_csrf_token() -> str:
    """
    Generate a cryptographically secure CSRF token.

    Uses `secrets.token_urlsafe(32)` to produce a URL-safe random string.

    Returns:
        A random URL-safe token string.
    """
    return secrets.token_urlsafe(32)


def convert_error_to_str(error) -> str:
    """
    Normalize various error representations into a human-readable string.

    Supports:
        - str          → returned as-is
        - dict         → multiple field errors joined line by line:
                           "field: msg1, msg2"
        - anything else → converted via str(error)

    Args:
        error: Error object (string, dict, etc.).

    Returns:
        Error message as string.
    """
    if not isinstance(error, str):
        if isinstance(error, dict):
            error_text = '\n'.join(
                f'{field}: {", ".join(messages)}'
                for field, messages in error.items()
            )
            return error_text
    
    return error


def handle_api_error(response) -> str:
    """
    Extract and normalize an error message from an HTTP response.

    Strategy:
        1. Try response.json() and look for 'error' or 'detail' keys.
        2. If JSON decoding fails, fall back to response.text.
        3. Convert the result via `convert_error_to_str`.

    Args:
        response: HTTP response object (e.g. httpx.Response / requests.Response).

    Returns:
        Human-readable error message string.
    """
    try:
        json_data = response.json()
        logger.info(f"handle_api_error: json_data={json_data!r}")
        error = json_data.get('error') or json_data.get('detail') or json_data
    except Exception:
        error = response.text

    error_text = convert_error_to_str(error)
    
    logger.info(f"handle_api_error: normalized error_text={error_text!r}")

    return error_text
    
    
def export_csv() -> bytes:
    """
    Generate a simple example CSV payload with sample transactions.

    Structure:
        Date, Description, Amount

    Returns:
        CSV content encoded as UTF-8 bytes.
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Description', 'Amount'])
    w.writerow(['2024-04-22', 'Zakupy', -90])
    w.writerow(['2024-04-21', 'Paliwo', -240])
    w.writerow(['2024-04-20', 'Wynagrodzenie', 3650])
    return buf.getvalue().encode('utf-8')


def colorize_numbers(sub: str, *, bold_percent: bool = True, color_negatives: bool = True) -> str:
    """
    Wrap numeric tokens in HTML spans for color/emphasis.

    Recognized tokens include optional arrows and +/- signs,
    with optional decimal part and optional '%' suffix, for example:
        "123", "-45.6", "↑ +3.2%", "↓ -10%", "−1,23%"

    Behavior:
        - Positive / up ( + or ↑ ) → span class 'text-positive'
        - Negative / down ( - / − / ↓ ) → span class 'text-negative' (if color_negatives is True)
        - If `bold_percent` is True, tokens containing '%' are wrapped in <strong>...</strong>.
        - Non-matching text is HTML-escaped unchanged.

    Args:
        sub: Input string that may contain numeric tokens.
        bold_percent: Whether to bold tokens that contain '%'.
        color_negatives: Whether to color negative tokens with 'text-negative'.

    Returns:
        HTML string with escaped text and decorated numeric tokens.
    """
    if not sub:
        return ''

    pattern = r'([↑↓]?\s*[+−-]?\s*\d[\d\s]*(?:[.,]\d+)?%?)'

    def repl(m: re.Match) -> str:
        token = m.group(0)
        t = token.replace(' ', '')
        pos = ('+' in t) or ('↑' in t)
        neg = ('−' in t) or ('-' in t and '+' not in t) or ('↓' in t)

        cls = 'text-positive' if pos else ('text-negative' if neg and color_negatives else '')
        content = html.escape(token)
        if bold_percent and '%' in token:
            content = f'<strong>{content}</strong>'
        return f'<span class="{cls}">{content}</span>' if cls else content

    parts, last = [], 0
    for m in re.finditer(pattern, sub):
        parts.append(html.escape(sub[last:m.start()]))  
        parts.append(repl(m))                            
        last = m.end()
    parts.append(html.escape(sub[last:]))
    return ''.join(parts)


def fmt_money(v, ccy='PLN'):
    """
    Format a value as money with 2 decimal places and a currency code.

    Attempts to convert `v` to float, defaulting to 0.0 if it fails.

    Example:
        fmt_money(1234.5, "PLN") -> "1 234.50 PLN"

    Args:
        v: Input numeric-like value.
        ccy: Currency code suffix (e.g. "PLN", "EUR").

    Returns:
        Formatted string: "X XXX.XX CCY" (spaces as thousands separators).
    """
    try:
        f = float(v)
    except Exception:
        f = 0.0
    return f"{f:,.2f} {ccy}".replace(',', ' ')


def century_fix(yy: int) -> int:
    """
    Map a 2-digit year into a 4-digit year based on a pivot.

    Rules:
        - 00–69 → 2000–2069
        - 70–99 → 1970–1999

    This is a common pivoting scheme; adjust if your domain needs a different pivot.

    Args:
        yy: 2-digit year (0–99).

    Returns:
        4-digit year.

    Raises:
        ValueError: if yy is not in 0..99.
    """
    return 2000 + yy if yy <= 69 else 1900 + yy


def parse_date(s, format: str = '%Y-%m-%d'):
    """
    Parse various date formats including PL formats and strings with Polish month names.

    Args:
        s: Input string or date-like object.

    Returns:
        Parsed datetime object or None if invalid.
    """
    if s is None: 
        return None
    if isinstance(s, datetime.datetime):
        logger.info("formar")
        return s.strftime(format)
        
    for fmt in (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%d-%m-%Y %H:%M:%S', 
        '%d-%m-%Y %H:%M',
        '%d.%m.%Y %H:%M:%S',
        '%d.%m.%Y %H:%M',
        '%Y-%m-%d',
        '%d.%m.%Y',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%d-%m-%y',
    ):
        try: 
            return datetime.datetime.strptime(str(s), fmt)
        except Exception:
            pass
        
    m = re.match(r'^\s*(\d{1,2})[-\s]([A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]+)[-\s](\d{2,4})\s*$', s, re.IGNORECASE)
    if m:
        day_str, mon_str, year_str = m.groups()
        mon_key = mon_str.lower()
        month = _PL_MONTHS.get(mon_key) or _PL_MONTHS_FULL.get(mon_key)
        if month:
            day = int(day_str)
            year = int(year_str)
            if year < 100:
                year = century_fix(year)
            try:
                return datetime.datetime(year, month, day)
            except ValueError:
                return None
    return None


def mask_account_numbers(text: str, show_last: int = 4) -> str:
    """
    Mask sensitive account numbers/IBANs inside text, keeping only the last digits.

    Supports:
    - PL-prefixed IBANs (e.g., PL 12 1234 1234 1234 1234 1234 1234)
    - 26-digit raw account numbers
    - 2-4-4-...-4 grouped with spaces or dashes

    Args:
        text: Input string containing account numbers.
        show_last: Number of digits to reveal at the end.

    Returns:
        Masked string.
    """
    if not text:
        return text

    def _mask_digits(digits: str) -> str:
        keep = digits[-show_last:] if digits else ""
        return "•" * max(0, len(digits) - show_last) + keep

    def _replacer(m: re.Match) -> str:
        s = m.group(0)
        digits = re.sub(r"\D", "", s)
        if len(digits) < 16:
            return s
        return _mask_digits(digits)

    patterns = [
        r"\bPL\s*\d(?:[\s-]?\d){25}\b",
        r"\b\d{26}\b",
        r"\b\d{2}(?:[ \u00A0]\d{4}){6}\b",
        r"\b\d{2}(?:-\d{4}){6}\b",
    ]

    out = text
    for pat in patterns:
        out = re.sub(pat, _replacer, out)
    return out


def read_bytes(obj) -> bytes:
    """
    Normalize file input to raw bytes.

    Args:
        obj: Byte-like object or file-like stream.

    Returns:
        Raw bytes.

    Raises:
        TypeError: If the input type is unsupported.
    """
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj)
    if hasattr(obj, 'read'):
        try: 
            obj.seek(0)
        except Exception: 
            pass
        return obj.read()
    raise TypeError(f'Unsupported upload content: {type(obj)}')


def truncate_string(text: Optional[str], n: int, suffix: str = "***", keep_words: bool = False) -> str:
    """
    Truncate `text` to at most `n` visible characters.
    Append `suffix` (default '***') ONLY if truncation occurred.

    Args:
        text: input string (can be None).
        n: max characters of the returned string (not counting suffix).
        suffix: marker to append on truncation.
        keep_words: if True, try not to cut mid-word (falls back to hard cut).

    Returns:
        Truncated (or original) string.
    """
    if not text:
        return ""
    if n <= 0:
        return suffix if suffix else ""

    s = text.strip()
    if len(s) <= n:
        return s

    limit = max(0, n)  

    if keep_words:
        soft = s[:limit]
        cut = soft.rfind(" ")
        if cut >= 0 and cut >= max(0, limit // 2):
            s = soft[:cut]
        else:
            s = s[:limit]
    else:
        s = s[:limit]

    return s.rstrip() + (suffix or "")



