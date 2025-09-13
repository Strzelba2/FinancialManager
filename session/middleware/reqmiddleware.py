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
        
        if path in ["admin", "static", "activate"]:
            return self.get_response(request)

        blocked_ip = BlockedIP.objects.filter(ip_address=ip).first()
        if blocked_ip:
            logger.warning(f"Blocked IP tried to access: {ip}")
            if not blocked_ip.is_temporary:
                return formatted_response(request,
                                          {"error": "Your IP has been blocked, please contact the administrator.",
                                           "href": f"http://{settings.WALLET_DOMAIN}/home",
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
            if parsed.netloc != settings.WALLET_DOMAIN:
                logger.warning("Invalid referer domain")
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
                    return HttpResponseRedirect(f"http://{settings.WALLET_DOMAIN}/two_factor")
        else:
            logger.info("Unauthenticated access attempt")
            return formatted_response(request,
                                      {'error': 'User do not have permison to this site, Please login',
                                       "href": f"http://{settings.WALLET_DOMAIN}/login",
                                       "text": "Go to Login"},
                                      template_name="401.html",
                                      status=401)
        
        return self.get_response(request)
