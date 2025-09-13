import secrets
import logging
import csv
import io
import html
import re
import datetime

logger = logging.getLogger(__name__)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def convert_error_to_str(error) -> str:
    if not isinstance(error, str):
        if isinstance(error, dict):
            error_text = '\n'.join(
                f'{field}: {", ".join(messages)}'
                for field, messages in error.items()
            )
            return error_text
    
    return error


def handle_api_error(response) -> str:
    try:
        json_data = response.json()
        logger.info(f"json_data: {json_data}")
        error = json_data.get('error') or json_data.get('detail') or json_data
    except Exception:
        error = response.text

    error_text = convert_error_to_str(error)
    
    logger.info(f"error_text: {error_text}")

    return error_text
    
    
def export_csv() -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['Date', 'Description', 'Amount'])
    w.writerow(['2024-04-22', 'Zakupy', -90])
    w.writerow(['2024-04-21', 'Paliwo', -240])
    w.writerow(['2024-04-20', 'Wynagrodzenie', 3650])
    return buf.getvalue().encode('utf-8')


def colorize_numbers(sub: str, *, bold_percent: bool = True, color_negatives: bool = True) -> str:
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
    try:
        f = float(v)
    except Exception:
        f = 0.0
    return f"{f:,.2f} {ccy}".replace(',', ' ')


def parse_date(s):
    if s is None: 
        return None
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d'):
        try: 
            return datetime.datetime.strptime(str(s), fmt)
        except Exception:
            pass
    return None
