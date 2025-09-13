from celery import shared_task
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session

from .models import BlockedIP

import logging

logger = logging.getLogger("session-auth")

User = get_user_model()


@shared_task()
def delete_old_temporary_blocked_ips():
    one_month_ago = timezone.now() - timedelta(days=10)
    old_ips = BlockedIP.objects.filter(is_temporary=True, blocked_at__lt=one_month_ago)
    count = old_ips.count()
    old_ips.delete()
    logger.info(f"Deleted {count} old temporary BlockedIP entries older than one month.")
   
    
@shared_task
def delete_inactive_users_older_than_3_days():
    threshold_date = timezone.now() - timedelta(days=3)
    users_to_delete = User.objects.filter(is_active=False, date_joined__lt=threshold_date)
    count, _ = users_to_delete.delete()
    logger.info(f"Deleted {count} inactive users created before {threshold_date}")


@shared_task
def delete_invalid_sessions():
    session_to_delete = Session.objects.filter(expire_date__lt=timezone.now())
    count, _ = session_to_delete.delete()
    logger.info(f"Deleted {count} invalid sessions")
