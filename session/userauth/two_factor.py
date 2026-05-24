import hashlib
import base64
import pyotp
import qrcode
from qrcode.image.svg import SvgImage 
from io import BytesIO
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger('session-auth')

TWO_FACTOR_PENDING_SESSION_KEY = "two_factor_pending_user_id"
TWO_FACTOR_VERIFIED_SESSION_KEY = "two_factor_verified_user_id"
TWO_FACTOR_ATTEMPTS_SESSION_KEY = "two_factor_attempts"
TWO_FACTOR_MAX_ATTEMPTS = 3
TWO_FACTOR_USED_TOKEN_TTL_SECONDS = 90
TWO_FACTOR_PENDING_LOGIN_TTL_SECONDS = 300


class TwoFactorSessionState:
    """
    Manage per-login 2FA verification state stored in the Django session.
    """

    MAX_ATTEMPTS = TWO_FACTOR_MAX_ATTEMPTS
    PENDING_LOGIN_TTL_SECONDS = TWO_FACTOR_PENDING_LOGIN_TTL_SECONDS

    @staticmethod
    def pending_login_cache_key(user) -> str:
        return f"two_factor_pending_login:{user.pk}"

    @staticmethod
    def _session_key(request) -> str | None:
        return getattr(request.session, "session_key", None)

    @staticmethod
    def mark_pending(request, user) -> None:
        request.session[TWO_FACTOR_PENDING_SESSION_KEY] = user.pk
        request.session.pop(TWO_FACTOR_VERIFIED_SESSION_KEY, None)
        request.session[TWO_FACTOR_ATTEMPTS_SESSION_KEY] = 0
        session_key = TwoFactorSessionState._session_key(request)
        if session_key:
            cache.set(
                TwoFactorSessionState.pending_login_cache_key(user),
                session_key,
                timeout=TwoFactorSessionState.PENDING_LOGIN_TTL_SECONDS,
            )

    @staticmethod
    def mark_verified(request, user) -> None:
        if TwoFactorSessionState.is_pending(request, user):
            TwoFactorSessionState.clear_current_pending_login(request, user)
        request.session[TWO_FACTOR_VERIFIED_SESSION_KEY] = user.pk
        request.session.pop(TWO_FACTOR_PENDING_SESSION_KEY, None)
        request.session.pop(TWO_FACTOR_ATTEMPTS_SESSION_KEY, None)

    @staticmethod
    def clear(request, user=None) -> None:
        if user is not None and TwoFactorSessionState.is_pending(request, user):
            TwoFactorSessionState.clear_current_pending_login(request, user)
        request.session.pop(TWO_FACTOR_PENDING_SESSION_KEY, None)
        request.session.pop(TWO_FACTOR_VERIFIED_SESSION_KEY, None)
        request.session.pop(TWO_FACTOR_ATTEMPTS_SESSION_KEY, None)

    @staticmethod
    def is_current_pending_login(request, user) -> bool:
        session_key = TwoFactorSessionState._session_key(request)
        if not session_key:
            return False

        return cache.get(TwoFactorSessionState.pending_login_cache_key(user)) == session_key

    @staticmethod
    def clear_current_pending_login(request, user) -> None:
        session_key = TwoFactorSessionState._session_key(request)
        if not session_key:
            return

        cache_key = TwoFactorSessionState.pending_login_cache_key(user)
        if cache.get(cache_key) == session_key:
            cache.delete(cache_key)

    @staticmethod
    def is_verified(request, user) -> bool:
        return str(request.session.get(TWO_FACTOR_VERIFIED_SESSION_KEY, "")) == str(user.pk)

    @staticmethod
    def is_pending(request, user) -> bool:
        return str(request.session.get(TWO_FACTOR_PENDING_SESSION_KEY, "")) == str(user.pk)

    @staticmethod
    def failed_attempts(request) -> int:
        return int(request.session.get(TWO_FACTOR_ATTEMPTS_SESSION_KEY, 0) or 0)

    @staticmethod
    def record_failed_attempt(request) -> int:
        attempts = TwoFactorSessionState.failed_attempts(request) + 1
        request.session[TWO_FACTOR_ATTEMPTS_SESSION_KEY] = attempts
        return attempts


class TwoFactor:
    """
    Helper class for generating secret keys, provisioning URIs, 
    and QR codes for two-factor authentication (2FA).
    """

    @staticmethod
    def generate_secret_key(email: str, username: str) -> str:
        """
        Generates a secret key using the user's email, username, and server salt.

        :param email: User's email address
        :param username: User's username
        :return: Secret key in Base32 format
        """
        SERVER_SALT = settings.SERVER_SALT
        
        logger.debug("Secert key started to be generated")
        
        combined = f"{username[::-1]}:POST:{email.lower()}:{SERVER_SALT}".encode("utf-8")
        hash1 = hashlib.sha512(combined).digest()
        salted_hash = hashlib.pbkdf2_hmac("sha256", hash1, SERVER_SALT.encode("utf-8"), iterations=100_000)
        secret_key = base64.b32encode(salted_hash).decode("utf-8")[:32]
        return secret_key
    
    @staticmethod
    def verify_token(email: str, username: str, token: str) -> bool:
        
        secret_key = TwoFactor.generate_secret_key(email, username)
        totp = pyotp.TOTP(secret_key)
        
        if not totp.verify(token, valid_window=1):
            return False

        return cache.add(
            TwoFactor._used_token_cache_key(secret_key, token),
            True,
            timeout=TWO_FACTOR_USED_TOKEN_TTL_SECONDS,
        )

    @staticmethod
    def _used_token_cache_key(secret_key: str, token: str) -> str:
        digest = hashlib.sha256(f"{secret_key}:{token}".encode("utf-8")).hexdigest()
        return f"two_factor_used_totp:{digest}"

    @staticmethod
    def generate_provisioning_uri(secret_key: str, username: str, issuer: str = "FinancialManager") -> str:
        """
        Generates a provisioning URI for configuring a 2FA application.

        :param secret_key: The secret key for 2FA
        :param username: User's username
        :param issuer: The name of the service or application (default: "FinancialManager")
        :return: A provisioning URI
        """
        logger.debug("Generating provisioning URI with secret_key: ****** ")
        totp = pyotp.TOTP(secret_key)
        return totp.provisioning_uri(name=username, issuer_name=issuer)

    @staticmethod
    def generate_qr_code(provisioning_uri: str) -> str:
        """
        Generates a QR code as a Base64-encoded SVG string from the provisioning URI.

        :param provisioning_uri: The provisioning URI for the 2FA configuration
        :return: A Base64-encoded SVG string representing the QR code
        """
        logger.debug("Generating QR code for provisioning URI: *******")
        stream = BytesIO()
        img = qrcode.make(provisioning_uri, image_factory=SvgImage)
        img.save(stream)
        img_str = base64.b64encode(stream.getvalue()).decode()
        logger.debug("Generated QR code") 
        
        return img_str
