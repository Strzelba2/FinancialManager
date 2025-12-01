import re

TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")
DATE_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z\u00C0-\u017F\.]+)\s*$")
NEXT_RE = re.compile(r'^(Następne|Next)\s+\d+$', re.IGNORECASE)
BUTTON_RX_ACCEPT = re.compile(r"(Zgoda|Akceptuj|Zgadzam|Zezwól|Accept|Agree|Allow|OK|Got it)", re.IGNORECASE)
BUTTON_RX_REJECT = re.compile(r"(Zamknij|Odrzuć|Od?rzucam|Tylko niezbędne|Reject|Decline|Essential only)", re.IGNORECASE)
