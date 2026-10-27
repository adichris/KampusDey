from celery import shared_task


@shared_task(name="growth.weekly_digest")
def weekly_digest():
    from .services import send_weekly_digest

    return send_weekly_digest()
