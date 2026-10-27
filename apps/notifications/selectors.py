from .models import Notification


def unread_count(user) -> int:
    return Notification.objects.filter(recipient=user, read_at__isnull=True).count()


def recent(user, limit=50):
    return Notification.objects.filter(recipient=user).order_by("-created_at")[:limit]
