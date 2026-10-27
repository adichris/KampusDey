from celery import shared_task


@shared_task(name="engagement.saved_search_alerts")
def saved_search_alerts():
    from .services import run_saved_search_alerts

    return run_saved_search_alerts()
