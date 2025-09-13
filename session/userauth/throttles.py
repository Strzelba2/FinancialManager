from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.exceptions import Throttled
from django.http import HttpRequest

from utils.utils import get_client_ip
from userauth.models import BlockedIP

import logging

logger = logging.getLogger("session-auth")


class VerifySessionThrottle(UserRateThrottle):
    """
    Throttle for verifying sessions.
    Limits requests on a per-user basis using DRF's `UserRateThrottle`.
    """
    scope = 'verify_session'


class RegisterIPThrottle(AnonRateThrottle):
    """
    Throttle for registration attempts.
    Limits requests per IP address using DRF's `AnonRateThrottle`.
    Blocks abusive IPs by creating `BlockedIP` records.
    """
    scope = 'register'

    def get_cache_key(self, request: HttpRequest, view) -> str:
        """
        Return the cache key based on client IP.

        Args:
            request (HttpRequest): Incoming request.
            view: The view being accessed.

        Returns:
            str: Cache key for rate limiting.
        """
        ip = get_client_ip(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ip
        }

    def throttle_failure(self):
        """
        Called when the request exceeds the throttle limit.
        Raises a DRF `Throttled` exception with a custom message.
        """
        logger.warning("Throttle failure: too many attempts from IP.")
        raise Throttled(detail='Too many attempts. Your IP may be temporarily blocked.')

    def throttle_request(self, request: HttpRequest, view) -> bool:
        """
        Apply the throttle logic. If the limit is exceeded, block the IP.

        Args:
            request (HttpRequest): Incoming request.
            view: The view being accessed.

        Returns:
            bool: True if allowed, False otherwise.
        """
        allowed = super().throttle_request(request, view)
        if not allowed:
            ip = get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            referer = request.META.get('HTTP_REFERER', '')
            endpoint = request.path

            blocked_ip = BlockedIP.objects.filter(ip_address=ip).first()
            if blocked_ip:
                if blocked_ip.is_temporary:
                    blocked_ip.is_temporary = False
                    blocked_ip.save(update_fields=["is_temporary"])
                    logger.error("Temporary blocked IP escalated to permanent.")
                    raise Throttled(detail='Your IP has been blocked, please contact the administrator.')
                else:
                    logger.error("Request from permanently blocked IP.")
                    raise Throttled(detail='Your IP has been permanently blocked.')

            BlockedIP.objects.create(
                ip_address=ip,
                user_agent=user_agent,
                referer=referer,
                endpoint=endpoint,
            )
            logger.error("New IP blocked due to throttle abuse.")
            
        return allowed
    
    
class LoginIPThrottle(RegisterIPThrottle):
    """
    Throttle for login attempts.
    Inherits IP-based throttling logic from `RegisterIPThrottle`.
    """
    scope = 'login'
