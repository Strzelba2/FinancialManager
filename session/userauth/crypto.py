import base64
import os 
import hmac
from typing import Tuple, Optional
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from django.conf import settings


KEK = base64.b64decode(settings.APP_AES_KEY)
HMAC_KEY = base64.b64decode(settings.APP_HMAC_KEY)


def wrap_dek(dek: bytes) -> tuple[bytes, bytes]:
    """
    Encrypt (wrap) a DEK using AES-GCM with a KEK.

    AES-GCM provides confidentiality and integrity (auth tag is appended to ciphertext).
    A fresh 12-byte random nonce is generated per call; reuse of a nonce with the same
    KEK catastrophically breaks security.

    Args:
        dek: Data Encryption Key to wrap (raw key bytes).

    Returns:
        Tuple[nonce, ciphertext]:
            - nonce (bytes): 12-byte random nonce used for AES-GCM.
            - ciphertext (bytes): encrypted DEK with the GCM auth tag appended
              (as produced by `AESGCM.encrypt`).
    """
    aes = AESGCM(KEK)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, dek, None) 
    return nonce, ct


def unwrap_dek(nonce: bytes, ct: bytes) -> bytes:
    """
    Decrypt (unwrap) a DEK previously wrapped with `wrap_dek`.

    Args:
        nonce: The 12-byte nonce returned by `wrap_dek`.
        ct: The ciphertext returned by `wrap_dek` (includes the GCM auth tag).

    Returns:
        The original DEK bytes.
    """
    aes = AESGCM(KEK)
    return aes.decrypt(nonce, ct, None)


def derive_keys_from_dek(dek: bytes) -> Tuple[bytes, bytes]:
    """
    Derive separate encryption and MAC keys from a DEK using HKDF-SHA256.

    This uses HKDF in extract+expand mode twice with different `info` labels
    (domain separation) so the resulting keys are independent even though they
    share the same salt and input key material.

    Args:
        dek: Data Encryption Key (raw bytes) used as HKDF input key material.

    Returns:
        (enc_key, mac_key):
            - enc_key (32 bytes): for AES-256-GCM (or other 256-bit cipher).
            - mac_key (32 bytes): for HMAC-SHA256 over your chosen data.
    """
    hkdf_enc = HKDF(algorithm=hashes.SHA256(), length=32, salt=settings.SERVER_SALT.encode(), info=b"enc")
    hkdf_mac = HKDF(algorithm=hashes.SHA256(), length=32, salt=settings.SERVER_SALT.encode(), info=b"mac")
    enc_key = hkdf_enc.derive(dek)
    mac_key = hkdf_mac.derive(dek)
    return enc_key, mac_key


def encrypt_bytes(enc_key: bytes, plaintext: bytes) -> Tuple[bytes, bytes]:
    """
    Encrypt arbitrary bytes with AES-GCM using a fresh random 12-byte nonce.

    Args:
        enc_key: 16/24/32-byte AES key (use 32 for AES-256-GCM).
        plaintext: data to encrypt.

    Returns:
        (nonce, ciphertext):
            - nonce (12 bytes): random per-encryption value.
            - ciphertext: AES-GCM output including the authentication tag.
    """
    aes = AESGCM(enc_key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext, None)
    return nonce, ct


def decrypt_bytes(enc_key: bytes, nonce: bytes, ct: bytes) -> bytes:
    """
    Decrypt bytes previously produced by `encrypt_bytes`.

    Args:
        enc_key: same key used for encryption.
        nonce: 12-byte nonce returned by `encrypt_bytes`.
        ct: ciphertext with embedded GCM tag.

    Returns:
        Decrypted plaintext bytes.
    """
    aes = AESGCM(enc_key)
    return aes.decrypt(nonce, ct, None)


def hmac_bytes(mac_key: bytes, data: bytes) -> bytes:
    """
    Compute HMAC-SHA256 over `data` with `mac_key`.

    Args:
        mac_key: secret MAC key (e.g., from `derive_keys_from_dek`).
        data: bytes to authenticate (e.g., nonce || ciphertext || metadata).

    Returns:
        Raw 32-byte HMAC digest.

    """
    return hmac.new(mac_key, data, hashlib.sha256).digest()


def hmac_verify(mac_key: bytes, data: bytes, mac: bytes) -> bool:
    """
    Constant-time verification of an HMAC-SHA256 tag.

    Args:
        mac_key: secret MAC key.
        data: original data that was MACed.
        mac: expected MAC to verify.

    Returns:
        True if valid, False otherwise.
    """
    expected = hmac_bytes(mac_key, data)
    return hmac.compare_digest(expected, mac)
