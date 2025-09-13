import os
import base64
import hmac
import hashlib
from pydantic import SecretStr
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _load_key(attr: str) -> bytes:
    secret = SecretStr(getattr(settings, attr, None))
    if isinstance(secret, SecretStr):
        raw = secret.get_secret_value()
    else:
        raise RuntimeError("Missing key in env")
    try:
        return base64.urlsafe_b64decode(raw)
    except Exception:
        b = raw.encode() if isinstance(raw, str) else raw
        if len(b) != 32:
            raise
        return b


AES_KEY = _load_key("APP_AES_KEY") 
HMAC_KEY = _load_key("APP_HMAC_KEY") 


def generate_key(n=32) -> None:
    import base64
    val = base64.urlsafe_b64encode(os.urandom(n)).decode()
    print(f"{val}")

            
def encrypt_str(plaintext: str) -> bytes:
    if plaintext is None:
        return None
    aes = AESGCM(AES_KEY)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return b"\x01" + nonce + ct  


def decrypt_str(blob: Optional[bytes]) -> Optional[str]:
    if not blob:
        return None
    if blob[0] != 1:
        raise ValueError("Unsupported ciphertext version")
    nonce, ct = blob[1:13], blob[13:]
    aes = AESGCM(AES_KEY)
    pt = aes.decrypt(nonce, ct, None)
    return pt.decode("utf-8")


def hmac_fingerprint(plaintext: str) -> bytes:
    return hmac.new(HMAC_KEY, plaintext.encode("utf-8"), hashlib.sha256).digest()


def mask_last4(plaintext: str) -> str:
    if not plaintext:
        return ""
    return "****" + plaintext[-4:]
