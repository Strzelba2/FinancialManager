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
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import login, logout

from .serializers import RegisterSerializer, LoginSerializer
from .throttles import VerifySessionThrottle, RegisterIPThrottle, LoginIPThrottle
from .tokens import account_activation_token
from .models import User
from .two_factor import TwoFactor
from .hmac_token import HmacToken
from .authentication import SessionAuthenticationWithoutCSRF
from utils.utils import formatted_response


import logging
import time
from urllib.parse import unquote
import json

logger = logging.getLogger("session-auth")


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
    
    def post(self, request, *args, **kwargs):
        """
        Handle login request. On success:
          - Authenticates user
          - Generates HMAC session cookie
          - Clears login attempt counters
          - Redirects to 2FA if required

        Returns:
            Response: Success message or error response.
        """
        try:
            logger.info("Login attempt received.")
            serializer = self.serializer_class(data=request.data)
            
            email = request.data.get('email')
            
            login_attempts_key = f"login_attempts_{email}"
            login_attempts = cache.get(login_attempts_key, 0)
            
            to_many_login_attempts_key = f"to_many_login_attempts_{email}"
            to_many_login_attempts = cache.get(to_many_login_attempts_key, 0)
          
            if login_attempts >= 3:
                cache.set(to_many_login_attempts_key, to_many_login_attempts + 1, timeout=settings.USER_TEMPORARY_BLOCK_TIME*2)
                logger.warning("Too many login attempts for user:")

                if to_many_login_attempts >= 2:   
                    user = User.objects.filter(email=email).first()
                    if user:
                        if not user.is_blocked:
                            user.is_blocked = True
                            user.save(update_fields=["is_blocked"])
                            logger.error("User permanently blocked due to repeated login failures.")
                    
                    return Response(
                        {"error": "Too many login attempts.User has been blocked."},
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )
                    
                return Response(
                    {"error": "Too many login attempts. Try again later."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            if serializer.is_valid():
                logger.info("Login serializer validated.")
                user = serializer.validated_data['user']
                
                if user.is_blocked:
                    logger.warning("Blocked user attempted login.")
                    return Response({'error': 'Your account has been blocked.'},
                                    status=status.HTTP_401_UNAUTHORIZED)
                try:  
                    login(request, user)  
                except Exception as e:
                    logger.error(f"Login error for user : {str(e)}")
                    return Response({'error': 'Login failed.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                timestamp = int(time.time())

                hmac = HmacToken.calculate_token(request.session.session_key, request, timestamp)
                
                cache.delete(to_many_login_attempts_key)
                cache.delete(login_attempts_key)
                
                if getattr(user, "is_two_factor", False):
                    if not getattr(user, "is_verified", False):
                        logger.info("Redirecting to 2FA verification.")
                        return HttpResponseRedirect(f"http://{settings.WALLET_DOMAIN}/two_factor")

                response = Response({"message": "Login successful"}, status=status.HTTP_200_OK)
                
                response.set_cookie(
                    'hmac_token',
                    f"{str(timestamp)}:{hmac}",
                    httponly=True,
                    samesite='Lax',
                )
                user_data = {
                    'username': request.user.username,
                    'id': request.user.id,
                    'email': request.user.email,
                }
                cache.set(f'session:{request.session.session_key}', user_data, timeout=3600)
                
                logger.info("Login successful.")
                return response
        
            else:
                cache.set(login_attempts_key, login_attempts + 1, timeout=settings.USER_TEMPORARY_BLOCK_TIME)
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
        try:
            logout(request)
            request.session.flush()
            logger.info("Logout successful; session flushed.")
        except Exception as e:
            logger.info(f"Exceprions from logout: {e}")
                
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
        
        logger.info(f"hmac_token:{hmac_token}")
        
        if not session_id or not hmac_token:
            logger.warning("Missing authorization data for session verification.")
            return formatted_response(request,
                                      {"error": "Missing authorizaton data.",
                                       "href": f"http://{settings.WALLET_DOMAIN}/login",
                                       "text": "Go to Login"},
                                      template_name="401.html",
                                      status=401)
            
        if not request.user or not request.user.is_authenticated:
            logger.info("Unauthenticated user during session verification; redirecting.")
            return HttpResponseRedirect(f"http://{settings.WALLET_DOMAIN}/login")
        
        try:
            timestamp, provided_hmac = unquote(hmac_token).strip('"').split(":")
            logger.info(f"htim:  {timestamp}/{provided_hmac}")
        except Exception as e:
            logger.warning(f"Failed to parse hmac token: {e}")
            return formatted_response(request,
                                      {"error": "Invalid HMAC format.",
                                       "href": f"http://{settings.WALLET_DOMAIN}/login",
                                       "text": "Go to Login"},
                                      template_name="400.html",
                                      status=400)
        
        if not HmacToken.is_valid_hmac(provided_hmac, request, timestamp):
            logger.warning(f"HMAC verification failed for user {request.user.username}")
            logout(request)
            response = HttpResponseRedirect(f"http://{settings.WALLET_DOMAIN}/login")
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

        logger.info(f"header User: {response.headers["X-User"]}")
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
