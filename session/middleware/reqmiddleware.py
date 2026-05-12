from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from urllib.parse import urlparse
from user_agents import parse
from typing import Callable

from userauth.models import BlockedIP
from utils.utils import get_client_ip, formatted_response

import logging

logger = logging.getLogger("session-auth")


class RequestMiddleware:
    """
    Middleware to validate client requests before accessing protected resources.

    Validations include:
    - IP address blocking
    - Missing or bot-like User-Agent
    - Referer header validation for login/register routes
    - Two-factor authentication enforcement
    - Authenticated access enforcement

    If any of the above fail, the middleware returns a formatted error response
    instead of continuing the request.
    """
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """
        Initialize the middleware with the next callable in the middleware chain.

        Args:
            get_response: The next middleware or view to handle the request.
        """
        self.get_response = get_response

    def _get_ui_domain(self, request) -> str:
        logger.debug(f"Extracting UI domain from request headers: {request.META}")

        referer = request.META.get("HTTP_REFERER", "")
        if referer:
            referer_host = urlparse(referer).netloc.split(":")[0]
        else:
            referer_host = request.META.get("HTTP_X_FORWARDED_HOST", "").split(":")[0]

        next_host = (settings.NEXT_UI_DOMAIN or "").split(":")[0]
        logger.debug(f"Referer host: {referer_host}, Next UI host: {next_host}")

        if next_host and referer_host == next_host:
            domain = settings.NEXT_UI_DOMAIN
        else:
            domain = settings.UI_DOMAIN

        return domain

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """
        Process the incoming request. If checks fail, return an error response.

        Args:
            request: Incoming HttpRequest object.

        Returns:
            HttpResponse: Either an error page or the normal response.
        """
        
        ip = get_client_ip(request)
        user_agent_str = request.META.get("HTTP_USER_AGENT", "")
        referer = request.META.get("HTTP_REFERER", "")
        path = request.META.get("PATH_INFO", "").strip('/').split('/')[0]
        logger.debug(f"Incoming request from IP: {ip}, User-Agent: {user_agent_str}, Referer: {referer}, Path: {path}")

        domain = self._get_ui_domain(request)

        logger.debug(f"Determined domain for request: {domain}")

        
        if path in ["admin", "static", "activate", "crypto", "healthz", "readyz"]:
            return self.get_response(request)

        blocked_ip = BlockedIP.objects.filter(ip_address=ip).first()
        if blocked_ip:
            logger.warning(f"Blocked IP tried to access: {ip}")
            if not blocked_ip.is_temporary:
                return formatted_response(request,
                                          {"error": "Your IP has been blocked, please contact the administrator.",
                                           "href": f"{settings.APP_PROTOCOL}://{domain}/home",
                                           "text": "Go Home Page"},
                                          template_name="403.html",
                                          status=403,
                                          )
        if not user_agent_str:
            logger.warning("Missing User-Agent header")
            return formatted_response(request,
                                      {"error": "The User-Agent header is missing.",
                                       "href": "javascript:history.back()",
                                       "text": "Go Back"},
                                      template_name="400.html",
                                      status=400)
        ua = parse(user_agent_str)
        if ua.is_bot:
            logger.warning("Bot detected and blocked")
            return formatted_response(request,
                                      {"error": "Bots are blocked.",
                                       "href": "javascript:history.back()",
                                       "text": "Go Back"},
                                      template_name="403.html",
                                      status=403)
        if path in ["login", "register"]:
            if not referer:
                logger.warning("Missing Referer header on login/register attempt")
                return formatted_response(request,
                                          {"error": "Missing referer header.",
                                           "href": "javascript:history.back()",
                                           "text": "Go Back"},
                                          template_name="400.html",
                                          status=400)
        
            parsed = urlparse(referer)
            allowed_domains = {
                getattr(settings, "WALLET_DOMAIN", ""),
                getattr(settings, "UI_DOMAIN", ""),
                getattr(settings, "NEXT_UI_DOMAIN", ""),
            }

            allowed_domains = {domain for domain in allowed_domains if domain}
            logger.info(f"Allowed domains for referer: {allowed_domains}")
            logger.info(f"Referer domain: {parsed.netloc}")
            if parsed.netloc not in allowed_domains:
                logger.warning(f"Invalid referer domain: {parsed.netloc}")
                return formatted_response(request,
                                          {"error": "Incorrect request",
                                           "href": "javascript:history.back()",
                                           "text": "Go Back"},
                                          template_name="400.html",
                                          status=400)
            
            return self.get_response(request)

        if request.user.is_authenticated:
            if request.user.is_two_factor:
                if not request.user.is_verified:
                    logger.info("Redirecting unverified 2FA user to verification page")
                    return HttpResponseRedirect(f"{settings.APP_PROTOCOL}://{domain}/two_factor")
        else:
            logger.info("Unauthenticated access attempt")
            return formatted_response(request,
                                      {'error': 'User do not have permison to this site, Please login',
                                       "href": f"{settings.APP_PROTOCOL}://{domain}/login",
                                       "text": "Go to Login"},
                                      template_name="401.html",
                                      status=401)
        
        return self.get_response(request)
