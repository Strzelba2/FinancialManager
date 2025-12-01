from __future__ import annotations
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Any, Annotated, Callable

from pydantic import BeforeValidator, AfterValidator, EmailStr


_IBAN_RE = re.compile(r"^[A-Z0-9]{15,34}$")
_BIC_RE = re.compile(r"^[A-Z0-9]{8}([A-Z0-9]{3})?$")  


def q2(v: Optional[Decimal]) -> Optional[Decimal]:
    if v is None:
        return None
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def q6(v: Optional[Decimal]) -> Optional[Decimal]:
    if v is None:
        return None
    return v.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def strip(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


def strip_upper(v: Any) -> Any:
    return v.strip().upper() if isinstance(v, str) else v


def strip_lower(v: Any) -> Any:
    return v.strip().lower() if isinstance(v, str) else v


def none_if_empty(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = v.strip()
    return s if s else None


def iban_normalize(iban: str) -> str:
    return iban.replace(" ", "").upper()


def iban_is_valid(iban: str) -> bool:
    iban = iban_normalize(iban)
    if not _IBAN_RE.match(iban):
        return False
    moved = iban[4:] + iban[:4]
    num = []
    for ch in moved:
        num.append(ch if ch.isdigit() else str(ord(ch) - 55)) 
    remainder = 0
    for c in "".join(num):
        remainder = (remainder * 10 + int(c)) % 97
    return remainder == 1


def require_len_between_1_12(v: str) -> str:
    if not (1 <= len(v) <= 12):
        raise ValueError("must be 1..12 characters")
    return v


def require_regex(pattern: str, msg: str) -> Callable[[str], str]:
    rx = re.compile(pattern)
    
    def _check(s: str) -> str:
        if not rx.fullmatch(s):
            raise ValueError(msg)
        return s
    return _check


def require_len_between_1_5(v: str) -> str:
    if not (1 <= len(v) <= 5):
        raise ValueError("must be 1..5 characters")
    return v


def require_nonempty(v: str) -> str:
    if not v or not v.strip():
        raise ValueError("cannot be empty")
    return v


def require_bytes_nonempty(v: bytes) -> bytes:
    if not isinstance(v, (bytes, bytearray)) or len(v) == 0:
        raise ValueError("must be non-empty bytes")
    return bytes(v)


def require_bytes_len_32(v: bytes) -> bytes:
    if not isinstance(v, (bytes, bytearray)) or len(v) != 32:
        raise ValueError("must be exactly 32 bytes")
    return bytes(v)


def require_positive(v: Decimal) -> Decimal:
    if v <= 0:
        raise ValueError("must be > 0")
    return v


def require_nonnegative_opt(v: Optional[Decimal]) -> Optional[Decimal]:
    if v is None:
        return None
    if v < 0:
        raise ValueError("must be ≥ 0")
    return v


def require_iso2_opt(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = none_if_empty(v.upper())
    if v and len(v) != 2:
        raise ValueError("must be 2-letter ISO code")
    return v


def validate_bic_opt(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = none_if_empty(v.upper())
    if v and not _BIC_RE.match(v):
        raise ValueError("bic must be 8 or 11 alphanumeric characters")
    return v


def validate_iban_opt(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = iban_normalize(v)
    if not iban_is_valid(v):
        raise ValueError("invalid IBAN")
    return v


Username12 = Annotated[str, BeforeValidator(strip), AfterValidator(require_len_between_1_12)]
FirstNameOpt = Annotated[Optional[str], AfterValidator(strip),
                         AfterValidator(lambda v: v if v is None or len(v) <= 30 else (
                             (_ for _ in ()).throw(ValueError("first_name must be ≤30 characters"))
                         ))]
NonEmptyStr = Annotated[str, AfterValidator(strip), AfterValidator(require_nonempty)]
Shortname = Annotated[str, BeforeValidator(strip_upper), AfterValidator(require_len_between_1_5)]
EmailLower = Annotated[EmailStr, BeforeValidator(lambda v: strip_lower(str(v)))]

CountryISO2Opt = Annotated[Optional[str], AfterValidator(require_iso2_opt)]
CityOpt = Annotated[Optional[str], AfterValidator(none_if_empty)]
NoneIfEmpty = Annotated[Optional[str], AfterValidator(none_if_empty)]

IBANOpt = Annotated[Optional[str], BeforeValidator(lambda v: None if v is None else iban_normalize(str(v))), 
                    AfterValidator(validate_iban_opt)]
BICOpt = Annotated[Optional[str], AfterValidator(validate_bic_opt)]

BytesNonEmpty = Annotated[bytes, AfterValidator(require_bytes_nonempty)]
BytesLen32 = Annotated[bytes, AfterValidator(require_bytes_len_32)]

Q2 = Annotated[Decimal, AfterValidator(q2)]
Q2OptNonNeg = Annotated[Optional[Decimal], AfterValidator(require_nonnegative_opt), AfterValidator(q2)]
Q6Pos = Annotated[Decimal, AfterValidator(q6), AfterValidator(require_positive)]
AreaQ2OptPos = Annotated[
    Optional[Decimal],
    AfterValidator(lambda v: None if v is None else q2(v)),
    AfterValidator(lambda v: v if v is None or v > 0 else (
        (_ for _ in ()).throw(ValueError("area_m2 must be > 0"))
    )),
]

MICCode = Annotated[
    str,
    BeforeValidator(strip_upper),
    AfterValidator(require_regex(r"^[A-Z0-9]{4}$", "MIC must be 4 uppercase letters/digits")),
]
