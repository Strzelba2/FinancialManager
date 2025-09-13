from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import make_password
from django.apps import apps

from .validators import EmailValidator

import logging
from typing import Optional

logger = logging.getLogger("session-auth")


class UserManager(DjangoUserManager):
    """
    Custom user manager for creating standard and superuser accounts with validation.

    Methods:
        - _create_user: Internal method to handle user creation with validations.
        - create_user: Creates a standard user.
        - create_superuser: Creates a superuser.
    """
    
    validate_email_address = EmailValidator()
    
    def _create_user(
        self, username: str, email: str, password: Optional[str] = None, **extra_fields
    ):
        """
        Internal method to create and save a user with the given username, email, and password.

        Args:
            username (str): The username for the user.
            email (str): The email address for the user.
            password (Optional[str]): The password for the user.
            **extra_fields: Additional fields for the user.

        Returns:
            User: The created user instance.

        Raises:
            ValueError: If required fields (username, email, password) are missing or invalid.
        """
        logger.debug("Starting user creation process.")
        
        if not password:
            logger.error("Password field cannot be empty.")
            raise ValueError("The password field cannot be empty.")
        
        if not username:
            logger.error("Username must be provided.")
            raise ValueError(_("A username must be provided"))

        if not email:
            logger.error("Email address must be provided.")
            raise ValueError(_("An email address must be provided"))
        
        try:
            validate_password(password) 
            logger.debug("Password validation passed.")
        except ValidationError as e:
            raise ValueError(f"Password validation error: {e.messages}")

        email = self.normalize_email(email)
        self.validate_email_address(email)
        
        global_user_model = apps.get_model(
            self.model._meta.app_label, self.model._meta.object_name
        )
        username = global_user_model.normalize_username(username)
        user = self.model(username=username, email=email, **extra_fields)
        user.password = make_password(password)
        
        try:
            user.full_clean() 
            logger.debug("User data validated successfully.")
        except ValidationError as e:
            logger.error(f"Validation error: {e.message_dict}")
            raise ValueError(f"Validation error: {e.message_dict}")
        
        user.save(using=self._db)
        logger.info(f"User '{username}' created successfully.")
        return user

    def create_user(
        self,
        username: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        **extra_fields
    ):
        """
        Creates a standard user.

        Args:
            username (str): The username for the user.
            email (Optional[str]): The email address for the user.
            password (Optional[str]): The password for the user.
            **extra_fields: Additional fields for the user.

        Returns:
            User: The created user instance.
        """
        logger.debug("Creating standard user.")
        
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(
        self,
        username: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        **extra_fields
    ):
        """
        Creates a superuser.

        Args:
            username (str): The username for the superuser.
            email (Optional[str]): The email address for the superuser.
            password (Optional[str]): The password for the superuser.
            **extra_fields: Additional fields for the user.

        Returns:
            User: The created superuser instance.

        Raises:
            ValueError: If `is_staff` or `is_superuser` fields are not correctly set.
        """
        logger.debug("Creating superuser.")
        
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True) 

        if extra_fields.get("is_staff") is not True:
            logger.error("Superuser must have is_staff=True.")
            raise ValueError(_("Superuser must have is_staff=True."))

        if extra_fields.get("is_superuser") is not True:
            logger.error("Superuser must have is_superuser=True.")
            raise ValueError(_("Superuser must have is_superuser=True."))

        logger.info("Superuser creation in progress.")
        return self._create_user(username, email, password, **extra_fields)
    
    def get_or_create(self, **kwargs):
        password = kwargs.pop("password", None)
        user, created = super().get_or_create(**kwargs)

        if created and password:
            try:
                validate_password(password)
                user.set_password(password)
                user.save()
            except ValidationError as e:
                user.delete()
                raise ValueError(f"Password validation error: {', '.join(e.messages)}")

        return user, created
