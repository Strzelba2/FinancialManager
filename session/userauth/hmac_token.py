from utils.utils import get_client_ip
from django.http import HttpRequest
from django.conf import settings

import hmac
import hashlib
import base64
import logging
import time


logger = logging.getLogger('session-auth')


class HmacToken:
    """
    Utility class for generating and validating HMAC tokens.
    
    This class provides methods to calculate and verify HMAC signatures using a secret token 
    and a message. It ensures secure message authentication by preventing tampering.
    """
    @staticmethod
    def calculate_token(session_id: str, request: HttpRequest, timestamp: int) -> str:
        """
        Generate a Base64-encoded HMAC token using session ID, client IP, platform, user-agent, and timestamp.

        Args:
            session_id (str): The session ID associated with the user.
            request (HttpRequest): The current Django request object.
            timestamp (int): The UNIX timestamp as a integer.

        Returns:
            str: The generated HMAC token (Base64 encoded).
        """

        message = f"{session_id}{get_client_ip(request)}{request.META.get("HTTP_SEC_CH_UA_PLATFORM", "")}"\
                  f"{request.META.get("HTTP_USER_AGENT", "")}{timestamp}"
        
        logger.debug("Calculating HMAC for message:")
        
        hmac_signature = hmac.new(settings.SERVER_SALT.encode(), message.encode(), hashlib.sha256).hexdigest()

        encoded_hmac_signature = base64.b64encode(hmac_signature.encode()).decode()

        logger.debug("HMAC token calculated successfully.")
        return encoded_hmac_signature
    
    @staticmethod
    def is_valid_hmac(provided_hmac: str, request: HttpRequest, timestamp: str) -> bool:
        """
        Validate a provided HMAC token against the expected value.

        Args:
            provided_hmac (str): The HMAC token received from the client.
            request (HttpRequest): The current Django request object.
            timestamp (str): The timestamp used to calculate the HMAC.

        Returns:
            bool: True if the token is valid and not expired, False otherwise.
        """
        try:
            last_request = int(time.time()) - int(timestamp)
        except ValueError:
            logger.warning("Invalid timestamp format in HMAC validation.")
            return False
            
        if last_request >= int(settings.VALID_HMAC):
            logger.info(f"Hmac is expired: {last_request}")
            return False
        expected_hmac = HmacToken.calculate_token(request.COOKIES.get("sessionid"), request, timestamp)

        return hmac.compare_digest(provided_hmac, expected_hmac)
    
