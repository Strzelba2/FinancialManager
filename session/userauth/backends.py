from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.contrib.auth import hashers
from django.db.models import Q
import logging
from typing import Optional

logger = logging.getLogger("django")
_DUMMY_PASSWORD_HASH = hashers.make_password("dummy-password")


class UsernameOrEmailBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using either their username or email.
    """
    def authenticate(self, request, username: Optional[str] = None, password: Optional[str] = None, **kwargs) -> Optional[object]:
        """
        Authenticate a user by their username or email and password.
        
        Args:
            request: The request object.
            username (str): The username or email provided by the user.
            password (str): The user's password.
            **kwargs: Additional keyword arguments.
        
        Returns:
            The authenticated user object if credentials are valid; otherwise, None.
        """
        
        logger.info("Starting authentication process.")
        
        if username is None or password is None:
            logger.warning("Username or password was not provided.")
            return None
        
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(Q(email=username) | Q(username=username))
            logger.info("User candidate found.")
            
        except UserModel.DoesNotExist:
            hashers.check_password(password, _DUMMY_PASSWORD_HASH)
            logger.warning("No user found for supplied credentials.")
            return None
        
        if user.check_password(password):
            logger.info("Password verification successful.")
            return user
        else:
            logger.warning("Password verification failed.")
            return None
