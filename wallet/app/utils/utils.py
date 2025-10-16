import base64
from datetime import date, datetime


def normalize_name(name: str) -> str:
    """Trim and collapse internal whitespace for consistent uniqueness checks."""
    return " ".join((name or "").split())


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()

def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")

def b64d(s: str) -> bytes:
    return base64.b64decode(s)
