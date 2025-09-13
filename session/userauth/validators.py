from django.core.exceptions import ValidationError
from django.core import validators
from django.conf import settings
from django.utils.translation import gettext as _
import re

import logging

logger = logging.getLogger("session-auth")


class CustomPasswordValidator:
    """
    A custom password validator that enforces strong password requirements.

    The password must:
    - Be at least 12 characters long.
    - Contain at least one uppercase letter.
    - Contain at least one lowercase letter.
    - Contain at least one digit.
    - Contain at least one special character from the set: !@#$%^&*(),.?":{}|<>.
    """
    def validate(self, password: str, user=None) -> None:
        """
        Validate a password against predefined strength rules.

        Args:
            password (str): The password to validate.
            user: The user associated with the password (default is None).

        Raises:
            ValidationError: If the password fails any of the strength checks.
        """
        logger.debug("Validating password for strength requirements.")
        
        if len(password) < 12:
            logger.error("Password validation failed: too short.")
            raise ValidationError(
                _("Password must be at least 12 characters long.")
            )
        if not re.search(r"[A-Z]", password):
            logger.error("Password validation failed: missing uppercase letter.")
            raise ValidationError(
                _("Password must contain at least one uppercase letter.")
            )
        if not re.search(r"[a-z]", password):
            logger.error("Password validation failed: missing lowercase letter.")
            raise ValidationError(
                _("Password must contain at least one lowercase letter.")
            )
        if not re.search(r"[0-9]", password):
            logger.error("Password validation failed: missing digit.")
            raise ValidationError(
                _("Password must contain at least one digit.")
            )
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            logger.error("Password validation failed: missing special character.")
            raise ValidationError(
                _("Password must contain at least one special character.")
            )
        
        logger.info("Password passed all strength validation checks.")

    def get_help_text(self) -> str:
        """
        Provide a help text describing the password requirements.

        Returns:
            str: A description of the password requirements.
        """
        logger.debug("Retrieving password help text.")
        return _(
            "Your password must be at least 12 characters long, "
            "contain at least one uppercase letter, one lowercase letter, "
            "one digit, and one special character."
        )
 
        
class UsernameValidator(validators.RegexValidator):
    """
    Validator for the username field, ensuring it meets specific character requirements.
    Allows only letters, numbers, dots, @, +, and hyphens.
    """
    regex = r"^[\w.+-]+\Z"
    message = _(
        "username is not valid. A username can only contain letters, numbers, a dot, "
        " + symbol and a hyphen "
    )
 

class EmailValidator(validators.EmailValidator):   
    """
    Custom email validator that extends Django's built-in `EmailValidator`.
    """
    domain_allowlist = settings.EMAIL_DOMAIN_ALLOWED_LIST
    
