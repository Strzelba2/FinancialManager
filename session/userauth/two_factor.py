import hashlib
import base64
import pyotp
import qrcode
from io import BytesIO
from django.conf import settings
import logging

logger = logging.getLogger('session-auth')


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
        
        if totp.verify(token, valid_window=1):
            return True
        
        return False

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
        img = qrcode.make(provisioning_uri, image_factory=qrcode.image.svg.SvgImage)
        img.save(stream)
        img_str = base64.b64encode(stream.getvalue()).decode()
        logger.debug("Generated QR code") 
        
        return img_str
