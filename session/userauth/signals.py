import os
import logging
from django.db import transaction
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save

from .models import UserKeys
from .crypto import wrap_dek


logger = logging.getLogger("session-auth")

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_keys(sender, instance: User, created, **kwargs) -> None:
    """
    Signal receiver that automatically generates and stores a wrapped Data Encryption Key (DEK)
    for each new user upon creation.

    Args:
        sender (type[User]): The model class that sent the signal.
        instance (User): The actual instance of the user that was created.
        created (bool): A flag indicating whether a new record was created.
        **kwargs: Additional keyword arguments provided by the signal.
    """
    logger.debug("Signal triggered: create_user_keys for user=%s (created=%s)", instance.username, created)

    if not created:
        logger.debug("User already existed, skipping key generation.")
        return
    
    dek = os.urandom(32) 
    nonce, ct = wrap_dek(dek)
    
    try:
        with transaction.atomic():
            UserKeys.objects.create(
                user=instance,
                wrapped_dek_nonce=nonce,
                wrapped_dek_ct=ct,
            )
        logger.info("Generated and stored DEK for new user '%s'", instance.username)
    except Exception as e:
        logger.error("Failed to create UserKeys for user '%s': %s", instance.username, str(e))
        raise