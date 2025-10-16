from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission
from django.conf import settings
from utils.utils import get_client_ip, parse_allowed


import logging
logger = logging.getLogger("session-auth")


class SessionAuthenticationWithoutCSRF(SessionAuthentication):
    def enforce_csrf(self, request):
        return
    
    
class IPAllowlistPermission(BasePermission):
    message = "Your IP is not allowed."

    def has_permission(self, request, view) -> bool:
        wallet_allowed_ip = parse_allowed(getattr(settings, "ALLOWED_WALLET_IPS", ()))
        
        ip: str = get_client_ip(request)

        if ip not in wallet_allowed_ip:
            logger.error("ip is not in: wallet_allowed_ip")
            return False
        
        return True
