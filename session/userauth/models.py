from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

from .validators import UsernameValidator, EmailValidator
from .managers import UserManager

import logging
import os

logger = logging.getLogger("session-auth")
  
  
class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser.
    
    Attributes:
        first_name (CharField): The user's first name.
        last_name (CharField): The user's last name.
        email (EmailField): The user's unique email address.
        username (CharField): The user's unique username, validated with UsernameValidator.
        allowed_users (AllowedUsersStore): Stores allowed users in Redis.
    """
    
    logger.info(f"User class loaded in process PID: {os.getpid()}")

    first_name = models.CharField(verbose_name=_("First Name"), max_length=60)
    last_name = models.CharField(verbose_name=_("Last Name"), max_length=60)
    email = models.EmailField(
        verbose_name=_("Email Address"), 
        unique=True, 
        db_index=True,
        validators=[EmailValidator()]
    )
    username = models.CharField(
        verbose_name=_("Username"),
        max_length=60,
        unique=True,
        validators=[UsernameValidator()],
    )
    
    is_active = models.BooleanField(default=False)
    is_two_factor = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    objects = UserManager()
    
    class Meta:
        """
        Meta options for the User model.
        
        Attributes:
            verbose_name (str): The singular name for the User model in the admin interface.
            verbose_name_plural (str): The plural name for the User model in the admin interface.
            ordering (list): Default ordering for User instances, by date joined in descending order.
        """
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["-date_joined"]
        
    def __str__(self) -> str:
        """
        Returns the string representation of the User instance, which is the username.
        
        Returns:
            str: The username of the user.
        """
        return self.username

    @property
    def get_full_name(self) -> str:
        """
        Returns the full name of the user.
        
        Returns:
            str: The full name of the user, which combines the first and last names.
        """
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()
    
    
class BlockedIP(models.Model):
    """
    Stores IP addresses that are blocked from accessing the system.

    Tracks metadata such as:
    - IP address (unique)
    - User agent string
    - Referer URL
    - Endpoint (path) that was accessed
    - Timestamp when the IP was blocked
    - Whether the block is temporary or permanent

    Used for request filtering, brute-force prevention, and abuse monitoring.
    """
    ip_address = models.GenericIPAddressField(
        verbose_name=_("Blocked Ip"),
        unique=True,
        editable=False,
        help_text=_("The unique blocked address IP"),
        )
    user_agent = models.CharField(
        verbose_name=_("User Agent"),
        max_length=255, 
        editable=False,
        help_text=_("User agent string of the client that was blocked."),
        )
    referer = models.CharField(
        verbose_name=_("Referer"),
        max_length=255,
        editable=False,
        help_text=_("HTTP referer header of the blocked request."),
        )
    endpoint = models.CharField(
        verbose_name=_("Endpoint"),
        max_length=255,
        editable=False,
        help_text=_("The path or endpoint that triggered the block."),
        )
    blocked_at = models.DateTimeField(
        verbose_name=_("Blocked At"),
        auto_now_add=True,
        editable=False,
        help_text=_("The time when address was block"),
        )
    is_temporary = models.BooleanField(
        verbose_name=_("Is Temporary"),
        default=True,
        help_text=_("Whether the block is temporary (vs permanent)."),
        )

    def __str__(self):
        """
        Return a human-readable representation of the blocked IP entry.

        Example:
            '192.168.0.1 (Temp)'
        """
        return f"{self.ip_address} ({'Temp' if self.is_temporary else 'Permanent'})"
  

    

    


