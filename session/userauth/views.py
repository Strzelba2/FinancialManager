from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.renderers import JSONRenderer, TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.urls import reverse
from django.http import HttpResponseRedirect, HttpResponse
from django.conf import settings
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.utils import timezone
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import login, logout

from .serializers import RegisterSerializer, LoginSerializer, CryptoBatchRequest
from .throttles import (
    CryptoBatchThrottle,
    LoginIPThrottle,
    RegisterIPThrottle,
    TwoFactorManagementThrottle,
    TwoFactorVerifyThrottle,
    VerifySessionThrottle,
)
from .tokens import account_activation_token
from .models import User, UserKeys
from .two_factor import TwoFactor, TwoFactorSessionState
from .hmac_token import HmacToken
from .authentication import SessionAuthenticationWithoutCSRF, IPAllowlistPermission
from utils.utils import formatted_response, get_client_ip
from .crypto import unwrap_dek, derive_keys_from_dek, encrypt_bytes, decrypt_bytes, hmac_bytes


import logging
import time
import hashlib
from urllib.parse import unquote
import json
import base64
from datetime import timedelta

logger = logging.getLogger("session-auth")


class NextServerActionRenderer(JSONRenderer):
    """
    Renderer for Next.js Server Action ForwardAuth calls.

    The `rsc` format is intentionally non-global and only works because
    VerifySessionView lists this renderer explicitly.
    """
    media_type = "text/x-component"
    format = "rsc"


def _valid_hmac_ttl_seconds() -> int:
    return int(getattr(settings, "VALID_HMAC", 1200))


def _active_login_key(user_id) -> str:
    return f"active_login:{user_id}"


def _request_fingerprint_hash(request) -> str:
    raw = "|".join(
        [
            get_client_ip(request),
            request.META.get("HTTP_SEC_CH_UA_PLATFORM", ""),
            request.META.get("HTTP_USER_AGENT", ""),
        ]
    )
    return hashlib.sha256(f"{settings.SERVER_SALT}:{raw}".encode("utf-8")).hexdigest()


def _store_active_login(request, user) -> None:
    if not request.session.session_key:
        return

    now = int(time.time())
    cache.set(
        _active_login_key(user.pk),
        {
            "session_key": request.session.session_key,
            "fingerprint_hash": _request_fingerprint_hash(request),
            "created_at": now,
            "last_seen_at": now,
        },
        timeout=_valid_hmac_ttl_seconds(),
    )


def _clear_active_login(user_id, session_key) -> None:
    if not user_id or not session_key:
        return

    active_login = cache.get(_active_login_key(user_id))
    if active_login and active_login.get("session_key") == session_key:
        cache.delete(_active_login_key(user_id))


def _session_user_data(user) -> dict[str, str]:
    return {
        'username': user.username,
        'first_name': user.first_name,
        'email': user.email,
    }


def _set_hmac_cookie(response, request) -> None:
    timestamp = int(time.time())
    hmac = HmacToken.calculate_token(request.session.session_key, request, timestamp)
    # next-ui maps this session-auth response cookie to its browser-side `hmac` cookie.
    response.set_cookie(
        'hmac_token',
        f"{str(timestamp)}:{hmac}",
        httponly=True,
        secure=True,
        samesite='Lax',
    )


def _login_success_response(request, user, message="Login successful") -> Response:
    response = Response({"message": message}, status=status.HTTP_200_OK)
    _set_hmac_cookie(response, request)
    # Keep the cached identity tied to the user approved by the login or 2FA flow.
    cache.set(
        f'session:{request.session.session_key}',
        _session_user_data(user),
        timeout=3600,
    )
    _store_active_login(request, user)
    return response


def _request_requires_two_factor(request, user) -> bool:
    return getattr(user, "is_two_factor", False) and not TwoFactorSessionState.is_verified(request, user)


def _clean_two_factor_token(value) -> str | None:
    if not isinstance(value, str):
        return None

    token = value.strip().replace(" ", "")
    if not token.isdigit() or len(token) != 6:
        return None

    return token


class RegisterView(APIView):
    """
    Public endpoint to register a new user account.

    - No authentication required.
    - Rate-limited per IP (see RegisterIPThrottle).
    - On success, sends an activation email with a time-bound token.
    """
    authentication_classes = [] 
    permission_classes = [AllowAny] 
    throttle_classes = [RegisterIPThrottle]
    serializer_class = RegisterSerializer
    renderer_classes = [JSONRenderer]
    
    def send_email(self, user: User, link: str) -> None:
        """
        Compose and send the activation email.

        Args:
            user: The newly created user.
            link: Activation URL (contains uidb64 and token).

        Returns:
            None
        """
        logger.info("Preparing email for user .")
        
        subject = f"Activate account for {user.username}"
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [user.email]
        context = {
            "user": user,
            "link": link,
        }
        html_email = render_to_string("activate_email.html", context)
        text_email = strip_tags(html_email)

        email = EmailMultiAlternatives(subject, text_email, from_email, recipient_list)
        email.attach_alternative(html_email, "text/html")
        email.send()
        logger.info("Activation email sent.")
          
    def post(self, request, *args, **kwargs) -> Response:
        """
        Handle registration:
          1) Validate payload with RegisterSerializer
          2) Create user in an atomic transaction
          3) Queue activation email on transaction commit
          4) Return a generic 201 message (no info leakage)

        Returns:
            DRF Response with 201 on success or an error status.
        """
        try:
            logger.info(f'RegisterView called from IP: {request.META.get("REMOTE_ADDR")}')
        
            serializer = self.serializer_class(data=request.data)
            if serializer.is_valid():
                try:
                    with transaction.atomic():
                        user = serializer.save()
                        uid = urlsafe_base64_encode(force_bytes(user.pk))
                        token = account_activation_token.make_token(user)
                        activation_link = f"{settings.APP_PROTOCOL}://{settings.SESSION_DOMAIN}"\
                                          f"{reverse('activate', kwargs={'uidb64': uid, 'token': token})}"
                        
                        def send_mail_after_commit():
                            try:
                                self.send_email(user, activation_link)
                            except Exception as e:
                                logger.error(f"Failed to send activation email: {e}")
                                return Response({"error": "Failed to send activation email."}, 
                                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                            
                        transaction.on_commit(send_mail_after_commit)

                    return Response({"message": "If your email is valid, we sent you an activation link."},
                                    status=status.HTTP_201_CREATED)
                    
                except Exception as e:
                    logger.error(f"Exception during registration: {e}")
                    return Response({"error": "Registration failed. Try again later."}, 
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                logger.error(f"serializer error: {serializer.errors}")
                return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Unexpected Exceptions: {e}")
            return Response({"error": "Unexpected Exceptions"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        
class ActivateAccountView(APIView):
    """
    Endpoint for activating a newly registered account via tokenized URL.

    Validates uidb64 + token, and if correct:
      - Activates the user (if inactive).
      - Redirects to login page with success/failure flags.
    """
    authentication_classes = []
    permission_classes = [AllowAny]    

    def get(self, request, uidb64: str, token: str, *args, **kwargs) -> HttpResponseRedirect:
        """
        Handle GET request for account activation.

        Args:
            request: Django request object.
            uidb64: Base64 encoded user ID.
            token: Account activation token.

        Returns:
            HttpResponseRedirect: Redirect to login page with activation status.
        """
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            logger.warning("Invalid activation link or user not found.")
            user = None
            
        if user is not None and account_activation_token.check_token(user, token):
            if not user.is_active:
                logger.info("user is not active")
                user.is_active = True
                user.save(update_fields=["is_active"])
                logger.info("User account activated successfully.")
                return HttpResponseRedirect(f"{settings.APP_PROTOCOL}://{settings.WALLET_DOMAIN}/login?already_activated=true")
        else:
            logger.warning("Invalid or expired activation token.")
            return HttpResponseRedirect(f"{settings.APP_PROTOCOL}://{settings.WALLET_DOMAIN}/login?already_activated=false")


class LoginView(APIView):
    """
    Public login endpoint with:
      - Throttling per IP and email
      - Brute-force protection (temporary/permanent block)
      - HMAC session token generation
      - Optional 2FA enforcement
    """
    
    authentication_classes = [] 
    permission_classes = [AllowAny] 
    throttle_classes = [LoginIPThrottle]
    serializer_class = LoginSerializer
    renderer_classes = [JSONRenderer]

    def _cache_ttl_seconds(self, key, fallback=None):
        """
        Return the remaining TTL for a cache key in seconds.

        Uses django-redis' `ttl()` when available and falls back to the provided
        value if the TTL cannot be determined.
        """
        try:
            ttl = cache.ttl(key)
        except Exception as e:
            logger.warning(f"Could not read cache TTL for {key}: {e}")
            return fallback

        if ttl is None or ttl < 0:
            return fallback

        return int(ttl)

    def _format_retry_after(self, seconds):
        """
        Convert a number of seconds into a short human-readable duration.
        """
        total_seconds = max(int(seconds or 0), 0)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)

        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if secs or not parts:
            parts.append(f"{secs}s")
        return " ".join(parts)

    def _temporary_block_response(self, email, login_attempts_key):
        """
        Build a 429 response with the remaining temporary block duration.
        """
        retry_after_seconds = self._cache_ttl_seconds(
            login_attempts_key,
            fallback=settings.USER_TEMPORARY_BLOCK_TIME,
        )
        retry_after_human = self._format_retry_after(retry_after_seconds)
        blocked_until = timezone.localtime(
            timezone.now() + timedelta(seconds=retry_after_seconds)
        ).isoformat()

        logger.warning(
            "Too many login attempts. Retry after %ss (until %s).",
            retry_after_seconds,
            blocked_until,
        )

        return Response(
            {
                "error": f"Too many login attempts. Try again in {retry_after_human}.",
                "retry_after_seconds": retry_after_seconds,
                "retry_after_human": retry_after_human,
                "blocked_until": blocked_until,
                "blocked_permanently": False,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def _permanent_block_response(self, email):
        """
        Build a 429 response for a permanently blocked user.
        """
        logger.error("User has been permanently blocked after repeated login failures.")
        return Response(
            {
                "error": "Too many login attempts. User has been blocked permanently. Contact the administrator.",
                "retry_after_seconds": None,
                "retry_after_human": None,
                "blocked_until": None,
                "blocked_permanently": True,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def _record_failed_login_attempt(self, login_attempts_key, login_attempts):
        cache.set(
            login_attempts_key,
            login_attempts + 1,
            timeout=settings.USER_TEMPORARY_BLOCK_TIME,
        )

    def _concurrent_login_response(self, email, login_attempts_key, login_attempts):
        self._record_failed_login_attempt(login_attempts_key, login_attempts)
        logger.warning("Concurrent login attempt rejected for active session.")
        return Response(
            {
                "error": (
                    "Konto jest już aktywne na innym urządzeniu. "
                    "Wyloguj się z poprzedniego urządzenia albo spróbuj ponownie za kilka minut."
                ),
                "blocked_permanently": False,
            },
            status=status.HTTP_409_CONFLICT,
        )
    
    def post(self, request, *args, **kwargs):
        """
        Handle login request. On success:
          - Authenticates user
          - Generates HMAC session cookie when 2FA is not required
          - Clears login attempt counters
          - Returns a JSON 2FA challenge when required

        Returns:
            Response: Success message or error response.
        """
        try:
            logger.info("Login attempt received.")
            serializer = self.serializer_class(data=request.data)
            
            email = request.data.get('email')
            
            login_attempts_key = f"login_attempts_{email}"
            login_attempts = cache.get(login_attempts_key, 0)
            
            too_many_login_attempts_key = f"too_many_login_attempts_{email}"
            too_many_login_attempts = cache.get(too_many_login_attempts_key, 0)
            logger.debug("Login attempts checked.")
          
            if login_attempts >= 3:
                cache.set(
                    too_many_login_attempts_key,
                    too_many_login_attempts + 1,
                    timeout=settings.USER_TEMPORARY_BLOCK_TIME * 2,
                )

                if too_many_login_attempts >= 2:
                    user = User.objects.filter(email=email).first()
                    if user:
                        if not user.is_blocked:
                            user.is_blocked = True
                            user.save(update_fields=["is_blocked"])
                    
                    return self._permanent_block_response(email)
                    
                return self._temporary_block_response(email, login_attempts_key)

            if serializer.is_valid():
                logger.info("Login serializer validated.")
                user = serializer.validated_data['user']
                
                if user.is_blocked:
                    logger.warning("Blocked user attempted login.")
                    return Response(
                        {
                            'error': 'Your account has been blocked permanently. Contact the administrator.',
                            'retry_after_seconds': None,
                            'retry_after_human': None,
                            'blocked_until': None,
                            'blocked_permanently': True,
                        },
                        status=status.HTTP_401_UNAUTHORIZED,
                    )

                active_login = cache.get(_active_login_key(user.pk))
                fingerprint_hash = _request_fingerprint_hash(request)
                if active_login and active_login.get("fingerprint_hash") != fingerprint_hash:
                    return self._concurrent_login_response(
                        email,
                        login_attempts_key,
                        login_attempts,
                    )

                try:  
                    login(request, user)  
                except Exception as e:
                    logger.error(f"Login error for user : {str(e)}")
                    return Response({'error': 'Login failed.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
                cache.delete(too_many_login_attempts_key)
                cache.delete(login_attempts_key)
                
                if getattr(user, "is_two_factor", False):
                    TwoFactorSessionState.mark_pending(request, user)
                    logger.info("Login requires two-factor verification.")
                    return Response(
                        {"requires_two_factor": True},
                        status=status.HTTP_202_ACCEPTED,
                    )

                TwoFactorSessionState.clear(request, user)
                response = _login_success_response(request, user)
                
                logger.info("Login successful.")
                return response
        
            else:
                self._record_failed_login_attempt(login_attempts_key, login_attempts)
                logger.warning("Invalid login payload.")
                return Response({"error": serializer.errors},
                                status=status.HTTP_401_UNAUTHORIZED)
        
        except Exception as e:
            logger.error(f"Unexpected Exceptions: {e}")
            return Response({"error": "Unexpected Exceptions"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LogoutView(APIView):
    """
    Log the user out of the current session.

    - Requires an authenticated session.
    - Clears Django session and deletes the HMAC session cookie.
    """
    authentication_classes = [SessionAuthenticationWithoutCSRF]
    permission_classes = (IsAuthenticated,)
    
    def post(self, request, *args, **kwargs) -> Response:
        """
        POST: Terminate the user session and clear the HMAC cookie.

        Returns:
            200 OK with a generic success message.
        """
        logger.info("Logout requested.")
        user_id = getattr(request.user, "pk", None)
        session_key = request.session.session_key
        try:
            logout(request)
            _clear_active_login(user_id, session_key)
            logger.info("Logout successful; session flushed.")
        except Exception:
            logger.warning("Logout error.", exc_info=True)
                
        response = Response({"message": "Logout successful"}, status=status.HTTP_200_OK)
        response.delete_cookie("hmac", path="/", samesite='Lax')
        return response


class VerifySessionView(APIView):
    """
    Verify the integrity of the current session via an HMAC cookie.

    Flow:
      - Ensure required cookies are present.
      - Require authenticated user.
      - Parse and validate HMAC (timestamp + signature).
      - If valid, issue a refreshed HMAC cookie and return JSON.
    """
    permission_classes = [AllowAny] 
    throttle_classes = [VerifySessionThrottle]
    renderer_classes = [JSONRenderer, TemplateHTMLRenderer, NextServerActionRenderer]

    def _login_url(self, request) -> str:
        """
        Return the correct login URL based on which frontend made the request.

        Traefik ForwardAuth copies the original request headers, so
        X-Forwarded-Host contains the browser-facing hostname (e.g.
        'next.localhost:8081' or 'wallet.localhost:8081').  We strip the port
        and compare the bare hostname against NEXT_UI_DOMAIN to decide whether
        to redirect to the Next.js frontend or the legacy NiceGUI frontend.
        """
        forwarded_host = request.META.get("HTTP_X_FORWARDED_HOST", "").split(":")[0]
        next_host = (settings.NEXT_UI_DOMAIN or "").split(":")[0]

        logger.debug(f"Forwarded host: {forwarded_host}, Next.js host: {next_host}")

        if next_host and forwarded_host == next_host:
            domain = settings.NEXT_UI_DOMAIN
        else:
            domain = settings.UI_DOMAIN

        return f"{settings.APP_PROTOCOL}://{domain}/login"

    def _two_factor_url(self, request) -> str:
        forwarded_host = request.META.get("HTTP_X_FORWARDED_HOST", "").split(":")[0]
        next_host = (settings.NEXT_UI_DOMAIN or "").split(":")[0]

        if next_host and forwarded_host == next_host:
            domain = settings.NEXT_UI_DOMAIN
        else:
            domain = settings.UI_DOMAIN

        return f"{settings.APP_PROTOCOL}://{domain}/two-factor"
    
    def get(self, request, *args, **kwargs):
        """
        GET: Verify session via HMAC cookie and refresh it on success.

        Returns:
            - 200 JSON with a fresh cookie if valid.
            - Redirects / error pages on failure.
        """
        logger.info("VerifySessionView called.")
        session_id = request.COOKIES.get("sessionid")
        hmac_token = request.COOKIES.get("hmac")
        
        logger.debug("Session verification HMAC cookie presence checked.")
        
        login_url = self._login_url(request)

        if not session_id or not hmac_token:
            logger.warning("Missing authorization data for session verification.")
            return formatted_response(request,
                                      {"error": "Missing authorizaton data.",
                                       "href": login_url,
                                       "text": "Go to Login"},
                                      template_name="401.html",
                                      status=401)
            
        if not request.user or not request.user.is_authenticated:
            logger.info("Unauthenticated user during session verification; redirecting.")
            return HttpResponseRedirect(login_url)

        if _request_requires_two_factor(request, request.user):
            logger.info("Two-factor verification required during session verification.")
            return HttpResponseRedirect(self._two_factor_url(request))
        
        try:
            timestamp, provided_hmac = unquote(hmac_token).strip('"').split(":")
            logger.debug("Session verification HMAC token parsed.")
        except Exception:
            logger.warning("Failed to parse HMAC token.")
            return formatted_response(request,
                                      {"error": "Invalid HMAC format.",
                                       "href": login_url,
                                       "text": "Go to Login"},
                                      template_name="400.html",
                                      status=400)
        
        if not HmacToken.is_valid_hmac(provided_hmac, request, timestamp):
            logger.warning("HMAC verification failed.")
            logout(request)
            response = HttpResponseRedirect(login_url)
            return response
        
        timestamp = int(time.time())

        hmac = HmacToken.calculate_token(session_id, request, timestamp)
        
        response = HttpResponse(
            json.dumps({"message": "verify_session"}),
            content_type="application/json",
            status=200
        )
                
        response.set_cookie(
            'hmac',
            f"{str(timestamp)}:{hmac}",
            httponly=True,
            secure=True,
            samesite='Lax',
        )
        response.headers["X-User"] = request.user.username
        response.headers["X-First-Name"] = request.user.first_name or ""
        response.headers["X-Email"] = request.user.email or ""
        response.headers["X-User-Id"] = request.session.get('wallet_user_id', '')
        _store_active_login(request, request.user)

        logger.debug(f"header User: {response.headers['X-User']}")
        logger.debug(f"header User-Id: {response.headers['X-User-Id']}")
        return response


class SetWalletUserIdView(APIView):
    """
    Store the wallet service user_id in the current session.

    Called by Next.js after syncUser() resolves — allows VerifySessionView
    to forward X-User-Id to all downstream services without each page
    having to call syncUser independently.
    """
    authentication_classes = [SessionAuthenticationWithoutCSRF]
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        logger.info("SetWalletUserIdView called.")
        wallet_user_id = request.data.get('wallet_user_id', '')
        if not wallet_user_id:
            return Response(
                {"error": "wallet_user_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.session['wallet_user_id'] = wallet_user_id
        logger.info("wallet_user_id saved to session.")
        return Response({"ok": True}, status=status.HTTP_200_OK)


class TwoFactorStatusView(APIView):
    """
    Return the current user's 2FA status for frontend settings screens.
    """
    authentication_classes = [SessionAuthenticationWithoutCSRF]
    permission_classes = [IsAuthenticated]
    throttle_classes = [VerifySessionThrottle]
    renderer_classes = [JSONRenderer]

    def get(self, request, *args, **kwargs) -> Response:
        return Response(
            {"is_two_factor_enabled": bool(getattr(request.user, "is_two_factor", False))},
            status=status.HTTP_200_OK,
        )


class TwoFactorSetupView(APIView):
    """
    Generate a QR code for the current user without enabling 2FA yet.
    """
    authentication_classes = [SessionAuthenticationWithoutCSRF]
    permission_classes = [IsAuthenticated]
    throttle_classes = [TwoFactorManagementThrottle]
    renderer_classes = [JSONRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        user = request.user
        if _request_requires_two_factor(request, user):
            return Response(
                {"error": "Two-factor authentication is required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        secret_key = TwoFactor.generate_secret_key(email=user.email, username=user.username)
        provisioning_uri = TwoFactor.generate_provisioning_uri(secret_key, username=user.username)
        qr_code_image = TwoFactor.generate_qr_code(provisioning_uri)

        logger.info("2FA setup QR code generated.")
        return Response(
            {
                "image": qr_code_image,
                "is_two_factor_enabled": bool(getattr(user, "is_two_factor", False)),
            },
            status=status.HTTP_200_OK,
        )


class TwoFactorEnableView(APIView):
    """
    Enable 2FA only after the current user proves possession of a valid TOTP code.
    """
    authentication_classes = [SessionAuthenticationWithoutCSRF]
    permission_classes = [IsAuthenticated]
    throttle_classes = [TwoFactorManagementThrottle]
    renderer_classes = [JSONRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        user = request.user
        if _request_requires_two_factor(request, user):
            return Response(
                {"error": "Two-factor authentication is required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = _clean_two_factor_token(request.data.get("token"))
        if not token:
            return Response({"error": "A valid 6-digit token is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not TwoFactor.verify_token(user.email, user.username, token):
            return Response({"error": "Invalid 2FA code."}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_two_factor:
            user.is_two_factor = True
            user.save(update_fields=["is_two_factor"])

        TwoFactorSessionState.mark_verified(request, user)
        logger.info("User enabled 2FA.")
        return Response({"is_two_factor_enabled": True}, status=status.HTTP_200_OK)


class TwoFactorDisableView(APIView):
    """
    Disable 2FA after the current user confirms a valid TOTP code.

    This intentionally does not use `_request_requires_two_factor`: a user with
    an authenticated pending-2FA session can disable 2FA only after proving TOTP
    possession, while setup and enable still require a fully verified session.
    """
    authentication_classes = [SessionAuthenticationWithoutCSRF]
    permission_classes = [IsAuthenticated]
    throttle_classes = [TwoFactorManagementThrottle]
    renderer_classes = [JSONRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        user = request.user
        token = _clean_two_factor_token(request.data.get("token"))
        if not token:
            return Response({"error": "A valid 6-digit token is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not TwoFactor.verify_token(user.email, user.username, token):
            return Response({"error": "Invalid 2FA code."}, status=status.HTTP_401_UNAUTHORIZED)

        if user.is_two_factor or getattr(user, "is_verified", False):
            user.is_two_factor = False
            # `is_verified` is retained for the legacy Django admin 2FA flow.
            # Next UI web sessions use TwoFactorSessionState instead.
            user.is_verified = False
            user.save(update_fields=["is_two_factor", "is_verified"])

        TwoFactorSessionState.clear(request, user)
        logger.info("User disabled 2FA.")
        return Response({"is_two_factor_enabled": False}, status=status.HTTP_200_OK)


class TwoFactorVerifyView(APIView):
    """
    Verify a pending 2FA login and issue the HMAC cookie only after TOTP succeeds.
    """
    authentication_classes = [SessionAuthenticationWithoutCSRF]
    permission_classes = [IsAuthenticated]
    throttle_classes = [TwoFactorVerifyThrottle]
    renderer_classes = [JSONRenderer]

    def post(self, request, *args, **kwargs) -> Response:
        user = request.user
        if not getattr(user, "is_two_factor", False):
            TwoFactorSessionState.clear(request, user)
            return Response(
                {"error": "Two-factor authentication is not enabled for this user."},
                status=status.HTTP_409_CONFLICT,
            )

        if TwoFactorSessionState.is_verified(request, user):
            return Response(
                {"error": "Two-factor verification is already complete for this session."},
                status=status.HTTP_409_CONFLICT,
            )

        if not TwoFactorSessionState.is_pending(request, user):
            return Response(
                {"error": "Two-factor verification is not pending for this session."},
                status=status.HTTP_409_CONFLICT,
            )

        if not TwoFactorSessionState.is_current_pending_login(request, user):
            TwoFactorSessionState.clear(request, user)
            logout(request)
            return Response(
                {"error": "Two-factor verification expired. Please log in again."},
                status=status.HTTP_409_CONFLICT,
            )

        token = _clean_two_factor_token(request.data.get("token"))
        if not token:
            return Response({"error": "A valid 6-digit token is required."}, status=status.HTTP_400_BAD_REQUEST)

        attempts = TwoFactorSessionState.failed_attempts(request)
        if attempts >= TwoFactorSessionState.MAX_ATTEMPTS:
            TwoFactorSessionState.clear(request, user)
            logout(request)
            return Response(
                {"error": "Too many failed 2FA attempts. Please log in again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not TwoFactor.verify_token(user.email, user.username, token):
            attempts = TwoFactorSessionState.record_failed_attempt(request)
            if attempts >= TwoFactorSessionState.MAX_ATTEMPTS:
                logger.warning("Too many failed user 2FA attempts. Logging out.")
                TwoFactorSessionState.clear(request, user)
                logout(request)
                return Response(
                    {"error": "Too many failed 2FA attempts. Please log in again."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            return Response({"error": "Invalid 2FA code."}, status=status.HTTP_401_UNAUTHORIZED)

        TwoFactorSessionState.mark_verified(request, user)
        response = _login_success_response(request, user, message="Two-factor verification successful")
        logger.info("2FA verification successful.")
        return response


class QRCodeView(APIView):
    """
    View to generate and display a QR code for two-factor authentication.

    This view handles:
    - Validating the signed token.
    - Checking for expired or used tokens.
    - Generating a QR code based on a valid token.

    Methods:
        - `get`: Handles GET requests to process the token and return the QR code.
    """
    
    permission_classes = [IsAdminUser] 
    renderer_classes = [TemplateHTMLRenderer] 

    def get(self, request, token: str) -> Response:
        """
        GET: Generate a provisioning URI and QR image for the authenticated user.

        Args:
            token: (Currently unused in generation; present for routing/compatibility.)

        Returns:
            Response: Template render containing the QR image.
        """
        logger.info("Starting qrcode view process for user.")
        
        user = request.user
        secret_key = TwoFactor.generate_secret_key(email=user.email, username=user.username)
        provisioning_uri = TwoFactor.generate_provisioning_uri(secret_key, username=user.username)
        qr_code_image = TwoFactor.generate_qr_code(provisioning_uri)

        logger.info(f"QR code successfully generated for user: {user.username}")
        return Response({'image': qr_code_image}, template_name='admin/qrcode.html')
   
    
class CryptoBatchView(APIView):
    """
    API endpoint for batch cryptographic operations (encrypt, decrypt, hmac).
    
    This view receives a batch of crypto operations tied to a specific user and:
    - decrypts their Data Encryption Key (DEK)
    - derives encryption and HMAC keys
    - executes requested crypto operations (AES-GCM or HMAC-SHA256)
    """

    authentication_classes = []
    permission_classes = [IPAllowlistPermission]
    throttle_classes = [CryptoBatchThrottle]
    serializer_class = CryptoBatchRequest
    renderer_classes = [JSONRenderer]
    
    def post(self, request, *args, **kwargs) -> Response:
        """
        Handles POST request with batch crypto operations.

        Returns:
            - 200 OK with results if successful
            - 400 Bad Request if validation fails
            - 401 Unauthorized if user is invalid
            - 404 Not Found if user's keys are missing
        """
        logger.info("CryptoBatchView: Received crypto batch request.")
        
        serializer = self.serializer_class(data=request.data)
        
        if serializer.is_valid():
            
            username = serializer.validated_data["username"]
            data = serializer.validated_data["data"]
            
            try:
                user = User.objects.get(username=username)
            except (TypeError, ValueError, OverflowError, User.DoesNotExist):
                logger.warning(f"CryptoBatchView: Invalid user '{username}'.")
                return Response({"error": "user do not exist"},
                                status=status.HTTP_401_UNAUTHORIZED)
                
            try:
                uk = UserKeys.objects.get(user=user)
            except UserKeys.DoesNotExist:
                logger.warning(f"CryptoBatchView: User keys not found for '{username}'.")
                return Response({"detail": "user keys not found"}, status=status.HTTP_404_NOT_FOUND)
            
            dek = unwrap_dek(uk.wrapped_dek_nonce, uk.wrapped_dek_ct)
            
            enc_key, mac_key = derive_keys_from_dek(dek)
            
            results = []
            for op in data:
                oid, kind = op["id"], op["kind"]
                try:
                    if kind == "encrypt":
                        pt = base64.b64decode(op["plaintext_b64"])
                        nonce, ct = encrypt_bytes(enc_key, pt)
                        results.append({
                            "id": oid, "ok": True,
                            "nonce_b64": base64.b64encode(nonce).decode(),
                            "ciphertext_b64": base64.b64encode(ct).decode(),
                        })
                        
                    elif kind == "hmac":
                        pt = base64.b64decode(op["plaintext_b64"])
                        dig = hmac_bytes(mac_key, pt)
                        results.append({"id": oid, "ok": True, "digest_b64": base64.b64encode(dig).decode()})
                        
                    elif kind == "decrypt":
                        nonce = base64.b64decode(op["nonce_b64"])
                        ct = base64.b64decode(op["ciphertext_b64"])
                        pt = decrypt_bytes(enc_key, nonce, ct)
                        results.append({"id": oid, "ok": True, "plaintext_b64": base64.b64encode(pt).decode()})
                        
                    else:
                        logger.warning(f"CryptoBatchView: Unsupported crypto kind: {kind}")
                        results.append({"id": oid, "ok": False, "error": "unsupported"})
                except Exception:
                    logger.error(f"CryptoBatchView: Error in operation {oid}: {e}")
                    results.append({"id": oid, "ok": False, "error": "crypto_error"})
                    
            return Response({"results": results})
            
        else:
            logger.error(f"CryptoBatchView: Invalid request data: {serializer.errors}")
            return Response({"error": serializer.errors},
                             status=status.HTTP_400_BAD_REQUEST)
