from django.conf import settings
from django.urls import resolve
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse


from utils.utils import get_client_ip
from userauth.models import BlockedIP, User

import logging
from typing import Callable, Iterable

logger = logging.getLogger("admin")


class AdminLoginBlockMiddleware:
    """
    Middleware protecting Django admin endpoints with:

    - IP allow-list (`settings.ADMIN_ALLOWED_IPS`)
    - Temporary/permanent IP blocking via `BlockedIP`
    - Brute-force throttling (per username and per IP) on admin login
    - 2FA gate enforcement for authenticated admin users

    Required settings:
        ADMIN_FAILURE_LIMIT: int                # failed attempts before block logic triggers
        ADMIN_TEMPORARY_BLOCK_TIME: int         # seconds TTL for attempt counters in cache
        ADMIN_ALLOWED_IPS: Iterable[str]        # IPs permitted to hit admin

    Templates expected:
        401.html, 403.html — accept: 'error', 'href', 'text'
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """
        Initialize the middleware with configuration sourced from settings.
        """
        self.get_response = get_response
        self.failure_limit: int = settings.ADMIN_FAILURE_LIMIT
        self.block_time: int = settings.ADMIN_TEMPORARY_BLOCK_TIME
        self.allowed_ips: Iterable[str] = getattr(settings, "ADMIN_ALLOWED_IPS", ())

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """
        Apply protections on admin routes:
          1) Enforce IP allow-list
          2) Deny blocked IPs
          3) Throttle login attempts (per-user and per-IP)
          4) Enforce 2FA for authenticated users where required
        Non-admin routes pass through unchanged.
        """

        resolver_match = resolve(request.path_info) 
        
        # Only act within the admin namespace 
        if resolver_match.app_name != 'admin':
            return self.get_response(request)
       
        ip: str = get_client_ip(request)
        
        # 1) IP allow-list check
        if ip not in self.allowed_ips:
            logger.warning("Admin access denied: IP not allow-listed")
            return self.forbidden_response(request, "This IP address cannot access the site")

        # 2) Blocked IP check
        if self.is_ip_blocked(ip, request):
            logger.warning("Admin access denied: IP blocked")
            return self.forbidden_response(request, "Your IP address has been blocked")
         
        # 3) Login endpoint logic   
        if resolver_match.url_name == 'login':
            if request.method == 'POST' and 'username' in request.POST:
                if not request.user.is_authenticated:
                    username = (request.POST.get("username") or "").strip()
                    user_agent = request.META.get('HTTP_USER_AGENT', '')
                    referer = request.META.get('HTTP_REFERER', '')
                    endpoint = request.path
                    user = User.objects.filter(email=username).first()
                    
                    logger.info(f"Admin login attempt for: {username}")
                    if user:
                        if user.is_blocked:
                            logger.warning(f"Blocked user: {username} attempted admin login")
                            return self.unauthorized_response(request, "You are blocked. Please contact the administrator.")
   
                        login_attempts_key = f"admin_login_attempts_{username}"
                        login_attempts = int(cache.get(login_attempts_key, 0))

                        if login_attempts >= self.failure_limit:
                            user.is_blocked = True
                            user.save(update_fields=["is_blocked"])

                            BlockedIP.objects.create(
                                ip_address=ip,
                                user_agent=user_agent,
                                referer=referer,
                                endpoint=endpoint,
                            )
                            
                            logger.error(f"Admin brute-force detected: user: {username} blocked and IP recorded")
                        else:
                            cache.set(login_attempts_key, login_attempts + 1, timeout=self.block_time)
                            logger.debug("Admin login failed counter incremented (per user)")
                            
                    else:
                        login_attempts_ip_key = f"admin_login_attempts_ip_{ip}"
                        login_attempts_ip = int(cache.get(login_attempts_ip_key, 0))
                        
                        if login_attempts_ip >= self.failure_limit:
                            BlockedIP.objects.create(
                                ip_address=ip,
                                user_agent=user_agent,
                                referer=referer,
                                endpoint=endpoint,
                            )
                            logger.error("Admin brute-force suspected from unknown account: IP recorded")
                        else:
                            logger.debug("Admin login failed counter incremented (per IP)")
                            cache.set(login_attempts_ip_key, login_attempts_ip + 1, timeout=self.block_time)
                            
                        return self.unauthorized_response(request, "You don't have permission to log in.")
          
        # 4) 2FA verify endpoint          
        elif resolver_match.url_name == 'two_factor_verify':   
            if request.user.is_authenticated:
                if request.user.is_two_factor:
                    if not request.user.is_verified:
                        logger.info("Admin 2FA verification in progress")
                        return self.get_response(request) 
            
            logger.warning("Invalid 2FA access attempt")    
            return self.unauthorized_response(request, "Invalid 2FA access.")
          
        # Other admin endpoints: enforce 2FA state              
        else:
            if request.user.is_authenticated:
                if request.user.is_two_factor:
                    if not request.user.is_verified:
                        login_attempts_2fa_key = f"admin_login_2fa_attempts_{request.user.username}"
                        login_attempts_2fa = int(cache.get(login_attempts_2fa_key, 0))
                        
                        if login_attempts_2fa <= 2:
                            logger.info("Admin 2FA required; redirecting to verify")
                            return redirect('/admin/two-factor/')
                        else:
                            logger.warning("Admin 2FA exceeded attempts; logging out")
                            logout(request)
                            return self.unauthorized_response(request, "Too many failed 2FA attempts. Please log in again.")
            else:
                logger.info("Admin access without authentication")
                return self.unauthorized_response(request, "You don't have permission. Please log in.")

        return self.get_response(request)

    def is_ip_blocked(self, ip: str, request) -> bool:
        """
        Return True if the IP exists in `BlockedIP`.

        If the record is temporary (`is_temporary=True`), convert it to permanent
        on subsequent hit and return True.
        """
        blocked_ip = BlockedIP.objects.filter(ip_address=ip).first()
        if blocked_ip:
            if blocked_ip.is_temporary:
                blocked_ip.is_temporary = False
                blocked_ip.save(update_fields=["is_temporary"])
                logger.warning("Temporary block escalated to permanent")
                return True
            return True
        return False
    
    def forbidden_response(self, request: HttpRequest, message: str) -> HttpResponse:
        """
        Render a 403 Forbidden with a consistent payload.
        """
        return render(request, '403.html', {'error': message, "href": "/admin/login/", "text": "Go to Login"}, status=403)

    def unauthorized_response(self, request: HttpRequest, message: str) -> HttpResponse:
        """
        Render a 401 Unauthorized with a consistent payload.
        """
        return render(request, '401.html', {'error': message, "href": "/admin/login/", "text": "Go to Login"}, status=401)
    
