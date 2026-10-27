from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task(name="accounts.purge_axes")
def purge_axes():
    """django-axes records older than 30 days are purged (§6.11)."""
    from axes.models import AccessAttempt, AccessFailureLog, AccessLog

    cutoff = timezone.now() - timedelta(days=30)
    n = AccessAttempt.objects.filter(attempt_time__lt=cutoff).delete()[0]
    n += AccessLog.objects.filter(attempt_time__lt=cutoff).delete()[0]
    n += AccessFailureLog.objects.filter(attempt_time__lt=cutoff).delete()[0]
    return n
