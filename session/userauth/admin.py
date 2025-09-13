from django.contrib.admin import AdminSite
from django.contrib import admin
from django.contrib.auth import logout
from django.template.response import TemplateResponse
from django.core.cache import cache
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django_celery_beat.models import PeriodicTask
from django_celery_beat.admin import PeriodicTaskAdmin
from django.urls import path
from django.conf import settings

from .forms import UserChangeForm, UserCreationForm, CustomAdminAuthenticationForm
from .models import BlockedIP
from .two_factor import TwoFactor
from utils.utils import get_client_ip

import logging
from typing import Optional

logger = logging.getLogger("admin")

User = get_user_model()


class CustomAdminSite(AdminSite):
    """
    Custom Django AdminSite that extends login, logout, and adds support for
    two-factor authentication (2FA) setup and verification.
    """
    login_form = CustomAdminAuthenticationForm
    
    def login(self, request: HttpRequest, extra_context: Optional[dict] = None) -> HttpResponse:
        """
        Handle admin login, clear failed login cache, unblock user if necessary,
        and redirect to 2FA page if required.
        """
        response = super().login(request, extra_context)
        user = request.user
        
        if user.is_authenticated:
            ip = get_client_ip(request)
            login_attempts_ip_key = f"admin_login_attempts_ip_{ip}"
            login_attempts_key_username = f"admin_login_attempts_{user.username}"
            login_attempts_key_email = f"admin_login_attempts_{user.email}"
            cache.delete(login_attempts_key_username)
            cache.delete(login_attempts_key_email)
            cache.delete(login_attempts_ip_key)
            logger.info("Admin login successful. Cleared login attempts.")
            
            if user.is_blocked:
                user.is_blocked = False
                user.save(update_fields=["is_blocked"])
                logger.info("User unblocked after successful login.")
                
            if user.is_two_factor and not user.is_verified:
                return redirect('/admin/two-factor/')
            else:
                return redirect('/admin/')

        return response

    def logout(self, request: HttpRequest, extra_context: Optional[dict] = None) -> HttpResponse:
        """
        Handle logout. Reset 2FA verification state if necessary.
        """
        user = request.user
        if user.is_authenticated:
            if user.is_two_factor and user.is_verified:
                user.is_verified = False
                user.save(update_fields=["is_verified"])
                logger.info("User 2FA status reset on logout.")
                
        return super().logout(request, extra_context)

    def qrcode_view(self, request: HttpRequest) -> HttpResponse:
        """
        Display and handle QR code generation for 2FA setup.
        """
        logger.info("Starting QR code setup for 2FA.")
        
        if not request.user.is_authenticated:
            messages.error(request, "You must be logged in to configure 2FA settings.")
            return redirect("/admin/login/")

        user_id = request.GET.get("user_id")
        
        if not user_id or not user_id.isdigit():
            logger.warning("Invalid or missing user ID in QR code request.")
            messages.error(request, "Invalid user ID.")
            return redirect("/admin/userauth/user/")

        user = get_object_or_404(User, pk=user_id)
        
        logged_user = request.user

        if user != logged_user:
            logger.warning("User tried to change 2FA for another account.")
            messages.error(request, "You can change 2FA settings only for your own account.")
            return redirect("/admin/userauth/user/")
        
        if logged_user.is_two_factor:
            logged_user.is_two_factor = False
            logged_user.save(update_fields=["is_two_factor"])
            logger.info("User disabled 2FA.")
            messages.error(request, "you have successfully disabled 2fa login.")
            return redirect("/admin/userauth/user/")

        secret_key = TwoFactor.generate_secret_key(email=user.email, username=user.username)
        provisioning_uri = TwoFactor.generate_provisioning_uri(secret_key, username=user.username)
        qr_code_image = TwoFactor.generate_qr_code(provisioning_uri)
        
        logged_user.is_two_factor = True
        logged_user.save(update_fields=["is_two_factor"])
        
        logger.info("User enabled 2FA.")
        
        logout(request)

        context = {'image': qr_code_image, 'title': 'QR Code Setup'}
        return TemplateResponse(request, 'admin/qrcode.html', context)
    
    @method_decorator(csrf_protect)
    def two_factor_verify_view(self, request: HttpRequest) -> HttpResponse:
        """
        Handle 2FA token verification. Redirect or block access based on result.
        """
        logger.info("Starting 2FA verification view.")
        
        if not request.user.is_authenticated:
            logger.warning("Unauthenticated user tried to access 2FA view.")
            messages.error(request, "You must be logged in.")
            return redirect("/admin/login/")

        if request.method == "POST":
            token = request.POST.get("token")
            login_attempts_key = f"admin_login_2fa_attempts_{request.user.username}"
            login_attempts = cache.get(login_attempts_key, 0)
            
            logger.info(f"2FA attempt for user {request.user.username}, attempt {login_attempts + 1}")
            if login_attempts <= 2:
                if TwoFactor.verify_token(request.user.email, request.user.username, token):
                    request.user.is_verified = True
                    request.user.save(update_fields=["is_verified"])
                    logger.info(f"2FA passed for user {request.user.username}")
                    messages.success(request, "Two-factor authentication complete.")
                    return redirect("/admin/") 
                else:
                    logger.warning(f"Failed 2FA for user {request.user.username}")
                    cache.set(login_attempts_key, login_attempts + 1, timeout=settings.ADMIN_TEMPORARY_BLOCK_TIME)
                    messages.error(request, "Invalid 2FA code. Try again.")
            else:
                logger.error("Too many failed 2FA attempts. Logging user out.")
                next_login = settings.ADMIN_TEMPORARY_BLOCK_TIME / 60
                
                messages.error(request, f"Too many failed attempts. Please log in again in {next_login} minutes.")
                logout(request)
                cache.delete(login_attempts_key)
                return redirect("/admin/login/")
            
        context = {
            "title": _("Verify Two-Factor Authentication"),
        }
        return TemplateResponse(request, "admin/twofactor.html", context)
    
    def get_urls(self):
        """
        Add custom admin URLs for QR code and 2FA verification.
        """
        urls = super().get_urls()
        custom_urls = [
            path("qrcode/", self.admin_view(self.qrcode_view), name="qrcode"),
            path("two-factor/", self.admin_view(self.two_factor_verify_view), name="two_factor_verify"),
        ]
        return custom_urls + urls


class UserAdmin(BaseUserAdmin):
    """
    Customizes the Django admin interface for the User model.

    Provides a user-friendly layout with links and organized field groups, allowing
    easier navigation and management of user records. This class configures forms,
    display options, and filtering/searching capabilities in the User admin section.
    """
    
    class Media:
        js = ('js/custom_user_admin.js',)
    
    # Forms to use for adding and changing users in the admin interface
    form = UserChangeForm
    add_form = UserCreationForm
    
    # Fields to display in the list view
    list_display = [
        "email",
        "first_name",
        "last_name",
        "is_superuser"
    ]
    
    list_display_links = ["email"]
    
    # Fields to allow search and filter options
    search_fields = ["email", "first_name", "last_name"]
    list_filter = ('is_staff', 'is_active', 'is_blocked')
 
    # Order users by email in the list view
    ordering = ["email"]
    
    # Define field grouping in the user detail view
    fieldsets = (
        (_("Login Credentials"), {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "username", "is_two_factor", "is_blocked")}),
        (
            _("Permissions and Groups"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important Dates"), {"fields": ("last_login", "date_joined")}),
    )
    
    # Field grouping in the user creation form
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


custom_admin_site = CustomAdminSite()

if not hasattr(admin, '_custom_admin_registered'):

    for model, model_admin in admin.site._registry.items():
        custom_admin_site.register(model, type(model_admin))
        
    admin.site = custom_admin_site

    custom_admin_site.register(BlockedIP)

    if PeriodicTask not in custom_admin_site._registry:
        custom_admin_site.register(PeriodicTask, PeriodicTaskAdmin)

    custom_admin_site.register(User, UserAdmin)

    admin._custom_admin_registered = True
