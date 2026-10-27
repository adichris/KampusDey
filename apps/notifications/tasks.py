from celery import shared_task


@shared_task(name="notifications.send_email_batch")
def send_email_batch():
    from .services import send_email_batch as run

    return run()
